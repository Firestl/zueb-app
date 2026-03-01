"""
Session and device identity persistence for the ZUEB CLI.

Files written under ~/.config/zueb-cli/:
  device.json  — {"device_id": "<uuid4>"}
                  Created once on first login; reused on every subsequent login
                  so the server sees a consistent device fingerprint.
  session.json — {"id_token": "...", "username": "...", "device_id": "..."}
                  Written after a successful login; read by all commands that
                  require authentication.
"""

import json
import uuid

from cli.config import DEVICE_FILE, TOKEN_FILE


def get_or_create_device_id() -> str:
    """Persist a UUID4 as the device identifier across sessions.

    On the first call, generates a new UUID4 and writes it to DEVICE_FILE.
    On subsequent calls, returns the previously stored value.
    This ensures the same device_id is sent on every login attempt,
    which is required by the Supwisdom SSO to track device registrations.
    """
    if DEVICE_FILE.exists():
        return json.loads(DEVICE_FILE.read_text())["device_id"]
    device_id = str(uuid.uuid4())
    DEVICE_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEVICE_FILE.write_text(json.dumps({"device_id": device_id}))
    return device_id


def save_session(id_token: str, username: str, device_id: str) -> None:
    """Persist the active session to TOKEN_FILE.

    Overwrites any previously saved session.  All three fields are required
    because downstream commands (schedule, attendance) need id_token, and
    the `status` command displays username + device_id.
    """
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(
        json.dumps({"id_token": id_token, "username": username, "device_id": device_id})
    )


def load_session() -> dict | None:
    """Load the saved session from TOKEN_FILE.

    Returns the session dict, or None if the user is not logged in.
    Callers should check for None and prompt the user to run `login`.
    """
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return None


def clear_session() -> None:
    """Delete the saved session file, effectively logging out.

    Silently does nothing if no session file exists.
    """
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
