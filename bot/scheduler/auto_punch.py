"""Automatic attendance punch scheduler.

每日在上班/下班时间前发送 Telegram 通知，若用户 3 分钟内未回复"取消"则自动打卡。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
import os
from zoneinfo import ZoneInfo

from aiogram import Bot

from cli.types import AttendanceResolvedMode
from bot.scheduler.cancel_gate import CancelGate
from bot.scheduler.utils import get_retry_delay, next_run_at, parse_time

logger = logging.getLogger(__name__)

# SSO 错误关键词（与 helper.py 保持一致）
_SSO_KEYWORDS = (
    "SSO authentication failed",
    "SSO redirect request failed",
    "CAS login",
    "CAS did not return redirect",
    "No ticket in CAS redirect",
    "JWXT",
    "userCode/md5Str not found",
    "id_token is required",
)

class SessionError(Exception):
    """Raised when no valid session is available and auto-login fails."""


def _is_sso_error(error_msg: str) -> bool:
    return any(kw in error_msg for kw in _SSO_KEYWORDS)


def _auto_login_sync() -> str | None:
    """Attempt login using ZUEB_USERNAME / ZUEB_PASSWORD from environment."""
    from cli.auth.login import login as do_login

    username = os.environ.get("ZUEB_USERNAME", "")
    password = os.environ.get("ZUEB_PASSWORD", "")
    if not username or not password:
        return None
    try:
        result = do_login(username, password)
        return result["id_token"]
    except Exception:
        logger.exception("Auto-login failed")
        return None


def _ensure_session_sync() -> str:
    """Return a valid id_token, auto-logging in if needed. Raises SessionError on failure."""
    from cli.auth.token import load_session

    session = load_session()
    if session and session.get("id_token"):
        return session["id_token"]

    token = _auto_login_sync()
    if token:
        return token

    raise SessionError("未登录，且自动登录失败，请先执行 /login。")


def _window_seconds(notify: str, punch: str) -> float:
    """Return seconds between notify_time and punch_time."""
    nh, nm = parse_time(notify)
    ph, pm = parse_time(punch)
    return float((ph * 60 + pm - nh * 60 - nm) * 60)


class AutoPunchScheduler:
    """工作日自动打卡调度器：上班卡 + 下班卡各一个后台循环 Task。"""

    def __init__(
        self,
        *,
        bot: Bot,
        cancel_gate: CancelGate,
        owner_id: int,
        enabled: bool,
        timezone_name: str,
        morning_notify: str,
        morning_punch: str,
        evening_notify: str,
        evening_punch: str,
        retries: int,
    ) -> None:
        self._bot = bot
        self._cancel_gate = cancel_gate
        self._owner_id = owner_id
        self._enabled = enabled
        self._timezone = ZoneInfo(timezone_name)
        self._timezone_name = timezone_name

        self._morning_notify = morning_notify
        self._morning_notify_h, self._morning_notify_m = parse_time(morning_notify)
        self._morning_window = _window_seconds(morning_notify, morning_punch)

        self._evening_notify = evening_notify
        self._evening_notify_h, self._evening_notify_m = parse_time(evening_notify)
        self._evening_window = _window_seconds(evening_notify, evening_punch)

        self._retries = retries
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        """启动上班卡和下班卡两个独立后台调度循环。"""
        if not self._enabled:
            logger.info("Auto punch scheduler disabled")
            return
        self._tasks = [
            asyncio.create_task(
                self._punch_loop(
                    label="morning",
                    notify_hour=self._morning_notify_h,
                    notify_minute=self._morning_notify_m,
                    window_seconds=self._morning_window,
                    mode="sbk",
                ),
                name="auto-punch-morning",
            ),
            asyncio.create_task(
                self._punch_loop(
                    label="evening",
                    notify_hour=self._evening_notify_h,
                    notify_minute=self._evening_notify_m,
                    window_seconds=self._evening_window,
                    mode="xbk",
                ),
                name="auto-punch-evening",
            ),
        ]
        logger.info(
            "Auto punch scheduler started: morning=%s evening=%s timezone=%s retries=%s",
            self._morning_notify,
            self._evening_notify,
            self._timezone_name,
            self._retries,
        )

    async def stop(self) -> None:
        """停止两个调度循环。"""
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("Auto punch scheduler stopped")

    async def _punch_loop(
        self,
        label: str,
        notify_hour: int,
        notify_minute: int,
        window_seconds: float,
        mode: AttendanceResolvedMode,
    ) -> None:
        """主循环：sleep 到通知时间 → 执行打卡周期 → 重复。"""
        try:
            while True:
                run_at = next_run_at(notify_hour, notify_minute, self._timezone)
                now = datetime.now(self._timezone)
                sleep_seconds = max((run_at - now).total_seconds(), 1.0)
                logger.info(
                    "Auto punch [%s] next run at %s", label, run_at.isoformat()
                )
                await asyncio.sleep(sleep_seconds)
                try:
                    await self._punch_cycle(mode=mode, window_seconds=window_seconds)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Auto punch [%s] cycle crashed", label)
        except asyncio.CancelledError:
            logger.info("Auto punch [%s] loop cancelled", label)
            raise

    async def _punch_cycle(
        self, mode: AttendanceResolvedMode, window_seconds: float
    ) -> None:
        """单次打卡周期：工作日检查 → 状态检查 → 通知 → 等待取消 → 打卡。"""
        import chinese_calendar
        from cli.attendance.service import AttendanceError, get_attendance_status

        card_label = "上班卡" if mode == "sbk" else "下班卡"
        today = datetime.now(self._timezone).date()

        # 1. 工作日检查
        try:
            is_holiday, _ = await asyncio.to_thread(
                chinese_calendar.get_holiday_detail, today
            )
        except NotImplementedError:
            logger.warning(
                "No holiday data for year %s, treating as workday", today.year
            )
            is_holiday = False

        if is_holiday:
            logger.debug("Auto punch [%s] skipped: not a workday (%s)", mode, today)
            return

        # 2. 获取会话
        try:
            id_token = await asyncio.to_thread(_ensure_session_sync)
        except SessionError as exc:
            logger.error("Auto punch [%s] session error: %s", mode, exc)
            await self._notify(f"【自动打卡】无法获取登录状态：{exc}")
            return

        # 3. 查询当前打卡状态（含 SSO 重试）
        done_key = "sbk_done" if mode == "sbk" else "xbk_done"
        try:
            status = await asyncio.to_thread(get_attendance_status, id_token)
        except AttendanceError as exc:
            if _is_sso_error(str(exc)):
                logger.info("Auto punch [%s] SSO error on status check, relogin", mode)
                new_token = await asyncio.to_thread(_auto_login_sync)
                if new_token:
                    id_token = new_token
                    try:
                        status = await asyncio.to_thread(get_attendance_status, new_token)
                    except AttendanceError as exc2:
                        await self._notify(f"【自动打卡】考勤查询失败：{exc2}")
                        return
                else:
                    await self._notify(f"【自动打卡】SSO 认证失败，自动重登录也失败：{exc}")
                    return
            else:
                await self._notify(f"【自动打卡】考勤查询失败：{exc}")
                return

        # 4. 已打卡则静默跳过
        if status[done_key]:
            logger.debug("Auto punch [%s] skipped: already done", mode)
            return

        # 5. 发送通知并打开取消窗口
        window_min = int(window_seconds // 60)
        self._cancel_gate.open(label=f"auto-punch-{mode}")
        try:
            await self._notify(
                f'即将在 {window_min} 分钟后自动打{card_label}，回复\u201c取消\u201d可阻止。'
            )

            # 6. 等待取消或超时
            cancelled = await self._cancel_gate.wait_or_timeout(window_seconds)

            if cancelled:
                await self._notify(f"自动打{card_label}已取消。")
                return

            # 7. 执行打卡（含重试）
            await self._do_punch(id_token=id_token, mode=mode, card_label=card_label)
        finally:
            self._cancel_gate.close()

    async def _do_punch(
        self, id_token: str, mode: AttendanceResolvedMode, card_label: str
    ) -> None:
        """执行打卡，SSO 重登录后继续沿用剩余重试次数。"""
        from cli.attendance.service import AttendanceError, punch_attendance

        last_error: Exception | None = None
        current_token = id_token

        for attempt in range(self._retries + 1):
            try:
                result = await asyncio.to_thread(
                    lambda tok=current_token: punch_attendance(tok, mode=mode)
                )
                msg = result.get("message") or "打卡请求已提交"
                await self._notify(f"【自动打卡】{card_label}完成：{msg}")
                return
            except AttendanceError as exc:
                if _is_sso_error(str(exc)):
                    logger.info("Auto punch SSO error on punch, relogin")
                    new_token = await asyncio.to_thread(_auto_login_sync)
                    if not new_token:
                        await self._notify(
                            f"【自动打卡】{card_label}失败（SSO 认证失败，重登录也失败）：{exc}"
                        )
                        return
                    current_token = new_token
                    try:
                        result = await asyncio.to_thread(
                            lambda tok=current_token: punch_attendance(tok, mode=mode)
                        )
                        msg = result.get("message") or "打卡请求已提交"
                        await self._notify(f"【自动打卡】{card_label}完成：{msg}")
                        return
                    except AttendanceError as exc2:
                        if _is_sso_error(str(exc2)):
                            await self._notify(
                                f"【自动打卡】{card_label}失败（SSO 认证失败，重登录后仍无法打卡）：{exc2}"
                            )
                            return
                        last_error = exc2
                else:
                    last_error = exc

                if attempt < self._retries:
                    delay = get_retry_delay(attempt)
                    logger.warning(
                        "Auto punch failed, retrying: attempt=%s delay=%ss error=%s",
                        attempt + 1,
                        delay,
                        last_error,
                    )
                    await asyncio.sleep(delay)
                    continue

        await self._notify(f"【自动打卡】{card_label}失败（已重试 {self._retries} 次）：{last_error}")

    async def _notify(self, text: str) -> None:
        """向 owner 发送 Telegram 消息。"""
        try:
            await self._bot.send_message(chat_id=self._owner_id, text=text)
        except Exception:
            # 设计选择：提醒消息发送失败时，自动打卡仍继续执行，避免把 Telegram 可用性
            # 变成打卡流程的硬依赖。
            logger.exception("Auto punch: failed to send notification: %r", text)
