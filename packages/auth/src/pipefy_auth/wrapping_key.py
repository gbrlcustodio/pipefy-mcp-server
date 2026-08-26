"""OS-protected wrapping keys for the encrypted session file.

The AES-256-GCM data-encryption key is created once. Token refresh rewrites
only the ciphertext file, never this key — that is what stops macOS Keychain
ACL prompts on every ``python3.xx`` process.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pipefy_auth.keychain_choice import (
    WRAPPING_KEY_BYTES,
    WRAPPING_KEY_FILENAME,
    encrypted_unsupported_platform_message,
)


class WrappingKeyStore(Protocol):
    """Load (or mint) the 32-byte AES wrapping key."""

    def load_or_create(self) -> bytes: ...


@dataclass
class InMemoryWrappingKey:
    """Test double: a fixed key that never touches the OS."""

    key: bytes = field(default_factory=lambda: os.urandom(WRAPPING_KEY_BYTES))

    def load_or_create(self) -> bytes:
        if len(self.key) != WRAPPING_KEY_BYTES:
            raise ValueError(
                f"wrapping key must be {WRAPPING_KEY_BYTES} bytes; "
                f"received {len(self.key)}"
            )
        return self.key


def wrapping_key_store_for_platform(*, config_dir: Path) -> WrappingKeyStore:
    """Return the OS wrapping-key store for this process.

    Raises:
        ValueError: When ``sys.platform`` is not macOS or Windows. The message
            matches the settings-boundary rejection so a leaked call site
            cannot dump a traceback.
    """
    if sys.platform == "darwin":
        # Security.framework CDLLs at import; cannot load on Linux CI.
        from pipefy_auth.wrapping_key_darwin import DarwinKeychainWrappingKey

        return DarwinKeychainWrappingKey()
    if sys.platform == "win32":
        # crypt32.CryptProtectData is Windows-only.
        from pipefy_auth.wrapping_key_windows import WindowsDpapiWrappingKey

        return WindowsDpapiWrappingKey(config_dir / WRAPPING_KEY_FILENAME)
    raise ValueError(encrypted_unsupported_platform_message(sys.platform))
