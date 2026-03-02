"""
HTTP client for the WebHR attendance system (rsxt1.zueb.edu.cn/webhr/).

Authentication flow (called by attendance/service.py):
  1. Call `get_webhrtoken` with SSO credentials + first RSA signature
     → returns a short-lived webhrtoken (session bearer token)
  2. Call `get_kqcard_info` with the webhrtoken + a second RSA signature
     → returns today's clock-in / clock-out card data

Both requests send the RSA signature in the JSON body (not as a header),
along with the current Unix timestamp used in the signed payload.
"""

import json
import logging

import httpx

from cli.config import DEFAULT_HEADERS, WEBHR_BASE_URL

logger = logging.getLogger(__name__)


class WebHRError(Exception):
    pass


def _parse_json_response(response: httpx.Response, action: str) -> dict:
    """Raise a descriptive WebHRError on HTTP errors or non-JSON bodies.

    Args:
        response: The httpx Response to validate.
        action:   Human-readable endpoint label for error messages.
    """
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = response.text.strip()
        raise WebHRError(
            f"{action} failed with status {response.status_code}: {body or exc}"
        ) from exc

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise WebHRError(f"{action} returned non-JSON response") from exc


class WebHRClient:
    """HTTP client for the WebHR attendance API.

    Manages a persistent httpx session across the two-step auth flow.
    Use as a context manager to ensure the session is closed:

        with WebHRClient() as client:
            token = client.get_webhrtoken(...)
            data  = client.get_kqcard_info(token, ...)
    """

    def __init__(self):
        self._client = httpx.Client(
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )

    def get_webhrtoken(
        self,
        user_code: str,
        md5str: str,
        signature: str,
        timestamp: int,
    ) -> str:
        """Exchange SSO credentials for a WebHR session token.

        POSTs to `appLoginsso` with the SSO credentials and RSA signature.
        The returned token must be passed to every subsequent API call.

        Args:
            user_code: WebHR user identifier from the SSO redirect URL.
            md5str:    Session credential from the SSO redirect URL.
            signature: Base64 RSA-SHA256 signature of "{md5str}&{user_code}&{timestamp}".
            timestamp: Unix epoch seconds used in the signature payload.

        Returns:
            webhrtoken string (short-lived session bearer).

        Raises:
            WebHRError: If the request fails or token is absent in the response.
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": "https://rsxt1.zueb.edu.cn",
            "Referer": (
                "https://rsxt1.zueb.edu.cn/webhrApp/static/loginsso.html"
                f"?userCode={user_code}&md5Str={md5str}"
                "&targetUrl=App-apply/App-apply-kqcard/index"
            ),
            # Server expects "null" (string literal) before the token is known.
            "webhrtoken": "null",
        }
        payload = {
            "userCode": user_code,
            "md5Str": md5str,
            "signature": signature,
            "timestamp": timestamp,
        }

        logger.info("POST appLoginsso for user_code=%s", user_code)
        response = self._client.post(
            WEBHR_BASE_URL + "appLoginsso",
            headers=headers,
            json=payload,
        )
        logger.debug("appLoginsso response status=%d", response.status_code)
        data = _parse_json_response(response, "appLoginsso")

        token = ((data.get("data") or {}).get("data") or {}).get("token")
        if not token:
            raise WebHRError("appLoginsso response missing data.data.token")
        logger.debug("Obtained webhrtoken (len=%d)", len(token))
        return token

    def get_kqcard_info(
        self,
        webhrtoken: str,
        signature: str,
        timestamp: int,
    ) -> dict:
        """Fetch today's clock-in / clock-out card information.

        Args:
            webhrtoken: Session token from `get_webhrtoken`.
            signature:  Base64 RSA-SHA256 signature (fresh, second call).
            timestamp:  Unix epoch seconds used in the signature payload.

        Returns:
            Raw response JSON; the card data is at response["data"]["data"].
            Fields: sbk (上班卡 clock-in list), xbk (下班卡 clock-out list).

        Raises:
            WebHRError: If the request fails or the response is not valid JSON.
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": "https://rsxt1.zueb.edu.cn",
            "Referer": "https://rsxt1.zueb.edu.cn/webhrApp/",
            # The cookie header is set manually because httpx CookieJar
            # would not send it to a different path scope automatically.
            "cookie": f"token={webhrtoken}",
        }

        payload = {
            "webhrtoken": webhrtoken,
            "signature": signature,
            "timestamp": timestamp,
        }

        logger.info("POST getKqCardInfo")
        response = self._client.post(
            WEBHR_BASE_URL + "AppKqCard/getKqCardInfo",
            headers=headers,
            json=payload,
        )
        logger.debug("getKqCardInfo response status=%d", response.status_code)
        return _parse_json_response(response, "getKqCardInfo")

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
