import json
import uuid

from cli.config import DEVICE_FILE, TOKEN_FILE


def get_or_create_device_id() -> str:
    """Persist a UUID4 as the device identifier across sessions."""
    if DEVICE_FILE.exists():
        return json.loads(DEVICE_FILE.read_text())["device_id"]
    device_id = str(uuid.uuid4())
    DEVICE_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEVICE_FILE.write_text(json.dumps({"device_id": device_id}))
    return device_id


def save_session(id_token: str, username: str, device_id: str) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(
        json.dumps({"id_token": id_token, "username": username, "device_id": device_id})
    )


def load_session() -> dict | None:
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return None


def clear_session() -> None:
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
