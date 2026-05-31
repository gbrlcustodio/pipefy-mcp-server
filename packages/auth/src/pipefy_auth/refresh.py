"""Refresh-token grant + eager pre-use refresh for the stored OAuth user session."""

from __future__ import annotations

import time

import httpx
from pydantic import ValidationError

from pipefy_auth import _http
from pipefy_auth.discovery import fetch_provider_metadata
from pipefy_auth.locks import RefreshLockTimeout, file_lock, refresh_lock_path
from pipefy_auth.responses import (
    OAuthErrorResponse,
    TokenResponse,
    _format_validation_error,
)
from pipefy_auth.storage import StoredSession, load_session, store_session

_LEEWAY_S = 60
_TIMEOUT_S = 30.0


class RefreshError(RuntimeError):
    """A stored session exists but its refresh attempt failed.

    Distinct from "no session" (which surfaces as ``None`` from
    :func:`ensure_fresh_session`). The caller should surface a "run
    ``pipefy auth login`` again" message and exit.

    ``error_code`` carries the RFC 6749 ``error`` value (e.g. ``invalid_grant``)
    when the token endpoint returned a structured OAuth error response. Callers
    that classify failures (e.g. CLI ``auth status`` deciding between
    ``refresh-expired`` and ``needs-login``) should branch on this attribute,
    not on substrings of ``str(exc)`` — message text isn't a stable contract.
    """

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


def refresh_access_token(
    *,
    issuer: str,
    client_id: str,
    refresh_token: str,
    http_client: httpx.Client | None = None,
) -> dict[str, object]:
    """POST ``grant_type=refresh_token`` to the issuer's token endpoint.

    Raises:
        RefreshError: For any failure that prevents a fresh token response
            (discovery failure, network error, non-200, malformed body).
    """
    with _http.http_client(http_client, timeout=_TIMEOUT_S) as http:
        try:
            metadata = fetch_provider_metadata(issuer, client=http)
        except ValueError as exc:
            raise RefreshError(f"OIDC discovery failed: {exc}") from exc
        try:
            response = http.post(
                metadata.token_endpoint,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                },
            )
        except httpx.HTTPError as exc:
            raise RefreshError(f"Refresh request failed: {exc}") from exc

    if response.status_code != 200:
        raise _refresh_error_from(response)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RefreshError(f"Token endpoint returned non-JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RefreshError("Token endpoint returned a non-object JSON payload.")
    return payload


def _refresh_error_from(response: httpx.Response) -> RefreshError:
    """Render a non-200 refresh response as a structured ``RefreshError``.

    Only OAuth-standard ``error`` / ``error_description`` fields are surfaced;
    raw bodies are never echoed (a hostile IdP could echo submitted params
    like ``refresh_token`` in error responses, and a ``[:N]`` window would be
    a guaranteed leak channel).
    """
    fallback = f"Refresh failed (HTTP {response.status_code})"
    err = OAuthErrorResponse.from_response(response)
    return RefreshError(
        err.render(fallback=fallback, prefix="Refresh failed"),
        error_code=err.error,
    )


def _is_stale(session: StoredSession, leeway_s: int) -> bool:
    expires_in = session.token.expires_in or 0
    deadline = session.obtained_at + expires_in - leeway_s
    return time.time() >= deadline


def _refresh_and_store(
    session: StoredSession,
    *,
    issuer: str,
    client_id: str,
    http_client: httpx.Client | None,
) -> StoredSession:
    prior = session.token
    payload = refresh_access_token(
        issuer=issuer,
        client_id=client_id,
        refresh_token=prior.refresh_token,
        http_client=http_client,
    )
    # Carry forward fields the IdP may omit from a refresh response so the
    # rotated session keeps its full shape — without ``expires_in`` the next
    # freshness check treats the token as already expired and refreshes again
    # on the very next call.
    payload.setdefault("refresh_token", prior.refresh_token)
    if prior.expires_in is not None:
        payload.setdefault("expires_in", prior.expires_in)
    if prior.refresh_expires_in is not None:
        payload.setdefault("refresh_expires_in", prior.refresh_expires_in)
    if prior.scope is not None:
        payload.setdefault("scope", prior.scope)
    if prior.id_token is not None:
        payload.setdefault("id_token", prior.id_token)
    try:
        new_token = TokenResponse.from_payload(payload)
    except ValidationError as exc:
        raise RefreshError(
            f"Refresh response malformed: {_format_validation_error(exc)}"
        ) from exc
    except ValueError as exc:
        raise RefreshError(f"Refresh response malformed: {exc}") from exc
    return store_session(
        issuer=session.issuer,
        client_id=session.client_id,
        token=new_token,
    )


def ensure_fresh_session(
    *,
    issuer: str,
    client_id: str,
    leeway_s: int = _LEEWAY_S,
    force: bool = False,
    http_client: httpx.Client | None = None,
) -> StoredSession | None:
    """Load the stored session; refresh it if the access token is near expiry.

    Returns ``None`` when no session is stored (or the keychain is unreachable
    — ``load_session`` already collapses those cases). Returns the (possibly
    refreshed) :class:`StoredSession` when one is usable.

    ``force=True`` bypasses the deadline check and always refreshes when a
    session is stored — used by the reactive 401-retry path to recover from
    IdP-side revocation when the clock-side lifetime still looks fine.

    Concurrent ``pipefy`` processes near the leeway boundary are serialised
    via a cross-process filesystem lock; a re-load + re-check inside the
    critical section means the loser of the race observes the winner's
    rotated session and skips its own refresh round-trip.

    Raises:
        RefreshError: When a stored session exists but refresh failed
            (including ``RefreshLockTimeout``, surfaced as a clean
            "lock could not be acquired" message rather than a raw
            ``RuntimeError``).
    """
    session = load_session(issuer=issuer, client_id=client_id)
    if session is None:
        return None
    if not force and not _is_stale(session, leeway_s):
        return session

    try:
        with file_lock(refresh_lock_path()):
            session = load_session(issuer=issuer, client_id=client_id)
            if session is None:
                return None
            if not force and not _is_stale(session, leeway_s):
                return session
            return _refresh_and_store(
                session,
                issuer=issuer,
                client_id=client_id,
                http_client=http_client,
            )
    except RefreshLockTimeout as exc:
        raise RefreshError(
            f"Could not acquire refresh lock; another process may be hung: {exc}"
        ) from exc


__all__ = [
    "RefreshError",
    "ensure_fresh_session",
    "refresh_access_token",
]
