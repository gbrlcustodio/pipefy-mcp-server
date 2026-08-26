"""OS-protected wrapping keys for the encrypted session file.

The AES-256-GCM data-encryption key is created once. Token refresh rewrites
only the ciphertext file, never this key — that is what stops macOS Keychain
ACL prompts on every ``python3.xx`` process.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pipefy_auth.keychain_choice import (
    ENCRYPTED_KEYCHAIN_PLATFORMS,
    WRAPPING_KEY_BYTES,
    WRAPPING_KEY_FILENAME,
    encrypted_unsupported_platform_message,
)


class WrappingKeyStore(Protocol):
    """Load (or mint) the 32-byte AES wrapping key."""

    def load(self) -> bytes | None: ...

    def load_or_create(self) -> bytes: ...


def require_persisted_wrapping_key(persisted: bytes | None, *, location: str) -> bytes:
    """Return the wrapping key read back from durable storage after create.

    Args:
        persisted: Bytes copied from Keychain / the DPAPI file after mint.
        location: User-facing description of that store (service/account or path).
    """
    if persisted is None:
        raise OSError(f"wrapping key was not readable after create at {location}")
    if len(persisted) != WRAPPING_KEY_BYTES:
        raise OSError(
            f"wrapping key at {location} has {len(persisted)} bytes, "
            f"expected {WRAPPING_KEY_BYTES}"
        )
    return persisted


def create_once_file_wrapping_key(
    *,
    cached: bytes | None,
    path: Path,
    read_unprotected: Callable[[], bytes],
    write_protected: Callable[[bytes], None],
    mint: Callable[[], bytes],
) -> bytes:
    """Create-once file wrapping key: prefer bytes already on disk over a local mint.

    Args:
        cached: In-process key from a previous successful load.
        path: Protected wrapping-key file.
        read_unprotected: Decrypt the file's current contents.
        write_protected: Persist a newly minted key.
        mint: Produce 32 random bytes (not stored until ``write_protected``).
    """
    if cached is not None:
        return cached
    location = str(path)
    if path.exists():
        return require_persisted_wrapping_key(read_unprotected(), location=location)
    minted = mint()
    if path.exists():
        return require_persisted_wrapping_key(read_unprotected(), location=location)
    write_protected(minted)
    return require_persisted_wrapping_key(read_unprotected(), location=location)


@dataclass
class InMemoryWrappingKey:
    """Test double: a wrapping key that never touches the OS.

    ``key`` is ``None`` until :meth:`load_or_create` mints one, so a stranded
    ciphertext can be detected without accidentally creating a wrapping key.
    """

    key: bytes | None = None

    def load(self) -> bytes | None:
        if self.key is None:
            return None
        if len(self.key) != WRAPPING_KEY_BYTES:
            raise ValueError(
                f"wrapping key must be {WRAPPING_KEY_BYTES} bytes; "
                f"received {len(self.key)}"
            )
        return self.key

    def load_or_create(self) -> bytes:
        if self.key is None:
            self.key = os.urandom(WRAPPING_KEY_BYTES)
        if len(self.key) != WRAPPING_KEY_BYTES:
            raise ValueError(
                f"wrapping key must be {WRAPPING_KEY_BYTES} bytes; "
                f"received {len(self.key)}"
            )
        return self.key


def wrapping_key_store_for_platform(*, config_dir: Path) -> WrappingKeyStore:
    """Return the OS wrapping-key store for this process.

    Raises:
        ValueError: When ``sys.platform`` is not in
            :data:`ENCRYPTED_KEYCHAIN_PLATFORMS`. The message matches the
            settings-boundary rejection so a leaked call site cannot dump a
            traceback.
    """
    if sys.platform not in ENCRYPTED_KEYCHAIN_PLATFORMS:
        raise ValueError(encrypted_unsupported_platform_message(sys.platform))
    if sys.platform == "darwin":
        from pipefy_auth.wrapping_key_darwin import DarwinKeychainWrappingKey

        return DarwinKeychainWrappingKey()
    from pipefy_auth.wrapping_key_windows import WindowsDpapiWrappingKey

    return WindowsDpapiWrappingKey(config_dir / WRAPPING_KEY_FILENAME)
