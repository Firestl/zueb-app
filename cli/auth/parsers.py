from __future__ import annotations

from cli.types import (
    LoginConfigsData,
    LoginConfigsResponse,
    LoginPageConfig,
    MFAData,
    MFAResponse,
    PasswordLoginData,
    PasswordLoginResponse,
    UserInfo,
    UserInfoResponse,
)


def _expect_object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a JSON object")
    return value


def _optional_int(source: dict[str, object], key: str, context: str) -> int | None:
    value = source.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context}.{key} must be an integer")
    return value


def _optional_str(source: dict[str, object], key: str, context: str) -> str | None:
    value = source.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{context}.{key} must be a string")
    return value


def _optional_bool(source: dict[str, object], key: str, context: str) -> bool | None:
    value = source.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{context}.{key} must be a boolean")
    return value


def parse_user_info(value: object, *, context: str) -> UserInfo:
    source = _expect_object(value, context)
    user: UserInfo = {}

    for key in ("name", "realName", "username", "mobile", "email", "orgName", "userType"):
        item = source.get(key)
        if item is None:
            continue
        if not isinstance(item, str):
            raise ValueError(f"{context}.{key} must be a string")
        user[key] = item

    return user


def parse_login_configs_response(payload: object) -> LoginConfigsResponse:
    source = _expect_object(payload, "loginConfigs response")
    response: LoginConfigsResponse = {}

    code = _optional_int(source, "code", "loginConfigs response")
    if code is not None:
        response["code"] = code

    message = _optional_str(source, "message", "loginConfigs response")
    if message is not None:
        response["message"] = message

    data_value = source.get("data")
    if data_value is not None:
        data_source = _expect_object(data_value, "loginConfigs response.data")
        data: LoginConfigsData = {}

        config_value = data_source.get("loginPageConfig")
        if config_value is not None:
            config_source = _expect_object(
                config_value,
                "loginConfigs response.data.loginPageConfig",
            )
            config: LoginPageConfig = {}

            encrypt_enabled = _optional_bool(
                config_source,
                "encryptEnabled",
                "loginConfigs response.data.loginPageConfig",
            )
            if encrypt_enabled is not None:
                config["encryptEnabled"] = encrypt_enabled

            data["loginPageConfig"] = config

        response["data"] = data

    return response


def parse_mfa_response(payload: object) -> MFAResponse:
    source = _expect_object(payload, "mfa/detect response")
    response: MFAResponse = {}

    code = _optional_int(source, "code", "mfa/detect response")
    if code is not None:
        response["code"] = code

    message = _optional_str(source, "message", "mfa/detect response")
    if message is not None:
        response["message"] = message

    data_value = source.get("data")
    if data_value is not None:
        data_source = _expect_object(data_value, "mfa/detect response.data")
        data: MFAData = {}

        mfa_enabled = _optional_bool(data_source, "mfaEnabled", "mfa/detect response.data")
        if mfa_enabled is not None:
            data["mfaEnabled"] = mfa_enabled

        need = _optional_bool(data_source, "need", "mfa/detect response.data")
        if need is not None:
            data["need"] = need

        state = _optional_str(data_source, "state", "mfa/detect response.data")
        if state is not None:
            data["state"] = state

        response["data"] = data

    return response


def parse_password_login_response(payload: object) -> PasswordLoginResponse:
    source = _expect_object(payload, "passwordLogin response")
    response: PasswordLoginResponse = {}

    code = _optional_int(source, "code", "passwordLogin response")
    if code is not None:
        response["code"] = code

    message = _optional_str(source, "message", "passwordLogin response")
    if message is not None:
        response["message"] = message

    data_value = source.get("data")
    if data_value is not None:
        data_source = _expect_object(data_value, "passwordLogin response.data")
        data: PasswordLoginData = {}

        id_token = _optional_str(data_source, "idToken", "passwordLogin response.data")
        if id_token is not None:
            data["idToken"] = id_token

        response["data"] = data

    return response


def parse_user_info_response(payload: object) -> UserInfoResponse:
    source = _expect_object(payload, "user info response")
    response: UserInfoResponse = {}

    code = _optional_int(source, "code", "user info response")
    if code is not None:
        response["code"] = code

    message = _optional_str(source, "message", "user info response")
    if message is not None:
        response["message"] = message

    data_value = source.get("data")
    if data_value is not None:
        response["data"] = parse_user_info(data_value, context="user info response.data")

    return response
