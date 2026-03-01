import httpx

from cli.config import DEFAULT_HEADERS, LOGIN_BASE_URL, PERSONAL_BASE_URL


class AuthClient:
    """HTTP client mapping to mj1.java Retrofit interface endpoints."""

    def __init__(self):
        self._client = httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True)

    def get_login_configs(self) -> dict:
        """GET loginConfigs — mj1.java line 161."""
        resp = self._client.get(LOGIN_BASE_URL + "loginConfigs")
        resp.raise_for_status()
        return resp.json()

    def get_public_key(self) -> str:
        """GET jwt/publicKey — mj1.java line 301. Returns raw PEM text."""
        resp = self._client.get(LOGIN_BASE_URL + "jwt/publicKey")
        resp.raise_for_status()
        return resp.text

    def mfa_detect(self, username: str, device_id: str, password: str) -> dict:
        """POST mfa/detect — mj1.java line 373. All params as @Query."""
        resp = self._client.post(
            LOGIN_BASE_URL + "mfa/detect",
            params={"username": username, "deviceId": device_id, "password": password},
        )
        resp.raise_for_status()
        return resp.json()

    def password_login(
        self,
        username: str,
        password: str,
        app_id: str,
        device_id: str,
        mfa_state: str,
    ) -> dict:
        """POST password/passwordLogin — mj1.java line 140. All params as @Query."""
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
        resp.raise_for_status()
        return resp.json()

    def get_user_info(self, id_token: str) -> dict:
        """GET api/v1/me/user — mj1.java line 65. Authorization: JWTToken {token}."""
        resp = self._client.get(
            PERSONAL_BASE_URL + "api/v1/me/user",
            headers={"authorization": f"JWTToken {id_token}"},
        )
        resp.raise_for_status()
        return resp.json()

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
