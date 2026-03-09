"""配置加载模块，从环境变量读取所有运行时配置。"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 时间格式校验正则：匹配 "HH:MM"
_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


# 不可变配置数据类，保存所有运行时配置项
@dataclass(frozen=True)
class BotConfig:
    telegram_bot_token: str
    anthropic_api_key: str
    anthropic_base_url: str | None
    anthropic_model: str | None
    bot_log_level: str
    owner_id: int
    nightly_check_enabled: bool
    nightly_check_time: str
    nightly_check_timezone: str
    nightly_check_retries: int
    nightly_check_prompt: str
    auto_punch_enabled: bool
    auto_punch_timezone: str
    auto_punch_morning_notify: str
    auto_punch_morning_punch: str
    auto_punch_evening_notify: str
    auto_punch_evening_punch: str
    auto_punch_retries: int


# 读取必需的环境变量，缺失时抛出异常
def _must_get_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# 读取可选的环境变量，不存在则返回 None
def _optional_get_env(name: str) -> str | None:
    value = (os.getenv(name) or "").strip()
    return value or None


# 读取布尔型环境变量，支持 true/false/1/0/yes/no 等写法
def _get_bool_env(name: str, default: bool) -> bool:
    value = _optional_get_env(name)
    if value is None:
        return default
    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean: true/false")


# 读取日志级别，默认 INFO，仅允许标准日志级别
def _get_log_level() -> str:
    value = (_optional_get_env("BOT_LOG_LEVEL") or "INFO").upper()
    allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if value not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise RuntimeError(f"BOT_LOG_LEVEL must be one of: {allowed_text}")
    return value


# 读取并校验 HH:MM 格式时间；若缺失使用 default
def _get_time_env(name: str, default: str) -> str:
    value = _optional_get_env(name) or default
    if not _TIME_PATTERN.match(value):
        raise RuntimeError(f"{name} must be in HH:MM format")
    hour, minute = _time_parts(value)
    if hour not in range(24) or minute not in range(60):
        raise RuntimeError(f"{name} must be a valid 24h time")
    return value


# 读取每晚考勤检查时间，默认 "21:30"，校验 HH:MM 格式和合法范围
def _get_nightly_time() -> str:
    return _get_time_env("NIGHTLY_CHECK_TIME", "21:30")


# 读取并校验 IANA 时区；若缺失使用 default
def _get_timezone_env(name: str, default: str) -> str:
    value = _optional_get_env(name) or default
    try:
        ZoneInfo(value)
    except Exception as exc:
        raise RuntimeError(f"{name} must be a valid IANA timezone") from exc
    return value


# 读取整数型环境变量，校验范围 [min_val, max_val]
def _get_int_env(name: str, default: int, min_val: int = 0, max_val: int = 5) -> int:
    value = _optional_get_env(name)
    if value is None:
        return default
    try:
        result = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if result < min_val or result > max_val:
        raise RuntimeError(f"{name} must be in range {min_val}..{max_val}")
    return result


# 读取考勤检查提示词，默认 "查看是否打卡"
def _get_nightly_prompt() -> str:
    value = _optional_get_env("NIGHTLY_CHECK_PROMPT") or "查看是否打卡"
    if not value.strip():
        raise RuntimeError("NIGHTLY_CHECK_PROMPT cannot be empty")
    return value


def _time_parts(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def _time_to_minutes(value: str) -> int:
    hour, minute = _time_parts(value)
    return hour * 60 + minute


# 校验 notify_time 早于 punch_time（两者为同一天内的 HH:MM）
def _assert_notify_before_punch(notify_name: str, notify: str, punch_name: str, punch: str) -> None:
    if _time_to_minutes(notify) >= _time_to_minutes(punch):
        raise RuntimeError(f"{notify_name} ({notify}) must be earlier than {punch_name} ({punch})")


def _assert_auto_punch_window(punch_name: str, punch: str, *, mode: str) -> None:
    if mode == "morning" and _time_to_minutes(punch) >= _time_to_minutes("08:00"):
        raise RuntimeError(f"{punch_name} ({punch}) must be earlier than 08:00")
    if mode == "evening" and _time_to_minutes(punch) < _time_to_minutes("16:30"):
        raise RuntimeError(f"{punch_name} ({punch}) must be at or after 16:30")


# 组装并返回完整的 BotConfig 配置对象
def load_config() -> BotConfig:
    # 读取必需配置
    telegram_bot_token = _must_get_env("TELEGRAM_BOT_TOKEN")
    anthropic_api_key = _must_get_env("ANTHROPIC_API_KEY")
    anthropic_base_url = _optional_get_env("ANTHROPIC_BASE_URL")
    anthropic_model = _optional_get_env("ANTHROPIC_MODEL")
    bot_log_level = _get_log_level()
    owner_id_raw = _must_get_env("OWNER_ID")
    # 读取每晚考勤相关配置
    nightly_check_enabled = _get_bool_env("NIGHTLY_CHECK_ENABLED", default=True)
    nightly_check_time = _get_nightly_time()
    nightly_check_timezone = _get_timezone_env("NIGHTLY_CHECK_TIMEZONE", "Asia/Shanghai")
    nightly_check_retries = _get_int_env("NIGHTLY_CHECK_RETRIES", default=2)
    nightly_check_prompt = _get_nightly_prompt()

    # 读取自动打卡相关配置
    auto_punch_enabled = _get_bool_env("AUTO_PUNCH_ENABLED", default=False)
    auto_punch_timezone = _get_timezone_env("AUTO_PUNCH_TIMEZONE", "Asia/Shanghai")
    auto_punch_morning_notify = _get_time_env("AUTO_PUNCH_MORNING_NOTIFY", "07:52")
    auto_punch_morning_punch = _get_time_env("AUTO_PUNCH_MORNING_PUNCH", "07:55")
    auto_punch_evening_notify = _get_time_env("AUTO_PUNCH_EVENING_NOTIFY", "17:57")
    auto_punch_evening_punch = _get_time_env("AUTO_PUNCH_EVENING_PUNCH", "18:00")
    _assert_notify_before_punch(
        "AUTO_PUNCH_MORNING_NOTIFY", auto_punch_morning_notify,
        "AUTO_PUNCH_MORNING_PUNCH", auto_punch_morning_punch,
    )
    _assert_auto_punch_window(
        "AUTO_PUNCH_MORNING_PUNCH", auto_punch_morning_punch, mode="morning"
    )
    _assert_notify_before_punch(
        "AUTO_PUNCH_EVENING_NOTIFY", auto_punch_evening_notify,
        "AUTO_PUNCH_EVENING_PUNCH", auto_punch_evening_punch,
    )
    _assert_auto_punch_window(
        "AUTO_PUNCH_EVENING_PUNCH", auto_punch_evening_punch, mode="evening"
    )
    auto_punch_retries = _get_int_env("AUTO_PUNCH_RETRIES", default=1)

    # 将 OWNER_ID 转为整数（Telegram 用户 ID）
    try:
        owner_id = int(owner_id_raw)
    except ValueError as exc:
        raise RuntimeError("OWNER_ID must be an integer Telegram user id") from exc

    return BotConfig(
        telegram_bot_token=telegram_bot_token,
        anthropic_api_key=anthropic_api_key,
        anthropic_base_url=anthropic_base_url,
        anthropic_model=anthropic_model,
        bot_log_level=bot_log_level,
        owner_id=owner_id,
        nightly_check_enabled=nightly_check_enabled,
        nightly_check_time=nightly_check_time,
        nightly_check_timezone=nightly_check_timezone,
        nightly_check_retries=nightly_check_retries,
        nightly_check_prompt=nightly_check_prompt,
        auto_punch_enabled=auto_punch_enabled,
        auto_punch_timezone=auto_punch_timezone,
        auto_punch_morning_notify=auto_punch_morning_notify,
        auto_punch_morning_punch=auto_punch_morning_punch,
        auto_punch_evening_notify=auto_punch_evening_notify,
        auto_punch_evening_punch=auto_punch_evening_punch,
        auto_punch_retries=auto_punch_retries,
    )
