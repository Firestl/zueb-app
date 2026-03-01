"""
Attendance status service — orchestrates the WebHR card query flow.

Full flow:
  1. SSO: Exchange id_token → userCode + md5Str (attendance/sso.py)
  2. Sign: Generate RSA-SHA256 signature #1 from md5Str + userCode (attendance/sign.py)
  3. Token: POST appLoginsso → webhrtoken (attendance/client.py)
  4. Sign: Generate a second, fresh RSA-SHA256 signature
  5. Fetch: POST getKqCardInfo → raw card data

Card data structure (from response["data"]["data"]):
  sbk: [label, "HH:MM"] or ["无"] — 上班卡 (clock-in)
  xbk: [label, "HH:MM"] or ["无"] — 下班卡 (clock-out)
  "无" means the card has not been punched.
"""

from cli.attendance.client import WebHRClient, WebHRError
from cli.attendance.sign import SignatureError, generate_signature
from cli.attendance.sso import SSOError, get_sso_credentials


class AttendanceError(Exception):
    pass


def _extract_card_time(value) -> str:
    """Extract the time string from a card field list.

    The server returns card fields as a list: [label, "HH:MM"] when punched,
    or a shorter list / "无" when not punched.  Returns "" on unexpected input.
    """
    if not isinstance(value, list):
        return ""
    if len(value) < 2:
        return ""
    card_time = value[1]
    if not isinstance(card_time, str):
        return ""
    return card_time.strip()


def _is_card_done(card_time: str) -> bool:
    """Return True if the card has been punched (non-empty and not "无")."""
    return bool(card_time) and card_time != "无"


def get_attendance_status(id_token: str) -> dict:
    """Fetch today's clock-in and clock-out status for the authenticated user.

    Args:
        id_token: JWT token from the main CAS login.

    Returns:
        dict with keys:
            sbk_time — Clock-in time string ("HH:MM") or "" if not punched
            xbk_time — Clock-out time string ("HH:MM") or "" if not punched
            sbk_done — True if clock-in card has been punched
            xbk_done — True if clock-out card has been punched
            all_done — True if both cards are punched

    Raises:
        AttendanceError: If any step in the flow fails.
    """
    try:
        # Step 1: Exchange id_token for WebHR SSO credentials.
        sso = get_sso_credentials(id_token)
        user_code = sso["user_code"]
        md5str = sso["md5str"]

        # Step 2 & 3: Sign + get session token.
        first_sign = generate_signature(md5str, user_code)

        with WebHRClient() as client:
            webhrtoken = client.get_webhrtoken(
                user_code=user_code,
                md5str=md5str,
                signature=first_sign["sign"],
                timestamp=first_sign["timestamp"],
            )

            # Step 4 & 5: Fresh signature + fetch card data.
            # A new signature is required because the timestamp must be current.
            second_sign = generate_signature(md5str, user_code)
            raw = client.get_kqcard_info(
                webhrtoken=webhrtoken,
                signature=second_sign["sign"],
                timestamp=second_sign["timestamp"],
            )

        data = (raw.get("data") or {}).get("data")
        if not isinstance(data, dict):
            raise AttendanceError("Unexpected attendance response: missing data.data")

        sbk_time = _extract_card_time(data.get("sbk"))
        xbk_time = _extract_card_time(data.get("xbk"))
        sbk_done = _is_card_done(sbk_time)
        xbk_done = _is_card_done(xbk_time)

        return {
            "sbk_time": sbk_time,
            "xbk_time": xbk_time,
            "sbk_done": sbk_done,
            "xbk_done": xbk_done,
            "all_done": sbk_done and xbk_done,
        }
    except (SSOError, WebHRError, SignatureError, KeyError) as exc:
        raise AttendanceError(str(exc)) from exc
