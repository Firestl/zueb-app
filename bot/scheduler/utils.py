"""Shared utilities for scheduler components."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# 重试延迟（秒）：第1次 60s，第2次 180s，第3次及之后 300s
RETRY_DELAYS = (60, 180, 300)


def parse_time(value: str) -> tuple[int, int]:
    """解析 "HH:MM" 格式的时间字符串，返回 (时, 分)。"""
    h, m = value.split(":", maxsplit=1)
    return int(h), int(m)


def next_run_at(hour: int, minute: int, tz: ZoneInfo) -> datetime:
    """计算指定时:分的下次触发时间（今天已过则推到明天）。"""
    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def get_retry_delay(attempt: int) -> int:
    """根据重试次数返回递增的延迟秒数。"""
    return RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
