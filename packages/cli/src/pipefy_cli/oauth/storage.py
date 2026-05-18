"""Persist the refresh-token-bearing session in the OS keychain via ``keyring``.

Single active session per ``(issuer_host, client_id)`` tuple. The keychain entry
holds a small JSON blob (refresh + access token + minimal metadata). The
short-lived access token is included so a single login is usable immediately;
the long-lived refresh token is the durable credential.

``keyring`` is imported lazily inside each function so that merely importing
this module (which happens at CLI startup via the ``auth`` subcommand) does not
pay the ~30-80ms backend-discovery cost on every ``pipefy`` invocation.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

_SERVICE = "pipefy-cli"


@dataclass(frozen=True)
class StoredSession:
    """Persisted session shape (JSON-serialised under one keychain key)."""

    issuer: str
    client_id: str
    access_token: str
    refresh_token: str
    token_type: str
    obtained_at: int
    expires_in: int | None
    refresh_expires_in: int | None
    scope: str | None
    id_token: str | None


def _issuer_host(issuer_url: str) -> str:
    host = urlparse(issuer_url).hostname
    if not host:
        raise ValueError(f"Cannot derive host from issuer URL: {issuer_url!r}")
    return host.lower()


def keychain_key(issuer_url: str, client_id: str) -> str:
    """Return the keychain account name for this issuer + client tuple."""
    return f"{_issuer_host(issuer_url)}|{client_id}"


def store_session(
    *,
    issuer: str,
    client_id: str,
    token_response: dict[str, object],
) -> StoredSession:
    """Persist a token response in the OS keychain. Returns the stored shape.

    Raises:
        KeyringError: When the keychain backend rejects the write. Caller should
            surface a user-facing message (e.g. headless Linux without a Secret
            Service daemon).
        ValueError: When ``token_response`` is missing required fields.
    """
    import keyring

    try:
        access_token = str(token_response["access_token"])
        refresh_token = str(token_response["refresh_token"])
    except KeyError as exc:
        raise ValueError(
            f"Token response is missing required field: {exc.args[0]!r}"
        ) from exc

    session = StoredSession(
        issuer=issuer,
        client_id=client_id,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=str(token_response.get("token_type") or "Bearer"),
        obtained_at=int(time.time()),
        expires_in=_optional_int(token_response.get("expires_in")),
        refresh_expires_in=_optional_int(token_response.get("refresh_expires_in")),
        scope=_optional_str(token_response.get("scope")),
        id_token=_optional_str(token_response.get("id_token")),
    )
    keyring.set_password(
        _SERVICE, keychain_key(issuer, client_id), json.dumps(asdict(session))
    )
    return session


def load_session(*, issuer: str, client_id: str) -> StoredSession | None:
    """Return the stored session for this issuer + client, or ``None`` if absent."""
    import keyring
    from keyring.errors import KeyringError

    try:
        blob = keyring.get_password(_SERVICE, keychain_key(issuer, client_id))
    except KeyringError:
        return None
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    try:
        return StoredSession(**data)
    except TypeError:
        return None


def delete_session(*, issuer: str, client_id: str) -> bool:
    """Remove the stored session. Returns True if an entry was present."""
    import keyring
    from keyring.errors import KeyringError, PasswordDeleteError

    try:
        keyring.delete_password(_SERVICE, keychain_key(issuer, client_id))
    except PasswordDeleteError:
        return False
    except KeyringError:
        return False
    return True


def keychain_backend_name() -> str:
    """Short identifier for the active keyring backend (diagnostics)."""
    import keyring
    from keyring.errors import KeyringError

    try:
        backend = keyring.get_keyring()
    except KeyringError as exc:
        return f"unavailable ({exc})"
    return backend.__class__.__name__


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "StoredSession",
    "delete_session",
    "keychain_backend_name",
    "keychain_key",
    "load_session",
    "store_session",
]
