"""Cancel intercept middleware — swallows "取消" messages during an active cancel window."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from bot.scheduler.cancel_gate import CancelGate


class CancelInterceptMiddleware(BaseMiddleware):
    """Intercept "取消" messages when the auto-punch cancel window is open.

    If the gate is active and the message is exactly "取消", calls gate.try_cancel()
    and swallows the message (returns None without calling downstream handlers).
    All other messages pass through unchanged.
    """

    def __init__(self, cancel_gate: CancelGate) -> None:
        super().__init__()
        self._gate = cancel_gate

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if (
            isinstance(event, Message)
            and self._gate.active
            and (event.text or "").strip() == "取消"
        ):
            self._gate.try_cancel()
            return None  # swallow — do not forward to agent or other handlers
        return await handler(event, data)
