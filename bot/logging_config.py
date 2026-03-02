"""Logging setup for the Telegram bot runtime.

全局日志配置模块，统一设置日志级别和输出格式。
"""

from __future__ import annotations

import logging

_DEFAULT_LOG_LEVEL = "INFO"
# 日志格式：时间 | 级别 | 模块名 | 消息
_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str) -> None:
    """配置全局日志级别和格式。"""
    # 解析日志级别，无效值时回退到 INFO
    level_name = (level or _DEFAULT_LOG_LEVEL).upper().strip()
    log_level = getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)
    root = logging.getLogger()
    root.setLevel(log_level)

    if root.handlers:
        # 已有 handler（如第三方库注册的），直接复用并更新配置
        for handler in root.handlers:
            handler.setLevel(log_level)
            handler.setFormatter(formatter)
    else:
        # 没有 handler 时，创建标准输出 StreamHandler
        handler = logging.StreamHandler()
        handler.setLevel(log_level)
        handler.setFormatter(formatter)
        root.addHandler(handler)

    # 将 Python warnings 模块的告警也纳入日志系统
    logging.captureWarnings(True)
