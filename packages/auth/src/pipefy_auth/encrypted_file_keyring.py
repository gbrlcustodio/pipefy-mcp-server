"""AES-GCM file keyring: rotating session blob stays off the OS keychain.

macOS Keychain / Windows Credential Manager hold only the create-once wrapping
key (see ``wrapping_key``). Every ``set_password`` (login and token refresh)
rewrites ``session.enc`` under ``config_dir()``.
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

from pipefy_auth.keychain_choice import SESSION_ENC_FILENAME, WRAPPING_KEY_BYTES
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


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    if os.name != "nt":
        tmp.chmod(0o600)
    tmp.replace(path)
    if os.name != "nt":
        path.chmod(0o600)


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
        entries = self._load_entries() or {}
        bucket = entries.setdefault(service, {})
        bucket[username] = password
        self._dump_entries(entries)

    def delete_password(self, service: str, username: str) -> None:
        entries = self._load_entries() or {}
        bucket = entries.get(service)
        if bucket is None or username not in bucket:
            raise PasswordDeleteError(
                f"no encrypted session entry for service {service!r} username {username!r}"
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
            plaintext = unseal_session_blob(
                self._path.read_bytes(), self._wrapping_key.load_or_create()
            )
            loaded: Any = json.loads(plaintext.decode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise KeyringError(
                f"could not read encrypted session file {self._path}: {exc}"
            ) from exc
        if not isinstance(loaded, dict):
            raise KeyringError(
                f"encrypted session file {self._path} JSON root is "
                f"{type(loaded).__name__}, expected object"
            )
        return loaded

    def _dump_entries(self, entries: dict[str, dict[str, str]]) -> None:
        plaintext = json.dumps(entries, ensure_ascii=False).encode("utf-8")
        blob = seal_session_blob(plaintext, self._wrapping_key.load_or_create())
        try:
            _atomic_write(self._path, blob)
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
