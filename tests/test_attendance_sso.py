"""Tests for cli/attendance/sso.py — httpx.Client mock 隔离测试。"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from cli.attendance.sso import SSOError, _extract_query_value, get_sso_credentials


# ---------------------------------------------------------------------------
# 本地 helper：构造 httpx.Client 上下文管理器替身
# ---------------------------------------------------------------------------


def _mock_httpx_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    final_url: str = "",
    http_error: Exception | None = None,
) -> Mock:
    """构造 httpx.Client 上下文管理器替身，控制最终重定向 URL 或触发 HTTP 错误。"""
    mock_resp = Mock()
    mock_resp.url = final_url
    if http_error is not None:
        mock_resp.raise_for_status = Mock(side_effect=http_error)
    else:
        mock_resp.raise_for_status = Mock(return_value=None)

    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client.get = Mock(return_value=mock_resp)

    monkeypatch.setattr(
        "cli.attendance.sso.httpx.Client", Mock(return_value=mock_client)
    )
    return mock_client


# ---------------------------------------------------------------------------
# _extract_query_value — 纯函数测试
# ---------------------------------------------------------------------------


    # _extract_query_value(): key 存在且有值时，返回首个 query value。
def test_extract_query_value_present() -> None:
    """key 存在时应返回列表中的第一个值。"""
    result = _extract_query_value({"key": ["val1", "val2"]}, "key")
    assert result == "val1"


    # _extract_query_value(): key 缺失时，安全返回空字符串。
def test_extract_query_value_absent() -> None:
    """key 不存在时应返回空字符串，不抛出 KeyError。"""
    result = _extract_query_value({}, "missing")
    assert result == ""


    # _extract_query_value(): key 对应空列表时，避免 IndexError 并返回空字符串。
def test_extract_query_value_empty_list() -> None:
    """key 存在但值列表为空时应返回空字符串，不抛出 IndexError。"""
    result = _extract_query_value({"key": []}, "key")
    assert result == ""


# ---------------------------------------------------------------------------
# get_sso_credentials — 集成测试（mock httpx）
# ---------------------------------------------------------------------------


    # get_sso_credentials(): 成功跟随重定向并从最终 URL 提取 userCode/md5Str。
def test_sso_credentials_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常流程：final URL 含 userCode 与 md5Str → 返回正确凭证字典。"""
    _mock_httpx_client(
        monkeypatch,
        final_url="https://rsxt1.zueb.edu.cn/webhrApp/index?userCode=E12345&md5Str=abc123",
    )

    creds = get_sso_credentials("valid-token")

    assert creds["user_code"] == "E12345"
    assert creds["md5str"] == "abc123"


    # get_sso_credentials(): 空 token 应在请求前被参数校验拒绝。
def test_sso_credentials_empty_token_raises() -> None:
    """空 id_token 应在发起 HTTP 请求前立即抛出 SSOError。"""
    with pytest.raises(SSOError, match="id_token is required"):
        get_sso_credentials("")


    # get_sso_credentials(): HTTP 层异常需要包装成统一的 SSOError。
def test_sso_credentials_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 请求失败（raise_for_status 抛出异常）时应包装为 SSOError。"""
    import httpx

    _mock_httpx_client(
        monkeypatch,
        http_error=httpx.HTTPError("connection refused"),
    )

    with pytest.raises(SSOError, match="SSO redirect request failed"):
        get_sso_credentials("some-token")


    # get_sso_credentials(): 最终 URL 缺少关键 query 参数时应报协议错误。
def test_sso_credentials_missing_user_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """final URL 缺少 userCode 参数时应抛出 SSOError，提示字段缺失。"""
    _mock_httpx_client(
        monkeypatch,
        # 仅含 md5Str，缺少 userCode
        final_url="https://rsxt1.zueb.edu.cn/webhrApp/index?md5Str=abc123",
    )

    with pytest.raises(SSOError, match="userCode/md5Str not found"):
        get_sso_credentials("some-token")
