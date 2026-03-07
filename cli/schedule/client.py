"""HTTP client for JWXT (教务系统) API."""

from __future__ import annotations

import hashlib
import logging
import math
import re
import time
from types import TracebackType
from typing import cast

import httpx

from cli.types import JSONObject, ScheduleData, SemesterItem
from cli.config import JWXT_BASE_URL

logger = logging.getLogger(__name__)


class JWXTClientError(Exception):
    """JWXT client operation error."""


class JWXTClient:
    """JWXT H5 client for jw_apply-based schedule endpoints."""

    BASE_URL = JWXT_BASE_URL
    _DEFAULT_ENCRYPT_KEY = "1tkdum1tkcbb"
    _REQUEST_TYPE = "kbvueh5"
    _STEP_XNXQ = "xnxq"
    _STEP_DETAIL = "detail"

    def __init__(
        self,
        jsessionid: str,
        login_id: str = "",
        user_type: str = "",
    ) -> None:
        """
        Initialize JWXT client with session cookie.

        Args:
            jsessionid: JSESSIONID cookie value from SSO
            login_id: Optional fallback user id (student/staff number)
            user_type: Optional fallback user type (TEA/STU/NST)
        """
        logger.debug("Initializing JWXT client with JSESSIONID (len=%d)", len(jsessionid))
        self.jsessionid = jsessionid
        self.login_id = login_id
        self.user_type = user_type
        self.school_code = ""
        self.encrypt_key = self._DEFAULT_ENCRYPT_KEY

        self._client = httpx.Client(
            base_url=self.BASE_URL,
            timeout=30.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
                    "SuperApp SuperApp-13508"
                ),
                "Referer": f"{self.BASE_URL}/h5/index.html",
            },
            cookies={"JSESSIONID": jsessionid},
        )
        self._bootstrap_context()

    def close(self) -> None:
        """Close underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> JWXTClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _bootstrap_context(self) -> None:
        """Load runtime context (G_ENCRYPT/G_LOGIN_ID/G_USER_TYPE) from H5 JS."""
        logger.debug("Bootstrapping JWXT context from H5 JS...")
        # Keep behavior close to app traffic: visit index first, then context JS.
        self._client.get("/h5/index.html")
        resp = self._client.get("/custom/js/SetRootPath4H5.jsp")
        resp.raise_for_status()

        script = resp.text
        self.encrypt_key = self._extract_js_var(script, "G_ENCRYPT") or self.encrypt_key
        js_login_id = self._extract_js_var(script, "G_LOGIN_ID")
        # SetRootPath4H5.jsp occasionally returns guest placeholders.
        # Keep token-derived identity in that case, otherwise schedule data may become empty.
        if js_login_id and "guest" not in js_login_id.lower():
            self.login_id = js_login_id

        js_user_type = self._extract_js_var(script, "G_USER_TYPE")
        # "SPE" is the same placeholder profile seen with guest context.
        if js_user_type and js_user_type.upper() != "SPE":
            self.user_type = js_user_type

        logger.debug(
            "Context: login_id=%s, user_type=%s, encrypt_key=%s...",
            self.login_id, self.user_type, self.encrypt_key[:8],
        )
        self.school_code = (
            self._extract_js_var(script, "G_SCHOOL_CODE") or self.school_code
        )
        logger.debug("School code: %s", self.school_code)
        user_code = self._extract_js_var(script, "G_USER_CODE")

        if not self.user_type:
            self.user_type = self._infer_user_type_from_user_code(user_code)

        if not self.login_id:
            raise JWXTClientError("missing G_LOGIN_ID from SetRootPath4H5.jsp")

    @staticmethod
    def _extract_js_var(script: str, name: str) -> str:
        # SetRootPath4H5.jsp uses: var NAME = 'value';
        # Keep regex tolerant to spaces and quote style.
        match = re.search(
            rf"var\s+{re.escape(name)}\s*=\s*['\"]([^'\"]*)['\"]\s*;", script
        )
        return match.group(1) if match else ""

    @staticmethod
    def _infer_user_type_from_user_code(user_code: str) -> str:
        # Common pattern in many deployments: txxxx -> TEA, sxxxx -> STU.
        if not user_code:
            return ""
        first = user_code[0].lower()
        if first == "t":
            return "TEA"
        if first == "s":
            return "STU"
        return ""

    @staticmethod
    def _to_base36(value: int) -> str:
        if value == 0:
            return "0"
        if value < 0:
            return "-" + JWXTClient._to_base36(-value)
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        out: list[str] = []
        n = value
        while n > 0:
            out.append(digits[n % 36])
            n //= 36
        return "".join(reversed(out))

    @staticmethod
    def _get_md5_2(plain: str) -> str:
        """Compute JWXT `param2` digest from the plaintext query string.

        Args:
            plain: Raw query string built by `_build_plain_payload`.

        Returns:
            Lowercase 32-char hex MD5 string used as `param2`.
        """
        # JWXT H5 getMd5_2 (used as param2 for jw_apply):
        #   h1 = md5(plain)
        #   remove chars at 1-index positions 3,10,17,25
        #   return md5(filtered)
        # Note: param2 is derived only from plain payload (not timestamp/server time).
        h1 = hashlib.md5(plain.encode("utf-8")).hexdigest()
        filtered = "".join(
            ch for i, ch in enumerate(h1, start=1) if i not in {3, 10, 17, 25}
        )
        return hashlib.md5(filtered.encode("utf-8")).hexdigest()

    @classmethod
    def _of_encrypt(cls, plain: str, key: str) -> str:
        """Encrypt a plaintext string with the JWXT jw_apply cipher.

        Port of module 76e3/of_encrypt from the JWXT H5 JavaScript bundle.

        Algorithm overview:
          1. Compute a single-byte `offset` = (6 * ceil(N/3)) % len(key),
             where N is the length of the plaintext.  This ties the offset to
             the message length and the key length.
          2. Walk each character of `plain`, pairing it with the corresponding
             cycling character of `key` (key repeats if plain is longer).
             Compute: mixed = ord(plain_char) + ord(key_char) + offset
             Format `mixed` as exactly 3 decimal digits (last 3 if overflow),
             appending each to a growing `decimal_stream` string.
          3. Slice `decimal_stream` into 9-digit chunks.
             Each 9-digit chunk is an integer; convert it to base-36 and
             zero-pad to 6 characters.  These 6-char groups are concatenated
             to form the final ciphertext.

        The session-specific `G_ENCRYPT` key (fetched from SetRootPath4H5.jsp)
        is used in production; the default fallback is "1tkdum1tkcbb".

        Args:
            plain: Plaintext query string to encrypt.
            key:   Encryption key (G_ENCRYPT from the JWXT session context).

        Returns:
            Encrypted string of base-36 6-char groups, or `plain` unchanged
            if either argument is empty.
        """
        if not plain or not key:
            return plain

        key_len = len(key)
        data_len = len(plain)
        rounds = math.ceil(data_len / key_len)
        # cipher_len is the total output length (6 chars per 3 input chars).
        cipher_len = 6 * math.ceil(data_len / 3)
        offset = cipher_len % key_len

        # Step 2: build decimal stream by mixing each plaintext char with its key char.
        decimal_stream = ""
        for round_index in range(rounds):
            for key_index in range(1, key_len + 1):
                pos = round_index * key_len + key_index
                if pos > data_len:
                    break
                data_ch = plain[pos - 1]
                key_ch = key[key_index - 1]
                mixed = ord(data_ch) + ord(key_ch) + offset
                # Take only the last 3 digits to keep each unit exactly 3 chars.
                decimal_stream += f"{mixed:03d}"[-3:]

        # Step 3: convert 9-digit chunks to zero-padded 6-char base-36 strings.
        encoded = ""
        cursor = 0
        while cursor < len(decimal_stream):
            chunk = decimal_stream[cursor : cursor + 9]
            cursor += 9
            base36 = cls._to_base36(int(chunk))
            encoded += ("000000" + base36)[-6:]
        return encoded

    def _build_plain_payload(self, step: str, payload: dict[str, str]) -> str:
        """
        Build plaintext query string exactly like JWXT H5 request interceptor.

        `param2` is derived from this exact plain string, so key order and raw value
        formatting must stay stable (no URL-encoding at this stage).

        Args:
            step: JWXT business step (for example, `xnxq` or `detail`).
            payload: Endpoint-specific plain fields to append after base fields.

        Returns:
            Plain `k=v&...` string used to generate both `param` and `param2`.
        """
        data: dict[str, str] = {
            "action": "jw_apply",
            "type": self._REQUEST_TYPE,
            "step": step,
        }

        # Keep insertion order from caller payload, mirroring JS object behavior.
        data.update(payload)

        if not data.get("userid"):
            data["userid"] = self.login_id
        if not data.get("userId"):
            data["userId"] = self.login_id
        if not data.get("yhzh"):
            data["yhzh"] = self.login_id
        if not data.get("usertype"):
            data["usertype"] = self.user_type

        # detail requests include these keys in app traffic, even when empty.
        if step == self._STEP_DETAIL:
            data.setdefault("bjdm", "")
            data.setdefault("jsdm", "")

        parts = [f"{k}={v}" for k, v in data.items()]
        return "&".join(parts)

    def _jw_apply_get(
        self, endpoint: str, step: str, payload: dict[str, str]
    ) -> JSONObject:
        """Send one jw_apply GET request and return decoded JSON payload.

        Args:
            endpoint: Relative JWXT path (for example, `/wap/mycourseschedule.action`).
            step: `step` field included in the plaintext payload.
            payload: Endpoint-specific business payload fields.

        Returns:
            Response body parsed as JSON dict.

        Raises:
            httpx.HTTPError: Request failure or non-2xx status code.
            ValueError: Response body is not valid JSON.
        """
        logger.debug("jw_apply GET %s step=%s", endpoint, step)
        plain = self._build_plain_payload(step, payload)
        encrypted = self._of_encrypt(plain, self.encrypt_key)
        logger.debug("Encrypted param length=%d", len(encrypted))
        params = {
            "action": "jw_apply",
            "param": encrypted,
            "param2": self._get_md5_2(plain),
            "timestamp": str(int(time.time() * 1000)),
        }

        resp = self._client.get(endpoint, params=params)
        logger.debug("Response status=%d", resp.status_code)
        resp.raise_for_status()
        return resp.json()

    def get_semester_items(self) -> list[SemesterItem]:
        """
        Return raw semester list items from getxnxq_xl.

        Each item usually contains:
            - dm: semester code (e.g. 20250 / 20251)
            - mc: display name
            - dqxq: current-semester marker ("1" means current)
        """
        logger.debug("Fetching semester items...")
        data = self.get_semester_list()
        items = data.get("xnxq", [])
        if not isinstance(items, list):
            raise JWXTClientError(
                "unexpected semester list response: xnxq is not a list"
            )
        semester_items: list[SemesterItem] = []
        for item in items:
            if isinstance(item, dict):
                semester_items.append(cast(SemesterItem, item))
        return semester_items

    def resolve_semester_code(self, year: int, term: int) -> str:
        """
        Resolve semester code from year/term.

        Args:
            year: academic year start, e.g. 2025 for "2025-2026学年"
            term: 1 (第一学期) or 2 (第二学期)
        """
        logger.debug("Resolving semester code for year=%d, term=%d", year, term)
        if term not in (1, 2):
            raise JWXTClientError("term must be 1 or 2")

        items = self.get_semester_items()

        # Common convention in this deployment: 20250 -> 第一学期, 20251 -> 第二学期.
        target_dm = f"{year}{0 if term == 1 else 1}"
        for item in items:
            if str(item.get("dm", "")) == target_dm:
                logger.debug("Resolved semester code=%s", target_dm)
                return target_dm

        # Fallback by display name.
        year_label = f"{year}-{year + 1}学年"
        term_label = "第一学期" if term == 1 else "第二学期"
        for item in items:
            mc = str(item.get("mc", ""))
            dm = str(item.get("dm", ""))
            if dm and year_label in mc and term_label in mc:
                logger.debug("Resolved semester code=%s", dm)
                return dm

        raise JWXTClientError(
            f"cannot resolve semester code for year={year}, term={term}"
        )

    def get_semester_list(self) -> JSONObject:
        """
        Call /wap/getxnxq_xl.action (step=xnxq) with jw_apply signing/encryption.

        Returns:
            Raw response JSON containing semester metadata (including xnxq list).

        Raises:
            httpx.HTTPError: If request fails
        """
        logger.debug("GET /wap/getxnxq_xl.action")
        return self._jw_apply_get("/wap/getxnxq_xl.action", self._STEP_XNXQ, {})

    def get_course_schedule(
        self, semester_code: str | None = None, week: str | None = None
    ) -> ScheduleData:
        """
        Get course schedule for a semester (optionally for a specific week).

        Args:
            semester_code: Semester code (e.g., "20251"), None means current.
            week: Explicit week string; None applies deployment-specific default.

        Returns:
            Raw mycourseschedule JSON payload.

        Raises:
            httpx.HTTPError: If request fails
        """
        logger.debug("GET /wap/mycourseschedule.action semester=%s week=%s", semester_code, week)
        semester_items = self.get_semester_items()
        current_dm = ""
        for item in semester_items:
            if str(item.get("dqxq", "")) == "1":
                current_dm = str(item.get("dm", ""))
                break

        if semester_code is None:
            if not current_dm:
                raise JWXTClientError(
                    "cannot determine current semester from getxnxq_xl"
                )
            semester_code = current_dm
            if not semester_code:
                raise JWXTClientError("current semester has empty dm")

        if week is None:
            # Matches packet behavior:
            # - current semester uses empty week
            # - non-current semester often needs week=1 to get stable data
            week = "" if semester_code == current_dm else "1"

        payload = {"xnxq": semester_code, "week": week}
        return cast(ScheduleData, self._jw_apply_get(
            "/wap/mycourseschedule.action", self._STEP_DETAIL, payload
        ))
