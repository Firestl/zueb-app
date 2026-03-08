"""
Global configuration constants for the ZUEB CLI.

URL layout:
  - CAS (cas.zueb.edu.cn): Central Authentication Service — handles login,
    token issuance, and SSO ticket generation for downstream systems.
  - authx-service (authx-service.zueb.edu.cn): Personal/profile API — used
    after login to fetch user info (name, email, orgName, etc.).
  - WebHR (rsxt1.zueb.edu.cn/webhr/): HR/attendance system — requires a
    separate SSO credential exchange before use.
  - JWXT (jwxt.zueb.edu.cn): Academic Affairs System (教务系统) — requires
    CAS SSO ticket exchange to obtain a JSESSIONID before use.

Local persistence (under ~/.config/zueb-cli/):
  - session.json: Stores id_token, username, and device_id after successful login.
  - device.json: Stores a stable UUID4 that acts as the device identifier,
    so repeated logins look like the same device to the server.
"""

from pathlib import Path

# ── CAS / auth endpoints ──────────────────────────────────────────────────────
# Base URL for the Supwisdom CAS token API (loginConfigs, publicKey, mfa, login).
# Derived from mj1.java Retrofit interface and gn1.java SwitchHostUtil.
LOGIN_BASE_URL = "https://cas.zueb.edu.cn/token/"

# Personal profile API — used to fetch user info with "Authorization: JWTToken <token>".
PERSONAL_BASE_URL = "https://authx-service.zueb.edu.cn/personal/"

# ── Downstream system endpoints ───────────────────────────────────────────────
# WebHR attendance system; login requires its own SSO credential exchange first.
WEBHR_BASE_URL = "https://rsxt1.zueb.edu.cn/webhr/"

# JWXT academic affairs system (教务系统); requires CAS SSO JSESSIONID.
JWXT_BASE_URL = "https://jwxt.zueb.edu.cn"

# CAS SSO login URL — used to exchange an id_token for a service ticket.
CAS_LOGIN_URL = "https://cas.zueb.edu.cn/cas/login"

# Android app bundle identifier — passed as appId during password login.
# Source: build.gradle line 10 (applicationId).
APP_ID = "com.supwisdom.zueb"

# Default attendance coordinate env var name. Value format: "lng,lat".
ATTENDANCE_DEFAULT_XY_ENV = "ZUEB_ATTENDANCE_DEFAULT_XY"

# ── Default HTTP headers ──────────────────────────────────────────────────────
# Mimics a mobile Chrome browser to avoid server-side bot detection.
DEFAULT_HEADERS = {
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
}

# ── Local config file paths ───────────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".config" / "zueb-cli"
# Stores: {"id_token": "...", "username": "...", "device_id": "..."}
TOKEN_FILE = CONFIG_DIR / "session.json"
# Stores: {"device_id": "<uuid4>"} — persisted once and reused across sessions.
DEVICE_FILE = CONFIG_DIR / "device.json"
