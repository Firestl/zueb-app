"""Tests for bot/scheduler/nightly_attendance.py — _split_text 纯函数 + 调度器异步测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from bot.scheduler.nightly_attendance import NightlyAttendanceScheduler, _split_text


# ---------------------------------------------------------------------------
# 本地 helper：构造最小调度器实例
# ---------------------------------------------------------------------------


def _make_scheduler(
    *,
    enabled: bool = True,
    retries: int = 2,
    query_result: str = "考勤已完成，上班卡 07:55，下班卡 17:30。",
    query_error: Exception | None = None,
) -> NightlyAttendanceScheduler:
    """构造带 mock 依赖的最小调度器实例，默认配置 enabled=True，retries=2。"""
    bot = Mock()
    bot.send_message = AsyncMock()

    agent_manager = Mock()
    agent_manager.reset_session = AsyncMock()
    if query_error:
        agent_manager.query = AsyncMock(side_effect=query_error)
    else:
        agent_manager.query = AsyncMock(return_value=query_result)

    return NightlyAttendanceScheduler(
        bot=bot,
        agent_manager=agent_manager,
        owner_id=12345,
        enabled=enabled,
        run_time="22:00",
        timezone_name="Asia/Shanghai",
        retries=retries,
        prompt="检查今日考勤打卡状态，自动打卡。",
    )


# ---------------------------------------------------------------------------
# _split_text — 纯函数测试
# ---------------------------------------------------------------------------


    # _split_text(): 空内容或纯空白应直接忽略，不发送空消息。
def test_split_text_empty() -> None:
    """空字符串（或纯空白）应返回空列表。"""
    assert _split_text("") == []
    assert _split_text("   ") == []


    # _split_text(): 未超长文本保持单段返回。
def test_split_text_short() -> None:
    """不超过限制的文本应作为单元素列表返回。"""
    text = "短消息"
    result = _split_text(text, limit=100)
    assert result == [text]


    # _split_text(): 超长且含换行时，优先按换行切段以保持可读性。
def test_split_text_splits_at_newline() -> None:
    """超过限制时应优先在换行符处拆分，避免截断行中文字。"""
    # 构造恰好需要拆分的文本：两段，每段 60 字符，中间有换行
    first_line = "A" * 60
    second_line = "B" * 60
    text = first_line + "\n" + second_line
    result = _split_text(text, limit=80)
    # 应在换行处拆成两段
    assert len(result) == 2
    assert result[0] == first_line
    assert result[1] == second_line


    # _split_text(): 没有换行可用时退化为按 limit 硬切。
def test_split_text_no_newline_hard_split() -> None:
    """文本无换行且超限时应硬切到 limit 位置。"""
    text = "X" * 200
    result = _split_text(text, limit=100)
    assert len(result) == 2
    assert result[0] == "X" * 100
    assert result[1] == "X" * 100


# ---------------------------------------------------------------------------
# NightlyAttendanceScheduler — 异步测试
# ---------------------------------------------------------------------------


    # NightlyAttendanceScheduler.start(): disabled 配置下不创建后台任务。
@pytest.mark.anyio
async def test_start_disabled_no_task() -> None:
    """enabled=False 时 start() 应直接返回，不创建后台任务。"""
    scheduler = _make_scheduler(enabled=False)

    await scheduler.start()

    assert scheduler._task is None


    # NightlyAttendanceScheduler.start(): 已在运行时重复启动不应生成重复任务。
@pytest.mark.anyio
async def test_start_already_running_no_duplicate() -> None:
    """已有运行中任务时，重复调用 start() 不应创建第二个任务。"""
    loop_gate = asyncio.Event()

    async def _mock_loop() -> None:
        await loop_gate.wait()  # 阻塞直到被显式解除

    scheduler = _make_scheduler(enabled=True)
    scheduler._run_loop = _mock_loop  # type: ignore[method-assign]

    await scheduler.start()
    first_task = scheduler._task
    assert first_task is not None

    await scheduler.start()  # 第二次调用不应替换任务
    assert scheduler._task is first_task

    loop_gate.set()
    await scheduler.stop()


    # NightlyAttendanceScheduler._run_once(): 首次成功时发送成功消息且不触发重试等待。
@pytest.mark.anyio
async def test_run_once_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """首次成功时应发送格式化结果消息并包含考勤内容。"""
    sleep_mock = AsyncMock()
    monkeypatch.setattr("bot.scheduler.nightly_attendance.asyncio.sleep", sleep_mock)

    scheduler = _make_scheduler(query_result="上班卡 07:55，下班卡 17:30")

    await scheduler._run_once()

    # agent 应被调用一次（无重试）
    scheduler._agent_manager.query.assert_called_once()
    # 应发送至少一条消息
    assert scheduler._bot.send_message.call_count >= 1
    # 发送的文本应包含考勤内容
    sent_text = scheduler._bot.send_message.call_args_list[0].kwargs["text"]
    assert "上班卡 07:55" in sent_text
    # 无需重试，sleep 不应被调用
    sleep_mock.assert_not_called()


    # NightlyAttendanceScheduler._run_once(): 首次失败、后续成功时应只经历一次重试等待。
@pytest.mark.anyio
async def test_run_once_retry_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """首次查询失败后重试成功，应只发送成功消息，重试延迟 sleep 应被调用一次。"""
    sleep_mock = AsyncMock()
    monkeypatch.setattr("bot.scheduler.nightly_attendance.asyncio.sleep", sleep_mock)

    call_count = [0]

    async def _query_once_fail(*args, **kwargs) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("WebHR timeout")
        return "打卡完成"

    scheduler = _make_scheduler()
    scheduler._agent_manager.query = _query_once_fail

    await scheduler._run_once()

    assert call_count[0] == 2  # 1 失败 + 1 成功
    sleep_mock.assert_called_once()  # 重试前等待一次
    assert scheduler._bot.send_message.call_count >= 1


    # NightlyAttendanceScheduler._run_once(): 所有尝试失败后发送失败通知。
@pytest.mark.anyio
async def test_run_once_all_retries_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """所有重试均失败后应发送错误通知消息。"""
    sleep_mock = AsyncMock()
    monkeypatch.setattr("bot.scheduler.nightly_attendance.asyncio.sleep", sleep_mock)

    scheduler = _make_scheduler(
        retries=1,  # 共 2 次尝试
        query_error=RuntimeError("persistent error"),
    )

    await scheduler._run_once()

    # 应发送错误通知
    assert scheduler._bot.send_message.call_count >= 1
    sent_text = scheduler._bot.send_message.call_args_list[-1].kwargs["text"]
    assert "失败" in sent_text
    # retries=1 → 1 次重试等待
    assert sleep_mock.call_count == 1


    # NightlyAttendanceScheduler._run_once(): Agent 返回空文本时使用兜底提示语。
@pytest.mark.anyio
async def test_run_once_empty_result_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """query 返回空字符串时应使用兜底提示语 '未获取到结果'。"""
    sleep_mock = AsyncMock()
    monkeypatch.setattr("bot.scheduler.nightly_attendance.asyncio.sleep", sleep_mock)

    scheduler = _make_scheduler(query_result="")

    await scheduler._run_once()

    assert scheduler._bot.send_message.call_count >= 1
    sent_text = scheduler._bot.send_message.call_args_list[0].kwargs["text"]
    assert "未获取到结果" in sent_text
