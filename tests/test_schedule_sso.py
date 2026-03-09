"""Tests for cli/schedule/sso.py — httpx.Client mock 隔离测试（两步 CAS SSO 流程）。"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from cli.schedule.sso import SSOError, get_jwxt_session


# ---------------------------------------------------------------------------
# 本地 helper：构造 httpx.Client 上下文管理器替身
# ---------------------------------------------------------------------------


def _make_response(
    *,
    status_code: int = 200,
    location: str | None = None,
    jsessionid: str | None = None,
) -> Mock:
    """构造最小 httpx.Response 替身，支持设置状态码、Location 头和 JSESSIONID cookie。"""
    resp = Mock()
    resp.status_code = status_code
    resp.headers = {"Location": location} if location else {}
    resp.cookies = Mock()
    resp.cookies.get = Mock(return_value=jsessionid)
    return resp


def _setup_client(
    monkeypatch: pytest.MonkeyPatch,
    responses: list,  # list of Mock responses or exceptions
) -> Mock:
    """设置 httpx.Client 上下文管理器，按顺序返回/抛出 responses 列表中的值。"""
    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client.get = Mock(side_effect=responses)

    monkeypatch.setattr(
        "cli.schedule.sso.httpx.Client", Mock(return_value=mock_client)
    )
    return mock_client


# 带 ticket 的合法 CAS redirect URL
_CAS_LOCATION = (
    "https://jwxt.zueb.edu.cn/jxcjcaslogin?ticket=ST-12345&url=h5/index.html"
)


# ---------------------------------------------------------------------------
# get_jwxt_session — 集成测试
# ---------------------------------------------------------------------------


    # get_jwxt_session(): 标准 CAS -> JWXT 两步流程成功返回 JSESSIONID。
def test_happy_path_returns_jsessionid(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常两步 SSO 流程应返回 JWXT JSESSIONID cookie 值。"""
    cas_resp = _make_response(status_code=302, location=_CAS_LOCATION)
    jwxt_resp = _make_response(status_code=200, jsessionid="SESS-ABC123")
    _setup_client(monkeypatch, [cas_resp, jwxt_resp])

    result = get_jwxt_session("valid-jwt")

    assert result == "SESS-ABC123"


    # get_jwxt_session(): CAS 未返回 302/303 时，应判定登录流程失败。
def test_cas_non_302_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """CAS 返回非 302/303 状态码时应抛出 SSOError。"""
    cas_resp = _make_response(status_code=200)
    _setup_client(monkeypatch, [cas_resp])

    with pytest.raises(SSOError, match="CAS login failed"):
        get_jwxt_session("token")


    # get_jwxt_session(): CAS 重定向缺少 Location 头时，无法继续票据交换。
def test_cas_302_no_location_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """CAS 返回 302 但无 Location 头时应抛出 SSOError。"""
    cas_resp = _make_response(status_code=302)  # no location
    _setup_client(monkeypatch, [cas_resp])

    with pytest.raises(SSOError, match="CAS did not return redirect location"):
        get_jwxt_session("token")


    # get_jwxt_session(): CAS redirect URL 没有 ticket 参数时，应拒绝继续。
def test_cas_location_no_ticket_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """CAS Location URL 中无 ticket 参数时应抛出 SSOError。"""
    cas_resp = _make_response(
        status_code=302,
        location="https://jwxt.zueb.edu.cn/jxcjcaslogin?url=h5/index.html",
        # 刻意省略 ticket= 参数
    )
    _setup_client(monkeypatch, [cas_resp])

    with pytest.raises(SSOError, match="No ticket in CAS redirect"):
        get_jwxt_session("token")


    # get_jwxt_session(): 第二跳 JWXT 验票请求网络失败时包装为 SSOError。
def test_jwxt_request_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """JWXT ticket 验证请求失败时应抛出 SSOError。"""
    import httpx

    cas_resp = _make_response(status_code=302, location=_CAS_LOCATION)
    jwxt_error = httpx.RequestError("JWXT unreachable")
    _setup_client(monkeypatch, [cas_resp, jwxt_error])

    with pytest.raises(SSOError, match="JWXT ticket validation failed"):
        get_jwxt_session("token")


    # get_jwxt_session(): JWXT 成功响应但未设置 JSESSIONID 也属于协议失败。
def test_jwxt_no_jsessionid_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """JWXT 响应缺少 JSESSIONID cookie 时应抛出 SSOError。"""
    cas_resp = _make_response(status_code=302, location=_CAS_LOCATION)
    jwxt_resp = _make_response(status_code=200)  # jsessionid=None
    _setup_client(monkeypatch, [cas_resp, jwxt_resp])

    with pytest.raises(SSOError, match="JWXT did not return JSESSIONID"):
        get_jwxt_session("token")


    # get_jwxt_session(): 第一跳 CAS 请求网络异常时需包装成统一错误。
def test_cas_request_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """CAS 初始请求网络错误时应包装为 SSOError。"""
    import httpx

    cas_error = httpx.RequestError("CAS unreachable")
    _setup_client(monkeypatch, [cas_error])

    with pytest.raises(SSOError, match="CAS login request failed"):
        get_jwxt_session("token")
