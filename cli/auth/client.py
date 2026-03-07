from __future__ import annotations

import json
import logging
from types import TracebackType

import httpx

from cli.auth.parsers import (
    parse_login_configs_response,
    parse_mfa_response,
    parse_password_login_response,
    parse_user_info_response,
)
from cli.config import DEFAULT_HEADERS, LOGIN_BASE_URL, PERSONAL_BASE_URL
from cli.types import LoginConfigsResponse, MFAResponse, PasswordLoginResponse, UserInfoResponse

logger = logging.getLogger(__name__)


class AuthClientError(Exception):
    """Auth API request/response error."""


def _parse_json_response(response: httpx.Response, action: str) -> object:
    """Raise a descriptive error on HTTP failures or invalid JSON bodies."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = response.text.strip()
        raise AuthClientError(
            f"{action} failed with status {response.status_code}: {body or exc}"
        ) from exc

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise AuthClientError(f"{action} returned non-JSON response") from exc


class AuthClient:
    """HTTP client mapping to mj1.java Retrofit interface endpoints."""

    def __init__(self) -> None:
        self._client = httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True)

    def get_login_configs(self) -> LoginConfigsResponse:
        """GET loginConfigs — mj1.java line 161."""
        logger.debug("GET loginConfigs")
        resp = self._client.get(LOGIN_BASE_URL + "loginConfigs")
        logger.debug("GET loginConfigs response status=%d", resp.status_code)
        payload = _parse_json_response(resp, "loginConfigs")
        try:
            return parse_login_configs_response(payload)
        except ValueError as exc:
            raise AuthClientError(f"loginConfigs returned invalid payload: {exc}") from exc

    def get_public_key(self) -> str:
        """GET jwt/publicKey — mj1.java line 301. Returns raw PEM text."""
        logger.debug("GET jwt/publicKey")
        resp = self._client.get(LOGIN_BASE_URL + "jwt/publicKey")
        resp.raise_for_status()
        logger.debug("GET jwt/publicKey key length=%d", len(resp.text))
        return resp.text

    def mfa_detect(self, username: str, device_id: str, password: str) -> MFAResponse:
        """POST mfa/detect — mj1.java line 373. All params as @Query."""
        logger.debug("POST mfa/detect for user=%s", username)
        resp = self._client.post(
            LOGIN_BASE_URL + "mfa/detect",
            params={"username": username, "deviceId": device_id, "password": password},
        )
        payload = _parse_json_response(resp, "mfa/detect")
        try:
            data = parse_mfa_response(payload)
        except ValueError as exc:
            raise AuthClientError(f"mfa/detect returned invalid payload: {exc}") from exc
        logger.debug("POST mfa/detect response code=%s", data.get("code"))
        return data

    def password_login(
        self,
        username: str,
        password: str,
        app_id: str,
        device_id: str,
        mfa_state: str,
    ) -> PasswordLoginResponse:
        """POST password/passwordLogin — mj1.java line 140. All params as @Query."""
        logger.debug("POST passwordLogin for user=%s", username)
        resp = self._client.post(
            LOGIN_BASE_URL + "password/passwordLogin",
            params={
                "username": username,
                "password": password,
                "appId": app_id,
                "geo": "",
                "deviceId": device_id,
                "osType": "python",
                "clientId": "",
                "mfaState": mfa_state,
            },
        )
        payload = _parse_json_response(resp, "password/passwordLogin")
        try:
            data = parse_password_login_response(payload)
        except ValueError as exc:
            raise AuthClientError(
                f"password/passwordLogin returned invalid payload: {exc}"
            ) from exc
        logger.debug("POST passwordLogin response code=%s", data.get("code"))
        return data

    def get_user_info(self, id_token: str) -> UserInfoResponse:
        """GET api/v1/me/user — mj1.java line 65. Authorization: JWTToken {token}."""
        logger.debug("GET api/v1/me/user")
        resp = self._client.get(
            PERSONAL_BASE_URL + "api/v1/me/user",
            headers={"authorization": f"JWTToken {id_token}"},
        )
        logger.debug("GET api/v1/me/user response status=%d", resp.status_code)
        payload = _parse_json_response(resp, "api/v1/me/user")
        try:
            return parse_user_info_response(payload)
        except ValueError as exc:
            raise AuthClientError(f"api/v1/me/user returned invalid payload: {exc}") from exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AuthClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
