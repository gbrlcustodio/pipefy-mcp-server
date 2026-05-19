"""Refresh-token grant + eager pre-use refresh for the stored OAuth user session."""

from __future__ import annotations

import time

import httpx

from pipefy_cli.oauth._http import http_client as _http_client
from pipefy_cli.oauth.discovery import fetch_provider_metadata
from pipefy_cli.oauth.storage import StoredSession, load_session, store_session

_LEEWAY_S = 60
_TIMEOUT_S = 30.0


class RefreshError(RuntimeError):
    """A stored session exists but its refresh attempt failed.

    Distinct from "no session" (which surfaces as ``None`` from
    :func:`ensure_fresh_session`). The caller should surface a "run
    ``pipefy auth login`` again" message and exit.
    """


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
    with _http_client(http_client, timeout=_TIMEOUT_S) as http:
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
        raise RefreshError(
            f"Refresh failed ({response.status_code}): {response.text[:300]}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RefreshError(f"Token endpoint returned non-JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RefreshError("Token endpoint returned a non-object JSON payload.")
    return payload


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

    token_response = refresh_access_token(
        issuer=issuer,
        client_id=client_id,
        refresh_token=session.refresh_token,
        http_client=http_client,
    )
    # Some IdPs don't rotate the refresh token on every refresh.
    token_response.setdefault("refresh_token", session.refresh_token)
    return store_session(
        issuer=session.issuer,
        client_id=session.client_id,
        token_response=token_response,
    )


__all__ = [
    "RefreshError",
    "ensure_fresh_session",
    "refresh_access_token",
]
