"""Tests for cli/auth/token.py — 文件 I/O 隔离测试，使用 tmp_path + monkeypatch。"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from cli.auth.token import (
    clear_session,
    get_or_create_device_id,
    load_session,
    save_session,
)


# ---------------------------------------------------------------------------
# get_or_create_device_id
# ---------------------------------------------------------------------------


    # get_or_create_device_id(): 首次调用时创建文件并持久化新的 device_id。
def test_create_device_id_when_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """文件不存在时应生成新 UUID 并写入 DEVICE_FILE。"""
    device_file = tmp_path / "device.json"
    monkeypatch.setattr("cli.auth.token.DEVICE_FILE", device_file)

    result = get_or_create_device_id()

    assert device_file.exists()
    stored = json.loads(device_file.read_text())
    assert stored["device_id"] == result
    # UUID4 格式校验（8-4-4-4-12）
    assert len(result) == 36


    # get_or_create_device_id(): 设备文件父目录不存在时应自动创建目录树。
def test_create_device_id_creates_parent_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """父目录不存在时 get_or_create_device_id 应自动递归创建。"""
    device_file = tmp_path / "nested" / "config" / "device.json"
    monkeypatch.setattr("cli.auth.token.DEVICE_FILE", device_file)

    get_or_create_device_id()

    assert device_file.exists()


    # get_or_create_device_id(): 已有设备文件时复用原 device_id。
def test_load_existing_device_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """文件已存在时应直接返回已有 device_id，不生成新 UUID。"""
    device_file = tmp_path / "device.json"
    device_file.write_text(json.dumps({"device_id": "existing-uuid-123"}))
    monkeypatch.setattr("cli.auth.token.DEVICE_FILE", device_file)

    result = get_or_create_device_id()

    assert result == "existing-uuid-123"


    # get_or_create_device_id(): monkeypatch uuid4 后可验证生成值的确定性。
def test_device_id_deterministic_uuid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """monkeypatch uuid4 后，生成的 device_id 与预期固定值一致。"""
    device_file = tmp_path / "device.json"
    monkeypatch.setattr("cli.auth.token.DEVICE_FILE", device_file)

    fixed_uuid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    monkeypatch.setattr("cli.auth.token.uuid.uuid4", lambda: fixed_uuid)

    result = get_or_create_device_id()

    assert result == "12345678-1234-5678-1234-567812345678"


# ---------------------------------------------------------------------------
# save_session
# ---------------------------------------------------------------------------


    # save_session(): 将 token/username/device_id 三字段写入 session 文件。
def test_save_session_writes_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """save_session 应将三个字段写入 TOKEN_FILE，内容可被正确解析。"""
    token_file = tmp_path / "session.json"
    monkeypatch.setattr("cli.auth.token.TOKEN_FILE", token_file)

    save_session("jwt-token-abc", "alice", "dev-001")

    data = json.loads(token_file.read_text())
    assert data["id_token"] == "jwt-token-abc"
    assert data["username"] == "alice"
    assert data["device_id"] == "dev-001"


    # save_session(): 目标目录不存在时先创建目录再写文件。
def test_save_session_creates_parent_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """父目录不存在时 save_session 应自动创建目录。"""
    token_file = tmp_path / "new_dir" / "sub" / "session.json"
    monkeypatch.setattr("cli.auth.token.TOKEN_FILE", token_file)

    save_session("tok", "user", "dev")

    assert token_file.exists()


    # save_session(): 重复保存时应覆盖旧内容，而不是追加。
def test_save_session_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """再次调用 save_session 应覆盖已有数据，以新值为准。"""
    token_file = tmp_path / "session.json"
    monkeypatch.setattr("cli.auth.token.TOKEN_FILE", token_file)

    save_session("tok1", "user1", "dev1")
    save_session("tok2", "user2", "dev2")

    data = json.loads(token_file.read_text())
    assert data["id_token"] == "tok2"
    assert data["username"] == "user2"


# ---------------------------------------------------------------------------
# load_session
# ---------------------------------------------------------------------------


    # load_session(): 文件存在时返回完整 SessionData。
def test_load_session_returns_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """文件存在时 load_session 应返回完整的 SessionData 对象。"""
    token_file = tmp_path / "session.json"
    token_file.write_text(
        json.dumps({"id_token": "jwt-xyz", "username": "bob", "device_id": "d-99"})
    )
    monkeypatch.setattr("cli.auth.token.TOKEN_FILE", token_file)

    result = load_session()

    assert result is not None
    assert result["id_token"] == "jwt-xyz"
    assert result["username"] == "bob"
    assert result["device_id"] == "d-99"


    # load_session(): 缺少 session 文件时返回 None。
def test_load_session_no_file_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """文件不存在时 load_session 应返回 None（未登录状态）。"""
    token_file = tmp_path / "nonexistent.json"
    monkeypatch.setattr("cli.auth.token.TOKEN_FILE", token_file)

    assert load_session() is None


# ---------------------------------------------------------------------------
# clear_session
# ---------------------------------------------------------------------------


    # clear_session(): 已存在 session 文件时将其删除。
def test_clear_session_deletes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """clear_session 应删除 TOKEN_FILE，使后续 load_session 返回 None。"""
    token_file = tmp_path / "session.json"
    token_file.write_text(json.dumps({"id_token": "x", "username": "u", "device_id": "d"}))
    monkeypatch.setattr("cli.auth.token.TOKEN_FILE", token_file)

    clear_session()

    assert not token_file.exists()


    # clear_session(): 文件不存在时静默 no-op。
def test_clear_session_no_file_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """文件不存在时 clear_session 应静默返回，不抛出任何异常。"""
    token_file = tmp_path / "nonexistent.json"
    monkeypatch.setattr("cli.auth.token.TOKEN_FILE", token_file)

    clear_session()  # 不应抛出异常
