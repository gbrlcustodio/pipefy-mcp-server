"""AES-GCM file keyring and ``configure_keychain_backend('encrypted')``."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import keyring
import pytest
from keyring.errors import KeyringError, PasswordDeleteError

from pipefy_auth.encrypted_file_keyring import (
    EncryptedFileKeyring,
    install_encrypted_file_keyring,
    seal_session_blob,
    unseal_session_blob,
)
from pipefy_auth.keychain_choice import SESSION_ENC_FILENAME, WRAPPING_KEY_BYTES
from pipefy_auth.storage import configure_keychain_backend
from pipefy_auth.wrapping_key import (
    InMemoryWrappingKey,
    wrapping_key_store_for_platform,
)


@pytest.fixture
def _isolated_keyring():
    original = keyring.get_keyring()
    yield
    keyring.set_keyring(original)


def test_seal_round_trips_and_wrong_key_fails():
    key = os.urandom(WRAPPING_KEY_BYTES)
    blob = seal_session_blob(b"hello", key)
    assert blob.startswith(b"PFY1")
    assert unseal_session_blob(blob, key) == b"hello"
    with pytest.raises(ValueError, match="AES-GCM authentication"):
        unseal_session_blob(blob, os.urandom(WRAPPING_KEY_BYTES))


def test_unseal_rejects_bad_magic():
    key = os.urandom(WRAPPING_KEY_BYTES)
    with pytest.raises(ValueError, match="magic"):
        unseal_session_blob(b"XXXX" + b"\x00" * 20, key)


def test_encrypted_file_keyring_round_trips_across_instances(tmp_path: Path):
    wrap = InMemoryWrappingKey()
    path = tmp_path / SESSION_ENC_FILENAME
    writer = EncryptedFileKeyring(path, wrap)
    reader = EncryptedFileKeyring(path, wrap)
    writer.set_password("pipefy", "acct", "secret")
    writer.set_password("pipefy", "acct", "rotated")
    assert reader.get_password("pipefy", "acct") == "rotated"
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_encrypted_file_keyring_missing_entry_is_none_and_delete_raises(
    tmp_path: Path,
):
    ring = EncryptedFileKeyring(tmp_path / SESSION_ENC_FILENAME, InMemoryWrappingKey())
    assert ring.get_password("pipefy", "acct") is None
    with pytest.raises(PasswordDeleteError, match="pipefy"):
        ring.delete_password("pipefy", "acct")


def test_encrypted_file_keyring_delete_removes_file_when_empty(tmp_path: Path):
    path = tmp_path / SESSION_ENC_FILENAME
    ring = EncryptedFileKeyring(path, InMemoryWrappingKey())
    ring.set_password("pipefy", "acct", "secret")
    assert path.exists()
    ring.delete_password("pipefy", "acct")
    assert not path.exists()


def test_corrupt_session_file_raises_keyring_error(tmp_path: Path):
    path = tmp_path / SESSION_ENC_FILENAME
    path.write_bytes(b"not-ciphertext")
    ring = EncryptedFileKeyring(path, InMemoryWrappingKey(key=os.urandom(32)))
    with pytest.raises(KeyringError, match="could not read"):
        ring.get_password("pipefy", "acct")


def test_configure_encrypted_installs_file_keyring(
    _isolated_keyring, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(
        "pipefy_auth.encrypted_file_keyring.wrapping_key_store_for_platform",
        lambda config_dir: InMemoryWrappingKey(),
    )
    configure_keychain_backend("encrypted")
    backend = keyring.get_keyring()
    assert isinstance(backend, EncryptedFileKeyring)
    assert backend.file_path == str(tmp_path / "pipefy" / SESSION_ENC_FILENAME)
    keyring.set_password("pipefy", "user", "secret-value")
    assert keyring.get_password("pipefy", "user") == "secret-value"


def test_install_encrypted_is_idempotent(
    _isolated_keyring, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    wrap = InMemoryWrappingKey()
    monkeypatch.setattr(
        "pipefy_auth.encrypted_file_keyring.wrapping_key_store_for_platform",
        lambda config_dir: wrap,
    )
    first = install_encrypted_file_keyring()
    second = install_encrypted_file_keyring()
    assert isinstance(first, EncryptedFileKeyring)
    assert isinstance(second, EncryptedFileKeyring)
    assert first.file_path == second.file_path


def test_wrapping_key_factory_rejects_linux(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr("pipefy_auth.wrapping_key.sys.platform", "linux")
    with pytest.raises(ValueError, match="only supported on macOS and Windows"):
        wrapping_key_store_for_platform(config_dir=tmp_path)


def test_set_password_overwrites_unreadable_session_file(tmp_path: Path):
    path = tmp_path / SESSION_ENC_FILENAME
    path.write_bytes(b"not-ciphertext")
    ring = EncryptedFileKeyring(path, InMemoryWrappingKey())
    ring.set_password("pipefy", "acct", "recovered")
    assert ring.get_password("pipefy", "acct") == "recovered"


def test_set_password_overwrites_session_sealed_with_a_different_wrapping_key(
    tmp_path: Path,
):
    path = tmp_path / SESSION_ENC_FILENAME
    EncryptedFileKeyring(path, InMemoryWrappingKey(key=os.urandom(32))).set_password(
        "pipefy", "acct", "old"
    )
    ring = EncryptedFileKeyring(path, InMemoryWrappingKey(key=os.urandom(32)))
    ring.set_password("pipefy", "acct", "new")
    assert ring.get_password("pipefy", "acct") == "new"


def test_get_password_does_not_mint_wrapping_key_when_session_file_exists(
    tmp_path: Path,
):
    path = tmp_path / SESSION_ENC_FILENAME
    path.write_bytes(b"not-ciphertext")
    wrap = InMemoryWrappingKey()
    ring = EncryptedFileKeyring(path, wrap)
    with pytest.raises(KeyringError, match="wrapping key is missing"):
        ring.get_password("pipefy", "acct")
    assert wrap.load() is None


def test_set_password_unlinks_stranded_file_before_minting_wrapping_key(
    tmp_path: Path,
):
    path = tmp_path / SESSION_ENC_FILENAME
    path.write_bytes(b"not-ciphertext")
    wrap = InMemoryWrappingKey()
    ring = EncryptedFileKeyring(path, wrap)
    ring.set_password("pipefy", "acct", "fresh")
    assert wrap.load() is not None
    assert ring.get_password("pipefy", "acct") == "fresh"


def test_get_password_rejects_non_dict_service_bucket(tmp_path: Path):
    wrap = InMemoryWrappingKey()
    key = wrap.load_or_create()
    path = tmp_path / SESSION_ENC_FILENAME
    path.write_bytes(
        seal_session_blob(json.dumps({"pipefy": ["not-a-map"]}).encode(), key)
    )
    ring = EncryptedFileKeyring(path, wrap)
    with pytest.raises(KeyringError, match="expected object"):
        ring.get_password("pipefy", "acct")


def test_sequential_set_password_keeps_both_usernames(tmp_path: Path):
    ring = EncryptedFileKeyring(tmp_path / SESSION_ENC_FILENAME, InMemoryWrappingKey())
    ring.set_password("pipefy", "alice", "secret-a")
    ring.set_password("pipefy", "bob", "secret-b")
    assert ring.get_password("pipefy", "alice") == "secret-a"
    assert ring.get_password("pipefy", "bob") == "secret-b"


def test_concurrent_set_password_keeps_both_usernames(tmp_path: Path):
    ring = EncryptedFileKeyring(tmp_path / SESSION_ENC_FILENAME, InMemoryWrappingKey())
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def write(username: str, secret: str) -> None:
        try:
            barrier.wait()
            ring.set_password("pipefy", username, secret)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=write, args=("alice", "secret-a")),
        threading.Thread(target=write, args=("bob", "secret-b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert ring.get_password("pipefy", "alice") == "secret-a"
    assert ring.get_password("pipefy", "bob") == "secret-b"
    assert not (tmp_path / "session.enc.tmp").exists()
