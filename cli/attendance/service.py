"""
Attendance service for the WebHR card system.

This module supports both read-only attendance status queries and actual
punch submission. The submission flow follows the previously reverse-
engineered `zueb_savecard` implementation:
  1. SSO: Exchange id_token → userCode + md5Str
  2. Sign: Generate RSA-SHA256 signature #1
  3. Token: POST appLoginsso → webhrtoken
  4. Sign: Generate RSA-SHA256 signature #2
  5. Fetch: POST getKqCardInfo → current card state
  6. Resolve target card (auto/sbk/xbk)
  7. Sign: Generate RSA-SHA256 signature #3
  8. Submit: POST saveKqCard
"""

from __future__ import annotations

from datetime import datetime, time
import logging
import os
from zoneinfo import ZoneInfo

from cli.attendance.client import WebHRClient, WebHRError
from cli.attendance.sign import SignatureError, generate_signature
from cli.attendance.sso import SSOError, get_sso_credentials
from cli.config import ATTENDANCE_DEFAULT_XY_ENV
from cli.types import (
    AttendancePunchMode,
    AttendancePunchResult,
    AttendanceResolvedMode,
    AttendanceStatus,
    CardField,
    JSONObject,
    SSOCredentials,
)

logger = logging.getLogger(__name__)

_ATTENDANCE_TIMEZONE = ZoneInfo("Asia/Shanghai")


class AttendanceError(Exception):
    pass


def _extract_card_time(value: CardField | None) -> str:
    """Extract the time string from a card field list.

    The server returns card fields as a list: [label, "HH:MM"] when punched,
    or a shorter list / "无" when not punched. Returns "" on unexpected input.
    """
    if not isinstance(value, list):
        return ""
    if len(value) < 2:
        return ""
    return value[1].strip()



def _is_card_done(card_time: str) -> bool:
    """Return True if the card has been punched (non-empty and not "无")."""
    return bool(card_time) and card_time != "无"



def _attendance_status_from_raw(raw: object) -> AttendanceStatus:
    if not isinstance(raw, dict):
        raise AttendanceError("Unexpected attendance response: payload must be an object")

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



def _authenticate_webhr(client: WebHRClient, id_token: str) -> tuple[SSOCredentials, str]:
    logger.info("Step 1: Exchanging id_token for WebHR SSO credentials...")
    sso = get_sso_credentials(id_token)
    user_code = sso["user_code"]
    md5str = sso["md5str"]
    logger.info("Step 1: Got user_code=%s", user_code)

    logger.info("Step 2: Generating first RSA signature...")
    first_sign = generate_signature(md5str, user_code)

    logger.info("Step 3: Getting WebHR session token...")
    webhrtoken = client.get_webhrtoken(
        user_code=user_code,
        md5str=md5str,
        signature=first_sign["sign"],
        timestamp=first_sign["timestamp"],
    )
    logger.info("Step 3: Got webhrtoken (len=%d)", len(webhrtoken))
    return sso, webhrtoken



def _fetch_attendance_raw(
    client: WebHRClient,
    *,
    webhrtoken: str,
    user_code: str,
    md5str: str,
) -> JSONObject:
    logger.info("Step 4: Generating second RSA signature...")
    second_sign = generate_signature(md5str, user_code)
    logger.info("Step 5: Fetching card data...")
    raw = client.get_kqcard_info(
        webhrtoken=webhrtoken,
        signature=second_sign["sign"],
        timestamp=second_sign["timestamp"],
    )
    return {str(key): value for key, value in raw.items()}



def _normalize_xy(xy: str | None) -> str:
    value = (xy or os.getenv(ATTENDANCE_DEFAULT_XY_ENV) or "").strip()
    if not value:
        raise AttendanceError(
            f"Attendance coordinates are required. Provide --xy or set {ATTENDANCE_DEFAULT_XY_ENV}."
        )

    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        raise AttendanceError("Attendance coordinates must be in 'lng,lat' format")

    try:
        float(parts[0])
        float(parts[1])
    except ValueError as exc:
        raise AttendanceError("Attendance coordinates must contain valid numbers") from exc

    return f"{parts[0]},{parts[1]}"



def _check_time_window(mode: AttendanceResolvedMode) -> None:
    now = datetime.now(_ATTENDANCE_TIMEZONE)
    if mode == "sbk" and now.time() > time(8, 0):
        raise AttendanceError(f"上班卡仅允许 08:00 前打卡，当前时间为 {now:%H:%M}")
    if mode == "xbk" and now.time() < time(16, 30):
        raise AttendanceError(f"下班卡仅允许 16:30 后打卡，当前时间为 {now:%H:%M}")



def _resolve_mode(
    requested_mode: AttendancePunchMode,
    status: AttendanceStatus,
) -> tuple[AttendanceResolvedMode | None, str]:
    if requested_mode == "auto":
        if not status["sbk_done"]:
            return "sbk", "将自动提交上班卡"
        if not status["xbk_done"]:
            return "xbk", "将自动提交下班卡"
        return None, "今日上班卡和下班卡都已完成，无需重复打卡"

    done = status["sbk_done"] if requested_mode == "sbk" else status["xbk_done"]
    if done:
        label = "上班卡" if requested_mode == "sbk" else "下班卡"
        return None, f"今日{label}已完成，无需重复打卡"
    return requested_mode, "准备提交打卡"



def get_attendance_status(id_token: str) -> AttendanceStatus:
    """Fetch today's clock-in and clock-out status for the authenticated user."""
    try:
        with WebHRClient() as client:
            sso, webhrtoken = _authenticate_webhr(client, id_token)
            raw = _fetch_attendance_raw(
                client,
                webhrtoken=webhrtoken,
                user_code=sso["user_code"],
                md5str=sso["md5str"],
            )
        status = _attendance_status_from_raw(raw)
        logger.info(
            "Attendance result: sbk_done=%s, xbk_done=%s",
            status["sbk_done"],
            status["xbk_done"],
        )
        return status
    except (SSOError, WebHRError, SignatureError, KeyError) as exc:
        raise AttendanceError(str(exc)) from exc



def punch_attendance(
    id_token: str,
    *,
    mode: AttendancePunchMode = "auto",
    xy: str | None = None,
) -> AttendancePunchResult:
    """Submit an attendance punch using the WebHR mobile API."""
    try:
        normalized_xy = _normalize_xy(xy)

        with WebHRClient() as client:
            sso, webhrtoken = _authenticate_webhr(client, id_token)
            raw = _fetch_attendance_raw(
                client,
                webhrtoken=webhrtoken,
                user_code=sso["user_code"],
                md5str=sso["md5str"],
            )
            attendance_before = _attendance_status_from_raw(raw)
            resolved_mode, message = _resolve_mode(mode, attendance_before)
            if resolved_mode is None:
                return {
                    "executed": False,
                    "mode_requested": mode,
                    "mode_executed": None,
                    "message": message,
                    "attendance_before": attendance_before,
                    "response": None,
                }

            _check_time_window(resolved_mode)

            logger.info("Step 6: Generating third RSA signature for saveKqCard...")
            third_sign = generate_signature(sso["md5str"], sso["user_code"])
            logger.info("Step 7: Submitting saveKqCard mode=%s", resolved_mode)
            response = client.save_kqcard(
                webhrtoken=webhrtoken,
                signature=third_sign["sign"],
                timestamp=third_sign["timestamp"],
                xy=normalized_xy,
                sbflag=resolved_mode,
            )

        response_message = response.get("message")
        if isinstance(response_message, str) and response_message.strip():
            message = response_message.strip()
        else:
            message = "打卡请求已提交"

        return {
            "executed": True,
            "mode_requested": mode,
            "mode_executed": resolved_mode,
            "message": message,
            "attendance_before": attendance_before,
            "response": response,
        }
    except (SSOError, WebHRError, SignatureError, KeyError) as exc:
        raise AttendanceError(str(exc)) from exc
