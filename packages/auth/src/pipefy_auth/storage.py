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

import time
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StrictInt,
    StrictStr,
    ValidationError,
    model_serializer,
    model_validator,
)

from pipefy_auth.responses import TokenResponse

_SERVICE = "pipefy"
_KEYRING_FILENAME = "keyring.cfg"
_TOKEN_FIELDS: frozenset[str] = frozenset(TokenResponse.model_fields.keys())


def configure_keychain_backend(choice: Literal["auto", "file"]) -> None:
    """Apply the requested keyring backend before any session read or write.

    Idempotent: safe to call multiple times; the second ``"file"`` call
    replaces the previous file backend with one pointing at the same path.

    Args:
        choice: ``"auto"`` is a no-op and preserves ``keyring``'s built-in
            backend-discovery default. ``"file"`` swaps to
            :class:`keyrings.alt.file.PlaintextKeyring` writing under
            ``pipefy_infra.paths.config_dir() / "keyring.cfg"``; the file stores
            credentials in plaintext on disk and is intended for headless
            Linux or CI runners where the OS keychain is unavailable.
    """
    if choice == "auto":
        return
    import keyring
    from keyrings.alt.file import PlaintextKeyring
    from pipefy_infra.paths import config_dir

    backend = PlaintextKeyring()
    backend.file_path = str(config_dir() / _KEYRING_FILENAME)
    keyring.set_keyring(backend)


class SessionDeleteError(RuntimeError):
    """Keychain backend rejected the delete (distinct from "entry absent")."""


class StoredSession(BaseModel):
    """Persisted session: identity + write timestamp + the token response.

    The token fields are bundled in :class:`TokenResponse` so there is one
    source of truth for the OAuth wire shape. On-disk JSON destructures the
    token attributes into the parent object (legacy flat shape) so existing
    keychain entries continue to load.

    ``extra="forbid"`` because both writer and reader live in this codebase:
    an unknown key on disk indicates corruption or hand-editing, not an IdP
    extension. Unknown keys nested under ``token`` are still ignored
    (see :class:`TokenResponse`).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    issuer: Annotated[StrictStr, Field(min_length=1)]
    client_id: Annotated[StrictStr, Field(min_length=1)]
    obtained_at: StrictInt
    token: TokenResponse

    @model_validator(mode="before")
    @classmethod
    def _accept_flat_blob(cls, data: Any) -> Any:
        """Rebuild a nested ``token`` from a legacy flat on-disk shape.

        Pre-pydantic blobs destructured the token attributes into the parent
        object. If we receive that shape (``"token"`` absent, token-shaped
        keys present), re-nest before field validation. Already-nested input
        passes through untouched.
        """
        if not isinstance(data, dict):
            return data
        if "token" in data:
            return data
        if "access_token" not in data:
            return data
        nested: dict[str, Any] = {}
        outer: dict[str, Any] = {}
        for key, value in data.items():
            if key in _TOKEN_FIELDS:
                nested[key] = value
            else:
                outer[key] = value
        outer["token"] = nested
        return outer

    @model_serializer(mode="wrap")
    def _to_flat_blob(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Always serialize to the flat on-disk shape (legacy readers stay green)."""
        nested = handler(self)
        token = nested.pop("token", {})
        return {**nested, **token}


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
        _SERVICE, keychain_key(issuer, client_id), session.model_dump_json()
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
        return StoredSession.model_validate_json(blob)
    except ValidationError:
        return None


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
