"""PKCE (RFC 7636) verifier and S256 challenge helpers."""

from __future__ import annotations

import base64
import hashlib
import secrets

_MIN_VERIFIER_LEN = 43
_MAX_VERIFIER_LEN = 128


def generate_verifier(length: int = 64) -> str:
    """Return a high-entropy code verifier (43-128 chars, URL-safe charset)."""
    if not _MIN_VERIFIER_LEN <= length <= _MAX_VERIFIER_LEN:
        raise ValueError(
            f"verifier length must be between {_MIN_VERIFIER_LEN} and "
            f"{_MAX_VERIFIER_LEN}; got {length}"
        )
    return secrets.token_urlsafe(length)[:length]


def challenge_from_verifier(verifier: str) -> str:
    """Compute the S256 code challenge for ``verifier`` (RFC 7636 §4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


__all__ = ["challenge_from_verifier", "generate_verifier"]
