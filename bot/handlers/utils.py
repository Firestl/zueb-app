"""Shared utilities for Telegram handlers."""


def chat_session_scope(chat_id: int | None) -> str:
    """根据 Telegram chat_id 生成 Agent session scope 标识。"""
    if chat_id is None:
        return "telegram-chat:unknown"
    return f"telegram-chat:{chat_id}"
