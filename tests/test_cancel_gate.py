"""Tests for bot/scheduler/cancel_gate.py — 纯异步状态机测试。"""

from __future__ import annotations

import pytest

from bot.scheduler.cancel_gate import CancelGate


# ---------------------------------------------------------------------------
# 同步状态测试
# ---------------------------------------------------------------------------


    # CancelGate.active: 新实例默认未打开取消窗口。
def test_initial_state_not_active() -> None:
    """新建的 CancelGate 初始应为非活跃状态。"""
    gate = CancelGate()
    assert not gate.active


    # CancelGate.open(): 打开窗口后 active 应变为 True。
def test_open_sets_active() -> None:
    """open() 后 active 应变为 True。"""
    gate = CancelGate()
    gate.open("test-label")
    assert gate.active


    # CancelGate.try_cancel(): 未激活时返回 False，且不设置内部事件。
def test_try_cancel_when_not_active() -> None:
    """非活跃时 try_cancel() 应返回 False，不触发 event。"""
    gate = CancelGate()
    result = gate.try_cancel()
    assert result is False
    assert not gate._event.is_set()


    # CancelGate.try_cancel(): 已激活时返回 True，并触发等待中的 event。
def test_try_cancel_when_active() -> None:
    """活跃时 try_cancel() 应返回 True 并设置内部 event。"""
    gate = CancelGate()
    gate.open("cancel-me")
    result = gate.try_cancel()
    assert result is True
    assert gate._event.is_set()


    # CancelGate.close(): 关闭窗口时应重置 active 和 event。
def test_close_resets_state() -> None:
    """close() 后 active 应为 False，event 应被清除。"""
    gate = CancelGate()
    gate.open("close-test")
    gate.try_cancel()
    gate.close()
    assert not gate.active
    assert not gate._event.is_set()


    # CancelGate 生命周期: open -> cancel -> close 的状态流转保持正确。
def test_full_lifecycle_cancel() -> None:
    """open → try_cancel → close 的完整生命周期应按序正确转换状态。"""
    gate = CancelGate()
    gate.open("lifecycle")
    assert gate.active
    result = gate.try_cancel()
    assert result is True
    gate.close()
    assert not gate.active


    # CancelGate.open(): 重新打开窗口时需要清掉上一次取消留下的 event。
def test_reopen_after_close() -> None:
    """close 后再次 open 应重置 event 为未触发状态，允许新一轮等待。"""
    gate = CancelGate()
    gate.open("first")
    gate.try_cancel()  # 设置 event
    gate.close()
    gate.open("second")
    assert gate.active
    # 重新 open 后 event 应被清除，ready for a fresh wait
    assert not gate._event.is_set()


# ---------------------------------------------------------------------------
# 异步 wait_or_timeout 测试
# ---------------------------------------------------------------------------


    # CancelGate.wait_or_timeout(): 事件已触发时立即返回 cancelled=True。
@pytest.mark.anyio
async def test_wait_or_timeout_cancelled() -> None:
    """在超时前通过 try_cancel 预先触发取消，wait_or_timeout 应立即返回 True。"""
    gate = CancelGate()
    gate.open("pre-cancelled")
    gate.try_cancel()  # 预先设置 event，wait_for 会立即解除阻塞
    result = await gate.wait_or_timeout(5.0)
    assert result is True


    # CancelGate.wait_or_timeout(): 无人取消且超时时返回 False。
@pytest.mark.anyio
async def test_wait_or_timeout_elapsed() -> None:
    """超时到期且无人取消时，wait_or_timeout 应返回 False。"""
    gate = CancelGate()
    gate.open("timeout-test")
    result = await gate.wait_or_timeout(0.001)  # 1ms 超时
    assert result is False
