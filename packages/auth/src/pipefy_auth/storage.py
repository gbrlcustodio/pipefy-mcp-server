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
from typing import Literal
from urllib.parse import urlparse

from pipefy_infra.coerce import optional_int, optional_str

from pipefy_auth.responses import TokenResponse

_SERVICE = "pipefy"
_KEYRING_FILENAME = "keyring.cfg"


def configure_keychain_backend(choice: Literal["auto", "file"]) -> None:
    """Apply the requested keyring backend before any session read or write.

    Idempotent: safe to call multiple times; the second ``"file"`` call
    replaces the previous file backend with one pointing at the same path.

    Args:
        choice: ``"auto"`` is a no-op and preserves ``keyring``'s built-in
            backend-discovery default. ``"file"`` swaps to
            :class:`keyrings.alt.file.PlaintextKeyring` writing under
            ``pipefy_infra.config.config_dir() / "keyring.cfg"``; the file stores
            credentials in plaintext on disk and is intended for headless
            Linux or CI runners where the OS keychain is unavailable.
    """
    if choice == "auto":
        return
    import keyring
    from keyrings.alt.file import PlaintextKeyring
    from pipefy_infra.config import config_dir

    backend = PlaintextKeyring()
    backend.file_path = str(config_dir() / _KEYRING_FILENAME)
    keyring.set_keyring(backend)


class SessionDeleteError(RuntimeError):
    """Keychain backend rejected the delete (distinct from "entry absent")."""


@dataclass(frozen=True)
class StoredSession:
    """Persisted session: identity + write timestamp + the token response.

    The token fields are bundled in :class:`TokenResponse` so there is one
    source of truth for the OAuth wire shape. On-disk JSON destructures the
    token attributes into the parent object (legacy flat shape) so existing
    keychain entries continue to load.
    """

    issuer: str
    client_id: str
    obtained_at: int
    token: TokenResponse


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
    token: TokenResponse,
) -> StoredSession:
    """Persist a token response in the OS keychain. Returns the stored shape.

    Raises:
        KeyringError: When the keychain backend rejects the write. Caller should
            surface a user-facing message (e.g. headless Linux without a Secret
            Service daemon).
    """
    import keyring

    session = StoredSession(
        issuer=issuer,
        client_id=client_id,
        obtained_at=int(time.time()),
        token=token,
    )
    keyring.set_password(
        _SERVICE, keychain_key(issuer, client_id), json.dumps(_session_to_blob(session))
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
    if not isinstance(data, dict):
        return None
    return _session_from_blob(data)


def delete_session(*, issuer: str, client_id: str) -> bool:
    """Remove the stored session. Returns True if an entry was present.

    Raises:
        SessionDeleteError: When the keychain backend rejects the operation
            (distinct from "no entry to delete"). The local credential may
            still exist; callers should surface a user-facing error rather
            than claim a successful sign-out.
    """
    import keyring
    from keyring.errors import KeyringError, PasswordDeleteError

    try:
        keyring.delete_password(_SERVICE, keychain_key(issuer, client_id))
    except PasswordDeleteError:
        return False
    except KeyringError as exc:
        raise SessionDeleteError(str(exc)) from exc
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


def _session_to_blob(session: StoredSession) -> dict[str, object]:
    """Flatten a ``StoredSession`` into the on-disk JSON shape.

    The token-response fields are destructured into the parent object so the
    JSON layout matches the pre-bundle format. Legacy keychain entries written
    under that layout continue to load via :func:`_session_from_blob`.
    """
    return {
        "issuer": session.issuer,
        "client_id": session.client_id,
        "obtained_at": session.obtained_at,
        **asdict(session.token),
    }


def _session_from_blob(data: dict[str, object]) -> StoredSession | None:
    """Rebuild a ``StoredSession`` from the flat on-disk JSON shape."""
    try:
        token = TokenResponse(
            access_token=str(data["access_token"]),
            refresh_token=str(data["refresh_token"]),
            token_type=str(data["token_type"]),
            expires_in=optional_int(data.get("expires_in")),
            refresh_expires_in=optional_int(data.get("refresh_expires_in")),
            scope=optional_str(data.get("scope")),
            id_token=optional_str(data.get("id_token")),
        )
        return StoredSession(
            issuer=str(data["issuer"]),
            client_id=str(data["client_id"]),
            obtained_at=int(data["obtained_at"]),  # type: ignore[arg-type]
            token=token,
        )
    except (KeyError, TypeError, ValueError):
        return None


__all__ = [
    "SessionDeleteError",
    "StoredSession",
    "configure_keychain_backend",
    "delete_session",
    "keychain_backend_name",
    "keychain_key",
    "load_session",
    "store_session",
]
