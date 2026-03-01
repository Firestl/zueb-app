from cli.attendance.client import WebHRClient, WebHRError
from cli.attendance.sign import SignatureError, generate_signature
from cli.attendance.sso import SSOError, get_sso_credentials


class AttendanceError(Exception):
    pass


def _extract_card_time(value) -> str:
    if not isinstance(value, list):
        return ""
    if len(value) < 2:
        return ""
    card_time = value[1]
    if not isinstance(card_time, str):
        return ""
    return card_time.strip()


def _is_card_done(card_time: str) -> bool:
    return bool(card_time) and card_time != "无"


def get_attendance_status(id_token: str) -> dict:
    try:
        sso = get_sso_credentials(id_token)
        user_code = sso["user_code"]
        md5str = sso["md5str"]

        first_sign = generate_signature(md5str, user_code)

        with WebHRClient() as client:
            webhrtoken = client.get_webhrtoken(
                user_code=user_code,
                md5str=md5str,
                signature=first_sign["sign"],
                timestamp=first_sign["timestamp"],
            )

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
