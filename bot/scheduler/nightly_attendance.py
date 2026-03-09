"""Nightly attendance check scheduler.

每晚定时执行考勤打卡检查，并将结果推送到 Telegram。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from aiogram import Bot

from bot.agent.client import AgentManager
from bot.scheduler.utils import get_retry_delay, next_run_at, parse_time

# Telegram 单条消息上限 4096 字符，预留 ~200 字符余量
_TELEGRAM_TEXT_LIMIT = 3900

logger = logging.getLogger(__name__)
_SCHEDULER_SESSION_SCOPE = "telegram-scheduler:nightly-attendance"


def _split_text(text: str, limit: int = _TELEGRAM_TEXT_LIMIT) -> list[str]:
    """将长文本按 limit 拆分成多段，优先在换行处断开。"""
    cleaned = text.strip()
    if not cleaned:
        return []

    chunks: list[str] = []
    current = cleaned
    while len(current) > limit:
        # 尽量在换行符处拆分，避免截断一行文字
        split_at = current.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(current[:split_at].strip())
        current = current[split_at:].strip()
    if current:
        chunks.append(current)
    return chunks


class NightlyAttendanceScheduler:
    """每晚定时考勤检查调度器，检查结果推送给 Telegram owner。"""

    def __init__(
        self,
        *,
        bot: Bot,
        agent_manager: AgentManager,
        owner_id: int,
        enabled: bool,
        run_time: str,
        timezone_name: str,
        retries: int,
        prompt: str,
    ) -> None:
        self._bot = bot
        self._agent_manager = agent_manager
        self._owner_id = owner_id
        self._enabled = enabled
        self._run_time = run_time
        # 解析配置的执行时间
        self._hour, self._minute = parse_time(run_time)
        self._timezone_name = timezone_name
        self._timezone = ZoneInfo(timezone_name)
        self._retries = retries
        self._prompt = prompt
        # 后台调度任务引用
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """启动调度器，创建后台循环任务。"""
        if not self._enabled:
            logger.info("Nightly attendance scheduler disabled")
            return
        # 避免重复启动
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(
            self._run_loop(),
            name="nightly-attendance-scheduler",
        )
        logger.info(
            "Nightly attendance scheduler started: time=%s timezone=%s retries=%s",
            self._run_time,
            self._timezone_name,
            self._retries,
        )

    async def stop(self) -> None:
        """停止调度器，取消后台任务并等待退出。"""
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("Nightly attendance scheduler stopped")

    async def _run_loop(self) -> None:
        """主循环：计算等待时间 → sleep 到目标时刻 → 执行检查 → 重复。"""
        try:
            while True:
                run_at = next_run_at(self._hour, self._minute, self._timezone)
                # 至少等待 1 秒，防止时间精度导致立即重跑
                now = datetime.now(self._timezone)
                sleep_seconds = max((run_at - now).total_seconds(), 1.0)
                logger.info(
                    "Nightly attendance next run scheduled at %s",
                    run_at.isoformat(),
                )
                await asyncio.sleep(sleep_seconds)
                try:
                    await self._run_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Nightly attendance run crashed")
        except asyncio.CancelledError:
            logger.info("Nightly attendance scheduler loop cancelled")
            raise

    async def _run_once(self) -> None:
        """执行一次考勤检查，失败时按配置重试，最终将结果发送给 owner。"""
        started = datetime.now(self._timezone)
        last_error: Exception | None = None
        await self._agent_manager.reset_session(_SCHEDULER_SESSION_SCOPE)

        for attempt in range(self._retries + 1):
            try:
                # 调用 Agent 查询考勤状态
                result = await self._agent_manager.query(
                    self._prompt,
                    session_scope=_SCHEDULER_SESSION_SCOPE,
                )
                text = (
                    f"【每晚打卡检查 {started.strftime('%Y-%m-%d %H:%M')}】\n"
                    f"{result.strip() or '未获取到结果，请手动确认。'}"
                )
                await self._send_text(text)
                logger.info(
                    "Nightly attendance check succeeded: attempt=%s",
                    attempt + 1,
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                # 还有剩余重试次数，等待后重试
                if attempt < self._retries:
                    delay = get_retry_delay(attempt)
                    logger.warning(
                        "Nightly attendance attempt failed, retrying: attempt=%s delay=%ss error=%s",
                        attempt + 1,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue

        # 所有重试均失败，发送错误通知
        logger.error(
            "Nightly attendance check failed after retries: attempts=%s error=%s",
            self._retries + 1,
            last_error,
        )
        error_text = (
            f"【每晚打卡检查失败 {started.strftime('%Y-%m-%d %H:%M')}】\n"
            f"原因：{last_error}"
        )
        try:
            await self._send_text(error_text)
        except Exception:
            logger.exception("Failed to send nightly attendance failure notification")

    async def _send_text(self, text: str) -> None:
        """将文本拆分后逐段发送给 owner。"""
        chunks = _split_text(text)
        if not chunks:
            return
        for chunk in chunks:
            await self._bot.send_message(chat_id=self._owner_id, text=chunk)
