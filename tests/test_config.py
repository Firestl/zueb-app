from __future__ import annotations

import logging
import os

import pytest
from bot.config import BotConfig, load_config, log_runtime_config


def _env(**overrides: str) -> dict[str, str]:
    """生成 load_config() 测试所需的基础环境变量集合。"""
    # 提供 load_config() 的最小必需环境，再由各测试覆盖关心的配置项。
    env = {
        "TELEGRAM_BOT_TOKEN": "bot-token",
        "ANTHROPIC_API_KEY": "api-key",
        "OWNER_ID": "123456",
    }
    env.update(overrides)
    return env


def test_load_config_accepts_valid_auto_punch_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    """测试合法的自动打卡时间边界可以顺利通过配置校验。"""
    # 正例：早卡 < 08:00，晚卡 >= 16:30，且通知时间早于打卡时间。
    monkeypatch.setattr(os, "environ", _env(
        AUTO_PUNCH_MORNING_NOTIFY="07:50",
        AUTO_PUNCH_MORNING_PUNCH="07:59",
        AUTO_PUNCH_EVENING_NOTIFY="16:20",
        AUTO_PUNCH_EVENING_PUNCH="16:30",
    ).copy())

    config = load_config()

    assert config.auto_punch_morning_punch == "07:59"
    assert config.auto_punch_evening_punch == "16:30"


def test_load_config_rejects_morning_punch_at_or_after_eight(monkeypatch: pytest.MonkeyPatch) -> None:
    """测试早卡时间到 08:00 或更晚时会被配置校验拒绝。"""
    # 反例：早卡到 08:00 及以后，启动阶段就应报错。
    monkeypatch.setattr(os, "environ", _env(AUTO_PUNCH_MORNING_PUNCH="08:00").copy())

    with pytest.raises(
        RuntimeError,
        match=r"AUTO_PUNCH_MORNING_PUNCH \(08:00\) must be earlier than 08:00",
    ):
        load_config()


def test_load_config_rejects_evening_punch_before_sixteen_thirty(monkeypatch: pytest.MonkeyPatch) -> None:
    """测试晚卡时间早于 16:30 时会被配置校验拒绝。"""
    # 反例：晚卡早于 16:30，启动阶段就应报错。
    monkeypatch.setattr(os, "environ", _env(
        AUTO_PUNCH_EVENING_NOTIFY="16:20",
        AUTO_PUNCH_EVENING_PUNCH="16:29",
    ).copy())

    with pytest.raises(
        RuntimeError,
        match=r"AUTO_PUNCH_EVENING_PUNCH \(16:29\) must be at or after 16:30",
    ):
        load_config()


def test_load_config_still_requires_notify_before_punch(monkeypatch: pytest.MonkeyPatch) -> None:
    """测试提醒时间必须早于打卡时间的旧规则仍然生效。"""
    # 回归：新增时间窗口校验后，原有的“提醒时间必须早于打卡时间”规则仍需保留。
    monkeypatch.setattr(os, "environ", _env(
        AUTO_PUNCH_MORNING_NOTIFY="07:55",
        AUTO_PUNCH_MORNING_PUNCH="07:54",
    ).copy())

    with pytest.raises(
        RuntimeError,
        match=r"AUTO_PUNCH_MORNING_NOTIFY \(07:55\) must be earlier than AUTO_PUNCH_MORNING_PUNCH \(07:54\)",
    ):
        load_config()


def test_log_runtime_config_emits_sanitized_summary(caplog: pytest.LogCaptureFixture) -> None:
    """测试启动配置摘要日志包含关键开关，但不会泄露敏感字段。"""
    config = BotConfig(
        telegram_bot_token="bot-token",
        anthropic_api_key="api-key",
        anthropic_base_url=None,
        anthropic_model=None,
        bot_log_level="INFO",
        owner_id=123456,
        nightly_check_enabled=True,
        nightly_check_time="22:00",
        nightly_check_timezone="Asia/Shanghai",
        nightly_check_retries=2,
        nightly_check_prompt="查看是否打卡",
        auto_punch_enabled=False,
        auto_punch_timezone="Asia/Shanghai",
        auto_punch_morning_notify="07:52",
        auto_punch_morning_punch="07:55",
        auto_punch_evening_notify="17:57",
        auto_punch_evening_punch="18:00",
        auto_punch_retries=1,
    )

    with caplog.at_level(logging.INFO):
        log_runtime_config(config)

    assert "Runtime config loaded" in caplog.text
    assert "Nightly check config: enabled=True time=22:00 timezone=Asia/Shanghai retries=2" in caplog.text
    assert "Auto punch config: enabled=False timezone=Asia/Shanghai morning_notify=07:52 morning_punch=07:55 evening_notify=17:57 evening_punch=18:00 retries=1" in caplog.text
    assert "Auto punch is disabled by config (AUTO_PUNCH_ENABLED=false)" in caplog.text
    assert "bot-token" not in caplog.text
    assert "api-key" not in caplog.text
