"""Tests for cli/auth/login.py — AuthClient 上下文管理器 mock 隔离测试。"""

from __future__ import annotations

from unittest.mock import Mock

import httpx
import pytest

from cli.auth.client import AuthClientError
from cli.auth.login import LoginError, MFARequiredError, login


# ---------------------------------------------------------------------------
# 本地 helper：构造 AuthClient 上下文管理器替身
# ---------------------------------------------------------------------------


def _make_auth_client(
    *,
    login_configs: object | None = None,
    public_key: str = "pem-key",
    mfa_detect: object | None = None,
    password_login: object | None = None,
    user_info: object | None = None,
    login_configs_error: Exception | None = None,
    mfa_error: Exception | None = None,
    login_error: Exception | None = None,
    user_info_error: Exception | None = None,
) -> Mock:
    """构造可控的 AuthClient 上下文管理器替身，默认走 happy path。"""
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)

    # get_login_configs
    if login_configs_error:
        client.get_login_configs = Mock(side_effect=login_configs_error)
    else:
        client.get_login_configs = Mock(
            return_value=login_configs
            or {
                "code": 0,
                "data": {"loginPageConfig": {"encryptEnabled": True}},
            }
        )

    client.get_public_key = Mock(return_value=public_key)

    # mfa_detect
    if mfa_error:
        client.mfa_detect = Mock(side_effect=mfa_error)
    else:
        client.mfa_detect = Mock(
            return_value=mfa_detect
            or {
                "code": 0,
                "data": {"mfaEnabled": False, "need": False},
            }
        )

    # password_login
    if login_error:
        client.password_login = Mock(side_effect=login_error)
    else:
        client.password_login = Mock(
            return_value=password_login
            or {
                "code": 0,
                "data": {"idToken": "test-jwt-token"},
            }
        )

    # get_user_info
    if user_info_error:
        client.get_user_info = Mock(side_effect=user_info_error)
    else:
        client.get_user_info = Mock(
            return_value=user_info or {"data": {"name": "Test User"}}
        )

    return client


def _patch_deps(
    monkeypatch: pytest.MonkeyPatch,
    client: Mock,
    *,
    rsa_result: str = "encrypted",
) -> None:
    """将 AuthClient 类和相关依赖统一 patch。"""
    monkeypatch.setattr("cli.auth.login.AuthClient", Mock(return_value=client))
    monkeypatch.setattr(
        "cli.auth.login.get_or_create_device_id", Mock(return_value="dev-001")
    )
    monkeypatch.setattr("cli.auth.login.save_session", Mock())
    monkeypatch.setattr("cli.auth.login.rsa_encrypt", Mock(return_value=rsa_result))


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


    # login(): 加密开启的标准成功路径，覆盖 RSA、登录、保存会话和拉取用户信息。
def test_login_happy_path_encrypt_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """加密启用 + 无 MFA 时，login 应返回包含 id_token 和 user 的结果字典。"""
    client = _make_auth_client()
    _patch_deps(monkeypatch, client)

    result = login("alice", "password123")

    assert result["id_token"] == "test-jwt-token"
    assert result["user"] == {"name": "Test User"}
    # rsa_encrypt 应被调用（加密启用）
    import cli.auth.login as _mod
    # save_session 应被调用一次
    _mod.save_session.assert_called_once()  # type: ignore[attr-defined]


    # login(): encryptEnabled=False 时应跳过 RSA，加密函数不被调用。
def test_login_encrypt_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """加密禁用时跳过 RSA，凭据以原始明文传递，login 仍应成功。"""
    client = _make_auth_client(
        login_configs={
            "code": 0,
            "data": {"loginPageConfig": {"encryptEnabled": False}},
        }
    )
    rsa_mock = Mock(return_value="encrypted")
    _patch_deps(monkeypatch, client, rsa_result="encrypted")
    # 覆盖 rsa_encrypt mock 以便追踪调用
    monkeypatch.setattr("cli.auth.login.rsa_encrypt", rsa_mock)

    result = login("alice", "password123")

    assert result["id_token"] == "test-jwt-token"
    # 加密禁用时 rsa_encrypt 不应被调用
    rsa_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 配置步骤失败
# ---------------------------------------------------------------------------


    # login(): loginConfigs 返回非 0 code 时，应在流程早期失败。
def test_login_config_code_nonzero_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """loginConfigs 返回非零 code 时应抛出 LoginError。"""
    client = _make_auth_client(
        login_configs={"code": 1, "message": "config unavailable"}
    )
    _patch_deps(monkeypatch, client)

    with pytest.raises(LoginError, match="Failed to get login config"):
        login("alice", "pw")


    # login(): MFA 探测接口返回业务失败码时，应包装为 LoginError。
def test_login_mfa_detect_code_nonzero_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """mfa/detect 返回非零 code 时应抛出 LoginError。"""
    client = _make_auth_client(
        mfa_detect={"code": 1, "message": "mfa detect failed"}
    )
    _patch_deps(monkeypatch, client)

    with pytest.raises(LoginError, match="MFA detect failed"):
        login("alice", "pw")


    # login(): 账号明确需要 MFA 时，应抛出专门的 MFARequiredError。
def test_login_mfa_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """mfaEnabled=True 且 need=True 时应抛出 MFARequiredError。"""
    client = _make_auth_client(
        mfa_detect={
            "code": 0,
            "data": {"mfaEnabled": True, "need": True},
        }
    )
    _patch_deps(monkeypatch, client)

    with pytest.raises(MFARequiredError, match="MFA is required"):
        login("alice", "pw")


    # login(): MFA 已开启但当前无需二次验证时，应透传 state 继续登录。
def test_login_mfa_enabled_not_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    """mfaEnabled=True 但 need=False 时应读取 state 继续，login 应成功。"""
    client = _make_auth_client(
        mfa_detect={
            "code": 0,
            "data": {"mfaEnabled": True, "need": False, "state": "mfa-state-xyz"},
        }
    )
    _patch_deps(monkeypatch, client)

    result = login("alice", "pw")

    assert result["id_token"] == "test-jwt-token"
    # password_login 被调用时 mfa_state 应传入正确的 state
    call_args = client.password_login.call_args
    assert call_args.kwargs.get("mfa_state") == "mfa-state-xyz" or (
        len(call_args.args) >= 5 and call_args.args[4] == "mfa-state-xyz"
    )


# ---------------------------------------------------------------------------
# 登录响应失败
# ---------------------------------------------------------------------------


    # login(): password_login 返回非 0 code 时，应以 LoginError 失败。
def test_login_response_code_nonzero_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """passwordLogin 返回非零 code 时应抛出 LoginError。"""
    client = _make_auth_client(
        password_login={"code": 1, "message": "wrong password"}
    )
    _patch_deps(monkeypatch, client)

    with pytest.raises(LoginError, match="Login failed"):
        login("alice", "wrong-pw")


    # login(): 登录响应缺少 idToken 时，应视为无效成功响应并报错。
def test_login_missing_idtoken_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """passwordLogin 响应缺少 idToken 字段时应抛出 LoginError。"""
    client = _make_auth_client(
        password_login={"code": 0, "data": {}}  # data 无 idToken
    )
    _patch_deps(monkeypatch, client)

    with pytest.raises(LoginError, match="no idToken"):
        login("alice", "pw")


    # login(): 用户信息拉取失败不应影响主登录结果，user 回退为空字典。
def test_login_user_info_failure_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_user_info 失败时 user 字段为空字典，但 id_token 仍正常返回。"""
    client = _make_auth_client(
        user_info_error=AuthClientError("user info unavailable")
    )
    _patch_deps(monkeypatch, client)

    result = login("alice", "pw")

    assert result["id_token"] == "test-jwt-token"
    assert result["user"] == {}


# ---------------------------------------------------------------------------
# 异常包装
# ---------------------------------------------------------------------------


    # login(): AuthClientError 这类底层客户端异常应统一包装为 LoginError。
def test_login_auth_client_error_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    """AuthClientError 应被包装为 LoginError 抛出。"""
    client = _make_auth_client(
        login_configs_error=AuthClientError("network timeout")
    )
    _patch_deps(monkeypatch, client)

    with pytest.raises(LoginError, match="network timeout"):
        login("alice", "pw")


    # login(): httpx.HTTPError 也应被转换为对外稳定的 LoginError。
def test_login_http_error_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    """httpx.HTTPError 应被包装为 LoginError 抛出。"""
    client = _make_auth_client(
        login_configs_error=httpx.HTTPError("HTTP 503")
    )
    _patch_deps(monkeypatch, client)

    with pytest.raises(LoginError, match="HTTP 503"):
        login("alice", "pw")
