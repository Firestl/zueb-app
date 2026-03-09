"""Tests for cli/attendance/service.py — 私有 helper 直接测试 + WebHRClient mock。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import ClassVar
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from cli.attendance.service import (
    AttendanceError,
    _attendance_status_from_raw,
    _check_time_window,
    _extract_card_time,
    _is_card_done,
    _normalize_xy,
    _resolve_mode,
    get_attendance_status,
    punch_attendance,
)
from cli.types import AttendanceStatus

_TZ = ZoneInfo("Asia/Shanghai")


# ---------------------------------------------------------------------------
# 本地 helper
# ---------------------------------------------------------------------------


def _make_status(
    *,
    sbk_done: bool = False,
    xbk_done: bool = False,
) -> AttendanceStatus:
    """构造测试用 AttendanceStatus 字典。"""
    return {
        "sbk_time": "08:30" if sbk_done else "",
        "xbk_time": "17:30" if xbk_done else "",
        "sbk_done": sbk_done,
        "xbk_done": xbk_done,
        "all_done": sbk_done and xbk_done,
    }


# datetime.now() 模拟类（与 test_scheduler_utils 同模式）
class _FakeDatetime(datetime):
    """用于 monkeypatch 的 datetime 子类，仅覆盖 now()。"""

    _fixed: ClassVar[datetime]

    def __new__(cls, fixed_now: datetime):  # type: ignore[override]
        instance = super().__new__(cls, 2000, 1, 1)
        return instance

    def __init__(self, fixed_now: datetime) -> None:
        self._fixed_now = fixed_now

    def now(self, tz=None):  # noqa: ANN001
        """返回预设的固定时间。"""
        return self._fixed_now


# 默认 WebHR API 响应（sbk 已打，xbk 未打）
_DEFAULT_KQCARD = {
    "data": {
        "data": {
            "sbk": ["上班时间", "08:30"],
            "xbk": "无",
        }
    }
}


def _mock_webhr_flow(
    monkeypatch: pytest.MonkeyPatch,
    *,
    kqcard_response: object | None = None,
    save_response: object | None = None,
    user_code: str = "E12345",
    md5str: str = "abc123",
    webhrtoken: str = "wt-test",
) -> Mock:
    """一站式 mock：get_sso_credentials + generate_signature + WebHRClient。"""
    monkeypatch.setattr(
        "cli.attendance.service.get_sso_credentials",
        Mock(return_value={"user_code": user_code, "md5str": md5str}),
    )
    monkeypatch.setattr(
        "cli.attendance.service.generate_signature",
        Mock(return_value={"sign": "base64sig", "timestamp": 1000}),
    )

    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client.get_webhrtoken = Mock(return_value=webhrtoken)
    mock_client.get_kqcard_info = Mock(
        return_value=kqcard_response if kqcard_response is not None else _DEFAULT_KQCARD
    )
    mock_client.save_kqcard = Mock(
        return_value=save_response if save_response is not None else {"message": "打卡成功"}
    )

    monkeypatch.setattr(
        "cli.attendance.service.WebHRClient", Mock(return_value=mock_client)
    )
    return mock_client


# ---------------------------------------------------------------------------
# _extract_card_time — 纯函数
# ---------------------------------------------------------------------------


    # _extract_card_time(): 标准 [label, HH:MM] 卡片字段应提取时间值。
def test_extract_card_time_valid_list() -> None:
    """两元素列表 [label, 'HH:MM'] 应返回时间字符串。"""
    assert _extract_card_time(["上班时间", "08:30"]) == "08:30"


    # _extract_card_time(): 长度不足 2 的列表按未打卡处理，返回空字符串。
def test_extract_card_time_short_list() -> None:
    """长度不足 2 的列表应返回空字符串，不抛出 IndexError。"""
    assert _extract_card_time(["仅标签"]) == ""


    # _extract_card_time(): 非 list 类型不参与解析，直接返回空字符串。
def test_extract_card_time_non_list() -> None:
    """非列表类型（如 '无' 字符串）应返回空字符串。"""
    assert _extract_card_time("无") == ""


    # _extract_card_time(): None 输入也应安全回退为空字符串。
def test_extract_card_time_none() -> None:
    """None 值应返回空字符串，不抛出 TypeError。"""
    assert _extract_card_time(None) == ""


# ---------------------------------------------------------------------------
# _is_card_done — 纯函数
# ---------------------------------------------------------------------------


    # _is_card_done(): 合法时间字符串表示该卡已完成。
def test_is_card_done_valid_time() -> None:
    """非空且非 '无' 的时间字符串表示已打卡，应返回 True。"""
    assert _is_card_done("08:30") is True


    # _is_card_done(): 空字符串表示未打卡。
def test_is_card_done_empty_string() -> None:
    """空字符串表示未打卡，应返回 False。"""
    assert _is_card_done("") is False


    # _is_card_done(): 服务器特殊标志“无”同样表示未打卡。
def test_is_card_done_wu_string() -> None:
    """'无' 字符串是未打卡的标志值，应返回 False。"""
    assert _is_card_done("无") is False


# ---------------------------------------------------------------------------
# _attendance_status_from_raw — 纯函数
# ---------------------------------------------------------------------------


    # _attendance_status_from_raw(): 正常响应能被解析成完整 AttendanceStatus。
def test_status_from_raw_valid() -> None:
    """正确嵌套的响应 dict 应解析为完整 AttendanceStatus。"""
    raw = {
        "data": {
            "data": {
                "sbk": ["上班", "07:55"],
                "xbk": ["下班", "17:30"],
            }
        }
    }
    status = _attendance_status_from_raw(raw)
    assert status["sbk_time"] == "07:55"
    assert status["xbk_time"] == "17:30"
    assert status["sbk_done"] is True
    assert status["xbk_done"] is True
    assert status["all_done"] is True


    # _attendance_status_from_raw(): 非 dict payload 属于协议错误。
def test_status_from_raw_non_dict_raises() -> None:
    """非 dict 输入（如列表）应抛出 AttendanceError。"""
    with pytest.raises(AttendanceError, match="payload must be an object"):
        _attendance_status_from_raw([1, 2, 3])


    # _attendance_status_from_raw(): 缺少 data.data 嵌套层级时拒绝解析。
def test_status_from_raw_missing_data_raises() -> None:
    """缺少 data.data 层级时应抛出 AttendanceError。"""
    with pytest.raises(AttendanceError, match="missing data.data"):
        _attendance_status_from_raw({"data": {"other": "value"}})


# ---------------------------------------------------------------------------
# _normalize_xy — 纯函数（含环境变量读取）
# ---------------------------------------------------------------------------


    # _normalize_xy(): 直接传入合法坐标时仅做规范化返回。
def test_normalize_xy_direct_value() -> None:
    """直接提供合法坐标字符串时应原样返回（去除多余空格）。"""
    result = _normalize_xy("116.3975,39.9087")
    assert result == "116.3975,39.9087"


    # _normalize_xy(): 未显式传参时可从默认环境变量读取坐标。
def test_normalize_xy_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """xy=None 时应从 ZUEB_ATTENDANCE_DEFAULT_XY 环境变量读取。"""
    monkeypatch.setenv("ZUEB_ATTENDANCE_DEFAULT_XY", "121.4737,31.2304")
    result = _normalize_xy(None)
    assert result == "121.4737,31.2304"


    # _normalize_xy(): 既无显式坐标又无环境变量时，应抛出必填错误。
def test_normalize_xy_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """xy=None 且环境变量未设置时应抛出 AttendanceError。"""
    monkeypatch.delenv("ZUEB_ATTENDANCE_DEFAULT_XY", raising=False)
    with pytest.raises(AttendanceError, match="coordinates are required"):
        _normalize_xy(None)


    # _normalize_xy(): 缺少 lng,lat 分隔格式时，应触发格式校验错误。
def test_normalize_xy_wrong_format_raises() -> None:
    """缺少逗号分隔符的坐标字符串应抛出 AttendanceError。"""
    with pytest.raises(AttendanceError, match="lng,lat"):
        _normalize_xy("116.39759087")  # 无逗号


    # _normalize_xy(): 坐标必须可解析为数字。
def test_normalize_xy_non_numeric_raises() -> None:
    """非数字坐标值应抛出 AttendanceError。"""
    with pytest.raises(AttendanceError, match="valid numbers"):
        _normalize_xy("abc,def")


# ---------------------------------------------------------------------------
# _check_time_window — 需要 datetime.now mock
# ---------------------------------------------------------------------------


    # _check_time_window(): 上班卡在 08:00 前允许提交。
def test_check_sbk_before_eight_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """07:30 时提交上班卡不超过 08:00 截止，不应抛出异常。"""
    fake_now = datetime(2026, 3, 9, 7, 30, 0, tzinfo=_TZ)
    monkeypatch.setattr("cli.attendance.service.datetime", _FakeDatetime(fake_now))

    _check_time_window("sbk")  # 不应抛出


    # _check_time_window(): 上班卡超过 08:00 后拒绝提交。
def test_check_sbk_after_eight_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """08:30 时提交上班卡已超过截止，应抛出 AttendanceError。"""
    fake_now = datetime(2026, 3, 9, 8, 30, 0, tzinfo=_TZ)
    monkeypatch.setattr("cli.attendance.service.datetime", _FakeDatetime(fake_now))

    with pytest.raises(AttendanceError, match="上班卡仅允许 08:00 前"):
        _check_time_window("sbk")


    # _check_time_window(): 下班卡在 16:30 之后允许提交。
def test_check_xbk_after_sixteen_thirty_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """17:00 时提交下班卡已过 16:30 起打窗口，不应抛出异常。"""
    fake_now = datetime(2026, 3, 9, 17, 0, 0, tzinfo=_TZ)
    monkeypatch.setattr("cli.attendance.service.datetime", _FakeDatetime(fake_now))

    _check_time_window("xbk")  # 不应抛出


    # _check_time_window(): 下班卡早于 16:30 时拒绝提交。
def test_check_xbk_before_sixteen_thirty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """16:00 时提交下班卡未到 16:30 打卡窗口，应抛出 AttendanceError。"""
    fake_now = datetime(2026, 3, 9, 16, 0, 0, tzinfo=_TZ)
    monkeypatch.setattr("cli.attendance.service.datetime", _FakeDatetime(fake_now))

    with pytest.raises(AttendanceError, match="下班卡仅允许 16:30 后"):
        _check_time_window("xbk")


# ---------------------------------------------------------------------------
# _resolve_mode — 纯函数
# ---------------------------------------------------------------------------


    # _resolve_mode(): auto 且上班卡未打时优先选择 sbk。
def test_resolve_auto_sbk_not_done() -> None:
    """auto 模式且上班卡未打时应自动选择 'sbk'。"""
    mode, _ = _resolve_mode("auto", _make_status(sbk_done=False, xbk_done=False))
    assert mode == "sbk"


    # _resolve_mode(): auto 且仅缺下班卡时切换到 xbk。
def test_resolve_auto_xbk_not_done() -> None:
    """auto 模式且上班卡已打、下班卡未打时应自动选择 'xbk'。"""
    mode, _ = _resolve_mode("auto", _make_status(sbk_done=True, xbk_done=False))
    assert mode == "xbk"


    # _resolve_mode(): auto 且两卡已完成时返回 no-op。
def test_resolve_auto_all_done() -> None:
    """auto 模式且两卡均已打时应返回 None（无需打卡）。"""
    mode, msg = _resolve_mode("auto", _make_status(sbk_done=True, xbk_done=True))
    assert mode is None
    assert "无需" in msg


    # _resolve_mode(): 显式请求已完成的 sbk 时避免重复打卡。
def test_resolve_explicit_sbk_done() -> None:
    """显式 'sbk' 但上班卡已打时应返回 None（避免重复打卡）。"""
    mode, msg = _resolve_mode("sbk", _make_status(sbk_done=True))
    assert mode is None
    assert "已完成" in msg


    # _resolve_mode(): 显式请求未完成的 xbk 时直接执行 xbk。
def test_resolve_explicit_xbk_not_done() -> None:
    """显式 'xbk' 且下班卡未打时应返回 'xbk'。"""
    mode, _ = _resolve_mode("xbk", _make_status(sbk_done=True, xbk_done=False))
    assert mode == "xbk"


# ---------------------------------------------------------------------------
# 公共函数：get_attendance_status
# ---------------------------------------------------------------------------


    # get_attendance_status(): 成功走完认证和查询流程后返回解析后的状态。
def test_get_status_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常流程应返回包含 sbk/xbk 状态的 AttendanceStatus。"""
    mock_client = _mock_webhr_flow(monkeypatch)

    status = get_attendance_status("valid-jwt")

    assert status["sbk_time"] == "08:30"
    assert status["sbk_done"] is True
    assert status["xbk_done"] is False
    mock_client.get_webhrtoken.assert_called_once()
    mock_client.get_kqcard_info.assert_called_once()


# ---------------------------------------------------------------------------
# 公共函数：punch_attendance
# ---------------------------------------------------------------------------


    # punch_attendance(): auto 模式下若当天已全部完成，应短路返回且不提交。
def test_punch_auto_all_done_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """auto 模式且今日已全部打卡时，punch_attendance 应返回 executed=False，不调用 save_kqcard。"""
    all_done_response = {
        "data": {
            "data": {
                "sbk": ["上班", "07:55"],
                "xbk": ["下班", "17:30"],
            }
        }
    }
    mock_client = _mock_webhr_flow(monkeypatch, kqcard_response=all_done_response)

    result = punch_attendance("jwt", mode="auto", xy="116.3975,39.9087")

    assert result["executed"] is False
    assert result["mode_executed"] is None
    assert "无需" in result["message"]
    mock_client.save_kqcard.assert_not_called()
