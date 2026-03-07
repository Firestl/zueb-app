import logging
import re

import httpx

from cli.auth.client import AuthClient, AuthClientError
from cli.auth.crypto import rsa_encrypt
from cli.auth.token import get_or_create_device_id, save_session
from cli.config import APP_ID
from cli.types import LoginResult, UserInfo

logger = logging.getLogger(__name__)


class LoginError(Exception):
    pass


class MFARequiredError(Exception):
    pass


def login(username: str, password: str) -> LoginResult:
    """Orchestrate the end-to-end login flow (config, RSA, MFA detect, login).

    Returns dict with 'id_token' and 'user' keys on success.
    Raises LoginError on failure, MFARequiredError if MFA is needed.
    """
    device_id = get_or_create_device_id()

    try:
        with AuthClient() as client:
            # Step 1: Fetch login configs, check encryptEnabled
            logger.info("Step 1: Fetching login configs...")
            configs_resp = client.get_login_configs()
            if configs_resp.get("code") != 0:
                raise LoginError(
                    f"Failed to get login config: {configs_resp.get('message', 'Unknown error')}"
                )

            login_page_config = configs_resp.get("data", {}).get("loginPageConfig") or {}
            encrypt_enabled = login_page_config.get("encryptEnabled", False)
            logger.info("Step 1: encryptEnabled=%s", encrypt_enabled)

            # Step 2: Fetch RSA public key if needed
            pub_key = ""
            if encrypt_enabled:
                logger.info("Step 2: Fetching RSA public key...")
                pub_key = client.get_public_key()

            # Step 3: Encrypt credentials (replicates LoginActivity.G() lines 1862-1885)
            enc_username = username
            enc_password = password
            if pub_key:
                logger.info("Step 3: Encrypting credentials with RSA")
                raw_enc_user = rsa_encrypt(pub_key, username)
                raw_enc_pass = rsa_encrypt(pub_key, password)
                # Prepend __RSA__ then strip all whitespace (m() method)
                enc_username = re.sub(r"\s", "", "__RSA__" + raw_enc_user)
                enc_password = re.sub(r"\s", "", "__RSA__" + raw_enc_pass)

            # Step 4: MFA detect (h0 callback logic)
            logger.info("Step 4: MFA detect...")
            mfa_resp = client.mfa_detect(enc_username, device_id, enc_password)
            if mfa_resp.get("code") != 0:
                raise LoginError(
                    f"MFA detect failed: {mfa_resp.get('message', 'Unknown error')}"
                )

            mfa_data = mfa_resp.get("data") or {}
            mfa_enabled = mfa_data.get("mfaEnabled", False)
            need_mfa = mfa_data.get("need", False)
            logger.info("Step 4: mfaEnabled=%s, needMfa=%s", mfa_enabled, need_mfa)

            if not mfa_enabled:
                mfa_state = ""
            elif not need_mfa:
                mfa_state = mfa_data.get("state", "")
            else:
                raise MFARequiredError(
                    "MFA is required for this account. Please use the app to complete MFA."
                )

            # Step 5: Password login
            logger.info("Step 5: Performing password login...")
            login_resp = client.password_login(
                enc_username, enc_password, APP_ID, device_id, mfa_state
            )
            logger.info("Step 5: Login response code=%s", login_resp.get("code"))
            if login_resp.get("code") != 0:
                raise LoginError(
                    f"Login failed: {login_resp.get('message', 'Unknown error')}"
                )

            id_token = (login_resp.get("data") or {}).get("idToken")
            if not id_token:
                raise LoginError("Login failed: no idToken in response")
            logger.info("Step 5: Obtained id_token (len=%d)", len(id_token))

            save_session(id_token, username, device_id)

            # Step 6: Fetch user info to verify token (optional)
            logger.info("Step 6: Fetching user info...")
            user_data: UserInfo = {}
            try:
                user_resp = client.get_user_info(id_token)
                user_data = user_resp.get("data") or {}
            except (AuthClientError, httpx.HTTPError) as exc:
                logger.debug("Step 6: user info fetch skipped: %s", exc)

            return {"id_token": id_token, "user": user_data}
    except MFARequiredError:
        raise
    except (AuthClientError, httpx.HTTPError) as exc:
        raise LoginError(str(exc)) from exc
