"""Single source of truth for the Pipefy credential precedence chain.

The chain is a fixed three-slot tuple — consumers do not extend it:

1. ``static-token`` — a pre-resolved bearer (consumers collapse their own
   surfaces — CLI ``--token`` flag, ``PIPEFY_TOKEN`` env var — into one value).
2. ``service-account`` — OAuth2 client-credentials grant.
3. ``stored-session`` — keychain session populated by ``pipefy auth login``.

The flag-vs-env distinction the CLI surfaces in ``pipefy auth status`` is a
display concern handled in CLI code, not a tier here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from httpx import Auth
from httpx_auth import OAuth2ClientCredentials

from pipefy_auth.bearer import (
    RefreshableBearerAuth,
    StaticBearerAuth,
)
from pipefy_auth.identity import OidcClient
from pipefy_auth.refresh import RefreshError, ensure_fresh_session
from pipefy_auth.storage import load_session

STATIC_TOKEN_TIER = "static-token"
SERVICE_ACCOUNT_TIER = "service-account"
STORED_SESSION_TIER = "stored-session"


@dataclass(frozen=True)
class ServiceAccount:
    """OAuth2 client-credentials inputs for the service-account tier."""

    token_url: str
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class StaticTokenAuth:
    """Resolved static-token tier: a pre-issued bearer, stripped and non-blank."""

    token: str


@dataclass(frozen=True)
class ServiceAccountAuth:
    """Resolved service-account tier: the OAuth2 client-credentials inputs."""

    credentials: ServiceAccount


@dataclass(frozen=True)
class StoredSessionAuth:
    """Resolved stored-session tier: the OIDC client whose keychain session was found.

    ``oidc_client`` is non-None by construction: :func:`resolve_pipefy_auth` only
    builds this variant once a keychain session is present, so consumers reach it
    without a further presence check.
    """

    oidc_client: OidcClient


# The credential precedence chain, parsed into the tier that won:
# :func:`resolve_pipefy_auth` produces it, :func:`build_httpx_auth` consumes it.
ResolvedAuth = StaticTokenAuth | ServiceAccountAuth | StoredSessionAuth


def _stored_session_provider(oidc_client: OidcClient) -> RefreshableBearerAuth:
    def _token() -> str:
        session = ensure_fresh_session(
            issuer=oidc_client.issuer_url, client_id=oidc_client.client_id
        )
        if session is None:
            raise RuntimeError(
                "Stored Pipefy session was removed; run `pipefy auth login` again."
            )
        return session.token.access_token

    def _force_refresh() -> str | None:
        try:
            session = ensure_fresh_session(
                issuer=oidc_client.issuer_url,
                client_id=oidc_client.client_id,
                force=True,
            )
        except RefreshError:
            return None
        return session.token.access_token if session is not None else None

    return RefreshableBearerAuth(token_provider=_token, force_refresh=_force_refresh)


def _has_stored_session(oidc_client: OidcClient) -> bool:
    return (
        load_session(issuer=oidc_client.issuer_url, client_id=oidc_client.client_id)
        is not None
    )


def resolve_pipefy_auth(
    *,
    static_token: str | None = None,
    service_account: ServiceAccount | None = None,
    oidc_client: OidcClient | None = None,
) -> ResolvedAuth | None:
    """Parse the available credentials into the highest-precedence tier that resolves.

    Short-circuits at the first tier that resolves; lower tiers are never
    inspected. The returned :data:`ResolvedAuth` variant carries the tier
    identity in its type; pass it to :func:`build_httpx_auth` to obtain the
    transport's ``httpx.Auth``.

    For an enumeration of every detected tier (e.g. for diagnostics), call
    :func:`detect_pipefy_tiers` instead.

    Args:
        static_token: Pre-resolved bearer for the static-token tier. Consumers
            collapse their own per-source precedence (e.g. CLI ``--token`` flag
            vs ``PIPEFY_TOKEN`` env var) into one value before calling.
        service_account: Service-account client-credentials inputs.
        oidc_client: OIDC client identity for the stored-session tier; the
            session is loaded from the keychain at detection time.
    """
    if static_token and static_token.strip():
        return StaticTokenAuth(static_token.strip())
    if service_account is not None:
        return ServiceAccountAuth(service_account)
    if oidc_client is not None and _has_stored_session(oidc_client):
        return StoredSessionAuth(oidc_client)
    return None


def build_httpx_auth(resolved: ResolvedAuth) -> Auth:
    """Construct the ``httpx.Auth`` for an already-resolved tier.

    Total over :data:`ResolvedAuth`: the "no credentials" case is decided once,
    in :func:`resolve_pipefy_auth`, so this function has no ``None`` branch. The
    stored-session tier fetches a fresh access token per request via
    :class:`pipefy_auth.bearer.RefreshableBearerAuth`, which also forces a
    refresh + retry on a 401 response.
    """
    match resolved:
        case StaticTokenAuth(token):
            return StaticBearerAuth(token)
        case ServiceAccountAuth(credentials):
            return OAuth2ClientCredentials(
                token_url=credentials.token_url,
                client_id=credentials.client_id,
                client_secret=credentials.client_secret,
            )
        case StoredSessionAuth(oidc_client):
            return _stored_session_provider(oidc_client)
        case _:
            assert_never(resolved)


def detect_pipefy_tiers(
    *,
    static_token: str | None = None,
    service_account: ServiceAccount | None = None,
    oidc_client: OidcClient | None = None,
) -> list[str]:
    """Return every tier with credentials available, highest-precedence first.

    Used by ``pipefy auth status`` to surface masked sources alongside the
    winner. Does not short-circuit — every tier's detection runs (including
    the keychain read for the stored-session tier).
    """
    detected: list[str] = []
    if static_token and static_token.strip():
        detected.append(STATIC_TOKEN_TIER)
    if service_account is not None:
        detected.append(SERVICE_ACCOUNT_TIER)
    if oidc_client is not None and _has_stored_session(oidc_client):
        detected.append(STORED_SESSION_TIER)
    return detected


def missing_auth_message(*, login_command: str = "pipefy auth login") -> str:
    """Canonical "no auth configured" message; consumers append their own context."""
    return (
        "Missing Pipefy authentication. Set PIPEFY_TOKEN, configure "
        f"PIPEFY_SERVICE_ACCOUNT_*, or run `{login_command}`."
    )


__all__ = [
    "SERVICE_ACCOUNT_TIER",
    "STATIC_TOKEN_TIER",
    "STORED_SESSION_TIER",
    "ResolvedAuth",
    "ServiceAccount",
    "ServiceAccountAuth",
    "StaticTokenAuth",
    "StoredSessionAuth",
    "build_httpx_auth",
    "detect_pipefy_tiers",
    "missing_auth_message",
    "resolve_pipefy_auth",
]
