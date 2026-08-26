"""AES-GCM file keyring and ``configure_keychain_backend('encrypted')``."""

from __future__ import annotations

import os
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
    ring = EncryptedFileKeyring(path, InMemoryWrappingKey())
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
