"""Nightly attendance check scheduler.

每晚定时执行考勤打卡检查，并将结果推送到 Telegram。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from aiogram import Bot

from bot.agent.client import AgentManager

# Telegram 单条消息上限 4096 字符，预留 ~200 字符余量
_TELEGRAM_TEXT_LIMIT = 3900

logger = logging.getLogger(__name__)
_SCHEDULER_SESSION_SCOPE = "telegram-scheduler:nightly-attendance"


def _parse_time_of_day(value: str) -> tuple[int, int]:
    """解析 "HH:MM" 格式的时间字符串，返回 (时, 分)。"""
    hour_str, minute_str = value.split(":", maxsplit=1)
    return int(hour_str), int(minute_str)


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
        self._hour, self._minute = _parse_time_of_day(run_time)
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

    def _next_run_at(self, now: datetime | None = None) -> datetime:
        """计算下一次执行时间点；若今天已过则推迟到明天同一时刻。"""
        current = now or datetime.now(self._timezone)
        target = current.replace(
            hour=self._hour,
            minute=self._minute,
            second=0,
            microsecond=0,
        )
        if target <= current:
            target += timedelta(days=1)
        return target

    # 重试间隔（秒）：第1次 60s，第2次 180s，第3次及之后 300s
    _RETRY_DELAYS = (60, 180, 300)

    def _retry_delay_seconds(self, attempt_index: int) -> int:
        """根据重试次数返回递增的延迟秒数。"""
        return self._RETRY_DELAYS[min(attempt_index, len(self._RETRY_DELAYS) - 1)]

    async def _run_loop(self) -> None:
        """主循环：计算等待时间 → sleep 到目标时刻 → 执行检查 → 重复。"""
        try:
            while True:
                now = datetime.now(self._timezone)
                run_at = self._next_run_at(now)
                # 至少等待 1 秒，防止时间精度导致立即重跑
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
                    delay = self._retry_delay_seconds(attempt)
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
