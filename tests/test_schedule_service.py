"""Tests for cli/schedule/service.py — JWT 纯函数直接测试 + JWXTClient mock。"""

from __future__ import annotations

import base64
import json
from unittest.mock import Mock

import pytest

from cli.schedule.service import (
    ScheduleError,
    _decode_token_payload,
    _extract_login_id_from_token,
    _extract_user_type_from_token,
    get_available_semesters,
    get_schedule,
)


# ---------------------------------------------------------------------------
# 本地 helper：构造测试 JWT 和 JWXTClient 替身
# ---------------------------------------------------------------------------


def _make_jwt(payload: dict) -> str:
    """构造 header.payload.signature 格式的测试 JWT（无真实签名）。"""
    header_b64 = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    )
    return f"{header_b64}.{payload_b64}.fakesig"


def _make_jwxt_client(**method_overrides: object) -> Mock:
    """构造可控的 JWXTClient 上下文管理器替身，默认返回空学期列表。"""
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)

    client.get_semester_items = Mock(return_value=[])
    client.get_course_schedule = Mock(
        return_value={"xn": "2025", "xq": "1", "zc": "3", "maxzc": "20"}
    )
    client.resolve_semester_code = Mock(return_value="20250")

    for method, value in method_overrides.items():
        if isinstance(value, Exception):
            getattr(client, method).side_effect = value
        else:
            getattr(client, method).return_value = value

    return client


def _patch_jwxt(
    monkeypatch: pytest.MonkeyPatch,
    client: Mock,
    *,
    jsessionid: str = "SESS-TEST",
    sso_error: Exception | None = None,
) -> None:
    """一站式 patch get_jwxt_session 和 JWXTClient。"""
    if sso_error:
        monkeypatch.setattr(
            "cli.schedule.service.get_jwxt_session", Mock(side_effect=sso_error)
        )
    else:
        monkeypatch.setattr(
            "cli.schedule.service.get_jwxt_session", Mock(return_value=jsessionid)
        )
    monkeypatch.setattr("cli.schedule.service.JWXTClient", Mock(return_value=client))


# ---------------------------------------------------------------------------
# _decode_token_payload — 纯函数测试
# ---------------------------------------------------------------------------


    # _decode_token_payload(): 合法 JWT payload 能被成功解码为 dict。
def test_decode_token_payload_valid_jwt() -> None:
    """合法 JWT 应正确解码出 payload dict。"""
    token = _make_jwt({"sub": "user123", "name": "Alice"})
    result = _decode_token_payload(token)
    assert result["sub"] == "user123"
    assert result["name"] == "Alice"


    # _decode_token_payload(): 非 JWT 格式输入应安全回退为空字典。
def test_decode_token_payload_no_dots() -> None:
    """无点号分隔符的字符串（非 JWT 格式）应返回空字典。"""
    result = _decode_token_payload("nodots")
    assert result == {}


    # _decode_token_payload(): base64 损坏时不抛异常，直接返回空字典。
def test_decode_token_payload_bad_base64() -> None:
    """base64 部分损坏时应安全返回空字典，不抛出异常。"""
    result = _decode_token_payload("header.!!!invalid_base64!!!.sig")
    assert result == {}


    # _decode_token_payload(): payload 不是 JSON object 时也返回空字典。
def test_decode_token_payload_non_dict() -> None:
    """payload 解码结果不是 dict 时（如 JSON 数组）应返回空字典。"""
    arr_b64 = base64.urlsafe_b64encode(b"[1, 2, 3]").rstrip(b"=").decode()
    token = f"header.{arr_b64}.sig"
    result = _decode_token_payload(token)
    assert result == {}


# ---------------------------------------------------------------------------
# _extract_login_id_from_token — 纯函数测试
# ---------------------------------------------------------------------------


    # _extract_login_id_from_token(): 优先使用 ATTR_userNo 作为登录标识。
def test_extract_login_id_attr_user_no() -> None:
    """ATTR_userNo 字段存在时应优先使用它作为 login_id。"""
    token = _make_jwt({"ATTR_userNo": "20230001", "sub": "other"})
    result = _extract_login_id_from_token(token)
    assert result == "20230001"


    # _extract_login_id_from_token(): 缺少 ATTR_userNo 时回退到 sub。
def test_extract_login_id_sub_fallback() -> None:
    """ATTR_userNo 缺失时应回退到 sub 字段。"""
    token = _make_jwt({"sub": "staff-xyz"})
    result = _extract_login_id_from_token(token)
    assert result == "staff-xyz"


    # _extract_login_id_from_token(): 无法解析 token 时返回空字符串。
def test_extract_login_id_empty_payload() -> None:
    """无法解析 token（格式错误）时应返回空字符串。"""
    result = _extract_login_id_from_token("invalid-token-no-dots")
    assert result == ""


# ---------------------------------------------------------------------------
# _extract_user_type_from_token — 纯函数测试
# ---------------------------------------------------------------------------


    # _extract_user_type_from_token(): 直接 usertype 命中已知类型时原样返回。
def test_extract_user_type_direct() -> None:
    """直接 usertype 字段为已知类型时应直接返回。"""
    token = _make_jwt({"usertype": "STU"})
    result = _extract_user_type_from_token(token)
    assert result == "STU"


    # _extract_user_type_from_token(): 身份编码以 T 开头时识别为教师。
def test_extract_user_type_code_prefix_t() -> None:
    """ATTR_identityTypeCode 以 T 开头时应返回 'TEA'。"""
    token = _make_jwt({"ATTR_identityTypeCode": "TEACHER01"})
    result = _extract_user_type_from_token(token)
    assert result == "TEA"


    # _extract_user_type_from_token(): 身份编码以 S 开头时识别为学生。
def test_extract_user_type_code_prefix_s() -> None:
    """ATTR_identityTypeCode 以 S 开头时应返回 'STU'。"""
    token = _make_jwt({"ATTR_identityTypeCode": "STUDENT"})
    result = _extract_user_type_from_token(token)
    assert result == "STU"


    # _extract_user_type_from_token(): 身份名称含“教/职工”时识别为教师。
def test_extract_user_type_name_teacher() -> None:
    """ATTR_identityTypeName 含 '教' 字时应返回 'TEA'。"""
    token = _make_jwt({"ATTR_identityTypeName": "教职工"})
    result = _extract_user_type_from_token(token)
    assert result == "TEA"


    # _extract_user_type_from_token(): 身份名称含“学”时识别为学生。
def test_extract_user_type_name_student() -> None:
    """ATTR_identityTypeName 含 '学' 字时应返回 'STU'。"""
    token = _make_jwt({"ATTR_identityTypeName": "学生"})
    result = _extract_user_type_from_token(token)
    assert result == "STU"


    # _extract_user_type_from_token(): 所有线索都无法识别时返回空字符串。
def test_extract_user_type_unrecognized() -> None:
    """无法识别的类型字段时应返回空字符串。"""
    token = _make_jwt({"ATTR_identityTypeCode": "UNKNOWN"})
    result = _extract_user_type_from_token(token)
    assert result == ""


# ---------------------------------------------------------------------------
# get_available_semesters — 集成测试（mock JWXTClient）
# ---------------------------------------------------------------------------


    # get_available_semesters(): 标准成功路径，直接返回 JWXTClient 学期列表。
def test_get_semesters_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常流程应返回学期列表（来自 get_semester_items）。"""
    semesters = [{"dm": "20250", "mc": "2025-2026第一学期"}]
    client = _make_jwxt_client(get_semester_items=semesters)
    _patch_jwxt(monkeypatch, client)

    result = get_available_semesters("valid-jwt")

    assert result == semesters
    client.get_semester_items.assert_called_once()


    # get_available_semesters(): SSO 建连失败时应抛出统一的 ScheduleError。
def test_get_semesters_sso_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """SSO 认证失败时应抛出 ScheduleError。"""
    from cli.schedule.sso import SSOError

    client = _make_jwxt_client()
    _patch_jwxt(monkeypatch, client, sso_error=SSOError("CAS timeout"))

    with pytest.raises(ScheduleError, match="SSO authentication failed"):
        get_available_semesters("token")


# ---------------------------------------------------------------------------
# get_schedule — 集成测试（mock JWXTClient）
# ---------------------------------------------------------------------------


    # get_schedule(): semester_code 与 year/term 互斥，参数冲突时立即失败。
def test_get_schedule_semester_and_year_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """同时提供 semester_code 和 year+term 时应抛出 ScheduleError（互斥参数）。"""
    client = _make_jwxt_client()
    _patch_jwxt(monkeypatch, client)

    with pytest.raises(ScheduleError, match="semester_code or year\\+term"):
        get_schedule("jwt", semester_code="20250", year=2025, term=1)


    # get_schedule(): year/term 必须成对出现，缺一个都属于参数错误。
def test_get_schedule_year_without_term_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """只提供 year 不提供 term 时应抛出 ScheduleError（需成对提供）。"""
    client = _make_jwxt_client()
    _patch_jwxt(monkeypatch, client)

    with pytest.raises(ScheduleError, match="year and term must be provided together"):
        get_schedule("jwt", year=2025)


    # get_schedule(): 默认模式下调用当前学期/当前周查询。
def test_get_schedule_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """无参数时应调用默认查询（当前学期当前周），返回 ScheduleData。"""
    expected = {"xn": "2025", "xq": "1", "zc": "3", "maxzc": "20"}
    client = _make_jwxt_client(get_course_schedule=expected)
    _patch_jwxt(monkeypatch, client)

    result = get_schedule("valid-jwt")

    assert result == expected
    client.get_course_schedule.assert_called_once_with(semester_code=None)


    # get_schedule(): 显式 week 且未越界时，返回对应周课表。
def test_get_schedule_explicit_week_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    """合法 week 参数（不超过 maxzc）时应返回该周的课表数据。"""
    week_data = {"xn": "2025", "xq": "1", "zc": "3", "maxzc": "20"}
    client = _make_jwxt_client(get_course_schedule=week_data)
    _patch_jwxt(monkeypatch, client)

    result = get_schedule("jwt", week=3)

    assert result["zc"] == "3"


    # get_schedule(): 显式 week 超过 maxzc 时，触发周数范围校验错误。
def test_get_schedule_week_exceeds_maxzc(monkeypatch: pytest.MonkeyPatch) -> None:
    """week > maxzc 时应抛出 ScheduleError（超出学期周数范围）。"""
    week_data = {"xn": "2025", "xq": "1", "zc": "21", "maxzc": "20"}
    client = _make_jwxt_client(get_course_schedule=week_data)
    _patch_jwxt(monkeypatch, client)

    with pytest.raises(ScheduleError, match="week 21 out of range"):
        get_schedule("jwt", week=21)
