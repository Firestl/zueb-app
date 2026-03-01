"""CAS SSO authentication for JWXT (教务系统)."""

from urllib.parse import parse_qs, urlparse

import httpx

from cli.config import CAS_LOGIN_URL, JWXT_BASE_URL

_JWXT_SERVICE_URL = f"{JWXT_BASE_URL}/jxcjcaslogin?url=h5/index.html"


class SSOError(Exception):
    """SSO authentication error."""


def get_jwxt_session(id_token: str) -> str:
    """
    Authenticate to JWXT using CAS SSO and return JSESSIONID.

    Flow:
        1. Request CAS login with idToken and service URL
        2. CAS redirects to JWXT with ticket
        3. JWXT validates ticket and sets JSESSIONID cookie

    Args:
        id_token: JWT token from login

    Returns:
        JSESSIONID cookie value

    Raises:
        SSOError: If SSO authentication fails
    """
    with httpx.Client(follow_redirects=False, timeout=30.0) as client:
        # Step 1: Request CAS login
        try:
            resp = client.get(
                CAS_LOGIN_URL,
                params={"idToken": id_token, "service": _JWXT_SERVICE_URL},
            )
        except httpx.RequestError as e:
            raise SSOError(f"CAS login request failed: {e}")

        # Step 2: Extract ticket from redirect
        if resp.status_code not in (302, 303):
            raise SSOError(f"CAS login failed: HTTP {resp.status_code}")

        location = resp.headers.get("Location")
        if not location:
            raise SSOError("CAS did not return redirect location")

        # Parse ticket from redirect URL
        parsed = urlparse(location)
        query = parse_qs(parsed.query)
        ticket = query.get("ticket", [None])[0]

        if not ticket:
            raise SSOError("No ticket in CAS redirect")

        # Step 3: Validate ticket with JWXT
        try:
            resp = client.get(location, cookies={})
        except httpx.RequestError as e:
            raise SSOError(f"JWXT ticket validation failed: {e}")

        # Extract JSESSIONID from cookies
        jsessionid = resp.cookies.get("JSESSIONID")
        if not jsessionid:
            raise SSOError("JWXT did not return JSESSIONID cookie")

        return jsessionid
