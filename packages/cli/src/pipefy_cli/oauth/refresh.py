"""Refresh-token grant + eager pre-use refresh for the stored OAuth user session."""

from __future__ import annotations

import time

import httpx

from pipefy_cli.oauth import _http
from pipefy_cli.oauth.discovery import fetch_provider_metadata
from pipefy_cli.oauth.storage import StoredSession, load_session, store_session

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
    session: StoredSession,
    http_client: httpx.Client | None = None,
) -> tuple[dict[str, object], str | None, str | None]:
    """POST ``grant_type=refresh_token`` to the issuer's token endpoint.

    Uses the persisted ``token_endpoint`` when available; otherwise falls back
    to OIDC discovery (legacy keychain entries from before endpoint caching).

    Returns:
        A tuple of ``(token_response, authorization_endpoint, token_endpoint)``.
        The endpoint fields are populated only when discovery ran (legacy
        sessions); callers should merge them into the stored session.

    Raises:
        RefreshError: For any failure that prevents a fresh token response
            (discovery failure, network error, non-200, malformed body).
    """
    discovered_authorization_endpoint: str | None = None
    discovered_token_endpoint: str | None = None
    with _http.http_client(http_client, timeout=_TIMEOUT_S) as http:
        if session.token_endpoint:
            token_endpoint = session.token_endpoint
        else:
            try:
                metadata = fetch_provider_metadata(session.issuer, client=http)
            except ValueError as exc:
                raise RefreshError(f"OIDC discovery failed: {exc}") from exc
            token_endpoint = metadata.token_endpoint
            discovered_authorization_endpoint = metadata.authorization_endpoint
            discovered_token_endpoint = metadata.token_endpoint
        try:
            response = http.post(
                token_endpoint,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": session.refresh_token,
                    "client_id": session.client_id,
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
    return payload, discovered_authorization_endpoint, discovered_token_endpoint


def _refresh_error_from(response: httpx.Response) -> RefreshError:
    """Render a non-200 refresh response as a structured ``RefreshError``.

    Only OAuth-standard ``error`` / ``error_description`` fields are surfaced;
    raw bodies are never echoed (same threat model as the token-exchange scrub
    in ``flow._format_token_error`` — a hostile IdP could echo submitted params
    like ``refresh_token`` in error responses, and a ``[:N]`` window would be a
    guaranteed leak channel).
    """
    generic = f"Refresh failed (HTTP {response.status_code})"
    try:
        payload = response.json()
    except ValueError:
        return RefreshError(generic)
    if not isinstance(payload, dict):
        return RefreshError(generic)
    error_value = payload.get("error")
    error_code = error_value if isinstance(error_value, str) else None
    description_value = payload.get("error_description")
    description = description_value if isinstance(description_value, str) else None
    if not error_code:
        return RefreshError(generic)
    if description:
        return RefreshError(
            f"{generic}: {error_code}: {description}", error_code=error_code
        )
    return RefreshError(f"{generic}: {error_code}", error_code=error_code)


def ensure_fresh_session(
    *,
    issuer: str,
    client_id: str,
    leeway_s: int = _LEEWAY_S,
    http_client: httpx.Client | None = None,
) -> StoredSession | None:
    """Load the stored session; refresh it if the access token is near expiry.

    Returns ``None`` when no session is stored (or the keychain is unreachable
    — ``load_session`` already collapses those cases). Returns the (possibly
    refreshed) :class:`StoredSession` when one is usable.

    Raises:
        RefreshError: When a stored session exists but refresh failed.
            Caller surfaces a "run ``pipefy auth login`` again" message.
    """
    session = load_session(issuer=issuer, client_id=client_id)
    if session is None:
        return None

    expires_in = session.expires_in or 0
    deadline = session.obtained_at + expires_in - leeway_s
    if time.time() < deadline:
        return session

    token_response, discovered_auth, discovered_token = refresh_access_token(
        session=session, http_client=http_client
    )
    # Carry forward fields the IdP may omit from a refresh response so the
    # rotated session keeps its full shape — without ``expires_in`` the next
    # freshness check treats the token as already expired and refreshes again
    # on the very next call.
    token_response.setdefault("refresh_token", session.refresh_token)
    if session.expires_in is not None:
        token_response.setdefault("expires_in", session.expires_in)
    if session.refresh_expires_in is not None:
        token_response.setdefault("refresh_expires_in", session.refresh_expires_in)
    if session.scope is not None:
        token_response.setdefault("scope", session.scope)
    if session.id_token is not None:
        token_response.setdefault("id_token", session.id_token)
    return store_session(
        issuer=session.issuer,
        client_id=session.client_id,
        token_response=token_response,
        authorization_endpoint=session.authorization_endpoint or discovered_auth,
        token_endpoint=session.token_endpoint or discovered_token,
    )


__all__ = [
    "RefreshError",
    "ensure_fresh_session",
    "refresh_access_token",
]
