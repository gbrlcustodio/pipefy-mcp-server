"""Canonical names for the stored-session keyring backend.

``AuthSettings.keychain_backend`` and ``configure_keychain_backend`` share this
Literal so a new value cannot land on one side only.
"""

from __future__ import annotations

from typing import Literal

KeychainBackendChoice = Literal["auto", "file", "encrypted"]

ENCRYPTED_KEYCHAIN_PLATFORMS = frozenset({"darwin", "win32"})
SESSION_ENC_FILENAME = "session.enc"
WRAPPING_KEY_FILENAME = "wrapping.key"
WRAPPING_KEYCHAIN_SERVICE = "pipefy-wrapping-key"
WRAPPING_KEYCHAIN_ACCOUNT = "aes-256-gcm"
WRAPPING_KEY_BYTES = 32


def encrypted_unsupported_platform_message(platform: str) -> str:
    """User-facing rejection when ``encrypted`` is selected off macOS/Windows."""
    return (
        "PIPEFY_KEYCHAIN_BACKEND=encrypted is only supported on macOS and "
        f"Windows; this platform is {platform!r}. Use auto or file."
    )
