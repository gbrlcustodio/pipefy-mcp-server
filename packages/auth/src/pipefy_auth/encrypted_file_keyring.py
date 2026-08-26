"""AES-GCM file keyring: rotating session blob stays off the OS keychain.

macOS Keychain holds the create-once wrapping key; Windows stores that key
DPAPI-encrypted as ``wrapping.key``. Every ``set_password`` (login and token
refresh) rewrites AES-GCM ``session.enc`` under ``config_dir()``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import keyring
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from keyring.backend import KeyringBackend
from keyring.compat import properties
from keyring.errors import KeyringError, PasswordDeleteError
from pipefy_infra.config import config_dir

from pipefy_auth.atomic_replace import replace_file_atomically
from pipefy_auth.keychain_choice import SESSION_ENC_FILENAME, WRAPPING_KEY_BYTES
from pipefy_auth.locks import RefreshLockTimeout, file_lock
from pipefy_auth.wrapping_key import WrappingKeyStore, wrapping_key_store_for_platform

_MAGIC = b"PFY1"
_NONCE_BYTES = 12


def seal_session_blob(plaintext: bytes, key: bytes) -> bytes:
    """Return ``PFY1`` + nonce + AES-256-GCM ciphertext (tag included)."""
    if len(key) != WRAPPING_KEY_BYTES:
        raise ValueError(
            f"AES wrapping key must be {WRAPPING_KEY_BYTES} bytes; received {len(key)}"
        )
    nonce = os.urandom(_NONCE_BYTES)
    return _MAGIC + nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def unseal_session_blob(blob: bytes, key: bytes) -> bytes:
    """Decrypt a blob from :func:`seal_session_blob`.

    Raises:
        ValueError: When the magic, length, key, or authentication tag is wrong.
    """
    if len(key) != WRAPPING_KEY_BYTES:
        raise ValueError(
            f"AES wrapping key must be {WRAPPING_KEY_BYTES} bytes; received {len(key)}"
        )
    prefix = blob[: len(_MAGIC)]
    if prefix != _MAGIC:
        raise ValueError(
            f"encrypted session blob magic is {prefix!r}, expected {_MAGIC!r}"
        )
    nonce = blob[len(_MAGIC) : len(_MAGIC) + _NONCE_BYTES]
    ciphertext = blob[len(_MAGIC) + _NONCE_BYTES :]
    if len(nonce) != _NONCE_BYTES or not ciphertext:
        raise ValueError(
            f"encrypted session blob is {len(blob)} bytes; "
            f"need magic + {_NONCE_BYTES}-byte nonce + ciphertext"
        )
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise ValueError(
            "encrypted session blob failed AES-GCM authentication"
        ) from exc


def parse_session_entries(loaded: object, *, path: object) -> dict[str, dict[str, str]]:
    """Parse the JSON map stored in ``session.enc``.

    Args:
        loaded: Decoded JSON root.
        path: Path used in error messages.
    """
    if not isinstance(loaded, dict):
        raise KeyringError(
            f"encrypted session file {path} JSON root is "
            f"{type(loaded).__name__}, expected object"
        )
    parsed: dict[str, dict[str, str]] = {}
    for service, bucket in loaded.items():
        if not isinstance(bucket, dict):
            raise KeyringError(
                f"encrypted session file {path} service {service!r} is "
                f"{type(bucket).__name__}, expected object"
            )
        parsed[str(service)] = {
            str(user): str(secret) for user, secret in bucket.items()
        }
    return parsed


class EncryptedFileKeyring(KeyringBackend):
    """JSON map of ``service -> username -> secret``, AES-GCM sealed on disk."""

    @properties.classproperty
    def priority(self) -> float:
        raise RuntimeError(
            "EncryptedFileKeyring is opt-in via PIPEFY_KEYCHAIN_BACKEND=encrypted"
        )

    def __init__(self, file_path: Path, wrapping_key: WrappingKeyStore) -> None:
        super().__init__()
        self.file_path = str(file_path)
        self._path = file_path
        self._wrapping_key = wrapping_key

    def get_password(self, service: str, username: str) -> str | None:
        entries = self._load_entries()
        if entries is None:
            return None
        return entries.get(service, {}).get(username)

    def set_password(self, service: str, username: str, password: str) -> None:
        try:
            with file_lock(self._path.with_name(self._path.name + ".lock")):
                entries = self._entries_for_write()
                bucket = entries.setdefault(service, {})
                bucket[username] = password
                self._dump_entries(entries)
        except RefreshLockTimeout as exc:
            raise KeyringError(
                f"could not lock encrypted session file {self._path}: {exc}"
            ) from exc

    def delete_password(self, service: str, username: str) -> None:
        try:
            with file_lock(self._path.with_name(self._path.name + ".lock")):
                self._delete_password_locked(service, username)
        except RefreshLockTimeout as exc:
            raise KeyringError(
                f"could not lock encrypted session file {self._path}: {exc}"
            ) from exc

    def _delete_password_locked(self, service: str, username: str) -> None:
        entries = self._load_entries() or {}
        bucket = entries.get(service)
        if bucket is None or username not in bucket:
            raise PasswordDeleteError(
                f"no encrypted session entry for service {service!r} "
                f"username {username!r}"
            )
        del bucket[username]
        if not bucket:
            del entries[service]
        if not entries:
            self._path.unlink(missing_ok=True)
            return
        self._dump_entries(entries)

    def _load_entries(self) -> dict[str, dict[str, str]] | None:
        if not self._path.exists():
            return None
        try:
            key = self._wrapping_key.load()
            if key is None:
                raise KeyringError(
                    f"wrapping key is missing while encrypted session file "
                    f"{self._path} still exists"
                )
            return self._unseal_entries(key)
        except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise KeyringError(
                f"could not read encrypted session file {self._path}: {exc}"
            ) from exc

    def _entries_for_write(self) -> dict[str, dict[str, str]]:
        if not self._path.exists():
            return {}
        key = self._wrapping_key.load()
        if key is None:
            self._path.unlink()
            return {}
        try:
            return self._unseal_entries(key)
        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            KeyringError,
        ):
            return {}

    def _unseal_entries(self, key: bytes) -> dict[str, dict[str, str]]:
        loaded: Any = json.loads(
            unseal_session_blob(self._path.read_bytes(), key).decode("utf-8")
        )
        return parse_session_entries(loaded, path=self._path)

    def _dump_entries(self, entries: dict[str, dict[str, str]]) -> None:
        plaintext = json.dumps(entries, ensure_ascii=False).encode("utf-8")
        blob = seal_session_blob(plaintext, self._wrapping_key.load_or_create())
        try:
            replace_file_atomically(self._path, blob)
        except OSError as exc:
            raise KeyringError(
                f"could not write encrypted session file {self._path}: {exc}"
            ) from exc


def install_encrypted_file_keyring(
    *,
    wrapping_key: WrappingKeyStore | None = None,
    file_path: Path | None = None,
) -> EncryptedFileKeyring:
    """Install :class:`EncryptedFileKeyring` as the process-wide ``keyring`` backend."""
    resolved_dir = config_dir()
    store = wrapping_key or wrapping_key_store_for_platform(config_dir=resolved_dir)
    path = file_path if file_path is not None else resolved_dir / SESSION_ENC_FILENAME
    backend = EncryptedFileKeyring(path, store)
    keyring.set_keyring(backend)
    return backend
