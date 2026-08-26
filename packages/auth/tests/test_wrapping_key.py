"""Create-once wrapping-key persistence (no live Keychain / DPAPI)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from pipefy_auth.atomic_replace import replace_file_atomically
from pipefy_auth.keychain_choice import WRAPPING_KEY_BYTES
from pipefy_auth.wrapping_key import (
    create_once_file_wrapping_key,
    require_persisted_wrapping_key,
)


def test_require_persisted_wrapping_key_raises_when_copy_is_none():
    with pytest.raises(OSError, match="pipefy-wrapping-key"):
        require_persisted_wrapping_key(
            None,
            location="Keychain service 'pipefy-wrapping-key' account 'aes-256-gcm'",
        )


def test_require_persisted_wrapping_key_rejects_wrong_length():
    with pytest.raises(OSError, match="expected 32"):
        require_persisted_wrapping_key(b"short", location="/tmp/wrapping.key")


def test_require_persisted_wrapping_key_returns_persisted_bytes():
    key = os.urandom(WRAPPING_KEY_BYTES)
    assert require_persisted_wrapping_key(key, location="mem") == key


def test_create_once_prefers_existing_file_over_local_mint(tmp_path: Path):
    path = tmp_path / "wrapping.key"
    disk_key = os.urandom(WRAPPING_KEY_BYTES)
    path.write_bytes(b"protected")

    def write_protected(_minted: bytes) -> None:
        raise AssertionError("must not write when the wrapping file already exists")

    result = create_once_file_wrapping_key(
        cached=None,
        path=path,
        read_unprotected=lambda: disk_key,
        write_protected=write_protected,
        mint=lambda: os.urandom(WRAPPING_KEY_BYTES),
    )
    assert result == disk_key


def test_create_once_prefers_file_that_appears_before_write(tmp_path: Path):
    path = tmp_path / "wrapping.key"
    disk_key = os.urandom(WRAPPING_KEY_BYTES)

    def mint() -> bytes:
        path.write_bytes(b"protected")
        return os.urandom(WRAPPING_KEY_BYTES)

    def write_protected(_minted: bytes) -> None:
        raise AssertionError("must not overwrite a wrapping file that appeared")

    result = create_once_file_wrapping_key(
        cached=None,
        path=path,
        read_unprotected=lambda: disk_key,
        write_protected=write_protected,
        mint=mint,
    )
    assert result == disk_key


def test_create_once_caches_bytes_read_back_after_write(tmp_path: Path):
    path = tmp_path / "wrapping.key"
    disk_key = os.urandom(WRAPPING_KEY_BYTES)

    def write_protected(minted: bytes) -> None:
        path.write_bytes(minted)

    result = create_once_file_wrapping_key(
        cached=None,
        path=path,
        read_unprotected=lambda: disk_key,
        write_protected=write_protected,
        mint=lambda: os.urandom(WRAPPING_KEY_BYTES),
    )
    assert result == disk_key


def test_replace_file_atomically_does_not_leave_a_shared_tmp_name(tmp_path: Path):
    path = tmp_path / "session.enc"
    replace_file_atomically(path, b"one")
    replace_file_atomically(path, b"two")
    assert path.read_bytes() == b"two"
    assert not (tmp_path / "session.enc.tmp").exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="Security.framework CDLL")
def test_darwin_load_or_create_raises_when_copy_returns_none_after_add(
    monkeypatch: pytest.MonkeyPatch,
):
    from pipefy_auth.wrapping_key_darwin import DarwinKeychainWrappingKey

    monkeypatch.setattr(
        "pipefy_auth.wrapping_key_darwin._copy_wrapping_key", lambda: None
    )
    monkeypatch.setattr(
        "pipefy_auth.wrapping_key_darwin._add_wrapping_key", lambda key: None
    )
    with pytest.raises(OSError, match="pipefy-wrapping-key"):
        DarwinKeychainWrappingKey().load_or_create()
