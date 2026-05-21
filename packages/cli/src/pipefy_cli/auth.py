"""Build an authenticated :class:`PipefyClient` from CLI configuration.

The credential precedence chain (most explicit wins) is:

1. ``--token`` CLI flag
2. ``PIPEFY_TOKEN`` env var
3. ``PIPEFY_OAUTH_*`` triple → client-credentials grant (service account)
4. Stored user session from ``pipefy auth login`` (keychain) — refreshed
   eagerly when the access token is within the leeway window

Tiers 1 and 2 reach this function collapsed into ``AuthContext.bearer_token``
(resolved by the root Typer callback in ``main.py``); tier 4 resolves into
the same slot. The cache key includes whichever bearer ultimately reaches the
SDK, so a refresh-rotated access token naturally invalidates the cached client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import typer
from pipefy_sdk import (
    AiAutomationService,
    InternalApiClient,
    PipefyClient,
    PipefySettings,
)

from pipefy_cli._docs import DOCS_CLI_AUTH_REF
from pipefy_cli.config import (
    describe_missing_oauth_vars,
    ensure_public_graphql_configured,
)
from pipefy_cli.oauth import RefreshError, ensure_fresh_session, load_session

AuthSource = Literal[
    "flag-token",
    "env-token",
    "service-account",
    "stored-session",
    "none",
]


@dataclass(frozen=True)
class OidcClient:
    """OIDC client identity: issuer URL + the public client id registered there.

    The two fields are a single configurable unit; presence of an :class:`OidcClient`
    on :class:`AuthContext` is what gates tier 4 of the credential precedence chain.
    """

    issuer_url: str
    client_id: str


@dataclass(frozen=True)
class BearerToken:
    """Static bearer token plus the surface that produced it (``--token`` or env).

    Carrying the origin lets diagnostics (e.g. ``pipefy auth status``) report which
    precedence tier won without having to re-inspect ``argv``/``os.environ``.
    """

    value: str
    source: Literal["flag", "env"]


@dataclass(frozen=True)
class AuthContext:
    """User-auth identity for a single CLI invocation.

    Carries only identity. Where-to-call configuration (URLs, service-account
    credentials, ``allow_insecure_urls``) lives on :class:`PipefySettings` and is
    passed alongside.
    """

    bearer_token: BearerToken | None
    oidc_client: OidcClient | None


_cached_signature: tuple[object, ...] | None = None
# One-shot CLIs reuse this; long-lived programmatic use should call
# ``clear_authenticated_client_cache`` between logical sessions (tests reset via fixture).
_cached_client: PipefyClient | None = None


def clear_authenticated_client_cache() -> None:
    """Drop the in-process client cache (tests and rare reload scenarios)."""
    global _cached_signature, _cached_client
    _cached_signature = None
    _cached_client = None


def _cache_key(
    pipefy_settings: PipefySettings,
    bearer_token: str | None,
) -> tuple[object, ...]:
    return (
        (pipefy_settings.graphql_url or "").strip(),
        (pipefy_settings.internal_api_url or "").strip(),
        (pipefy_settings.oauth_url or "").strip(),
        (pipefy_settings.oauth_client or "").strip(),
        (pipefy_settings.oauth_secret or "").strip(),
        bool(pipefy_settings.allow_insecure_urls),
        (bearer_token or "").strip(),
    )


def detect_all_sources(
    pipefy_settings: PipefySettings,
    auth: AuthContext,
) -> list[AuthSource]:
    """Return every configured credential source, highest-precedence first.

    Side-effect-free except for a single keychain read when an ``oidc_client`` is
    set. Powers both :func:`detect_auth_source` (winner = first element) and
    diagnostic display (full list surfaces masked sources).
    """
    sources: list[AuthSource] = []
    if auth.bearer_token is not None:
        sources.append(
            "flag-token" if auth.bearer_token.source == "flag" else "env-token"
        )
    if not describe_missing_oauth_vars(pipefy_settings):
        sources.append("service-account")
    if (
        auth.oidc_client is not None
        and load_session(
            issuer=auth.oidc_client.issuer_url,
            client_id=auth.oidc_client.client_id,
        )
        is not None
    ):
        sources.append("stored-session")
    return sources


def detect_auth_source(
    pipefy_settings: PipefySettings,
    auth: AuthContext,
) -> AuthSource:
    """Return the precedence winner among configured sources, or ``"none"``."""
    sources = detect_all_sources(pipefy_settings, auth)
    return sources[0] if sources else "none"


def _missing_auth_message(pipefy_settings: PipefySettings) -> str:
    missing = describe_missing_oauth_vars(pipefy_settings)
    return (
        "Missing authentication. Use --token, set PIPEFY_TOKEN, configure "
        f"PIPEFY_OAUTH_* ({missing}), or run `pipefy auth login`. "
        f"See {DOCS_CLI_AUTH_REF}."
    )


def get_authenticated_client(
    pipefy_settings: PipefySettings,
    auth: AuthContext,
) -> PipefyClient:
    """Return a facade client using the highest-precedence available auth source.

    Args:
        pipefy_settings: Validated Pipefy endpoint settings (``PIPEFY_*``).
        auth: User-auth identity for this invocation. ``bearer_token`` covers
            tiers 1 and 2 (``--token`` / ``PIPEFY_TOKEN``); ``oidc_client`` covers
            tier 4 (stored user session keyed by issuer + client id). Tier 3
            (service-account client credentials) is resolved from
            ``pipefy_settings`` alone.

    Returns:
        Shared in-process instance when settings match a prior call; otherwise
        a new client.

    Raises:
        typer.Exit: Code 2 when no auth source resolves, or when a stored
            session exists but refresh failed.
    """
    global _cached_signature, _cached_client

    try:
        ensure_public_graphql_configured(pipefy_settings)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc

    source = detect_auth_source(pipefy_settings, auth)

    if source == "none":
        typer.echo(_missing_auth_message(pipefy_settings), err=True)
        raise typer.Exit(2)

    # Resolve the effective bearer BEFORE the cache lookup so a refresh-rotated
    # access token produces the right (new) cache signature.
    effective_bearer: str | None = None
    if source in ("flag-token", "env-token"):
        if auth.bearer_token is None:
            # Internal inconsistency: `detect_auth_source` returned a bearer
            # source but the AuthContext doesn't carry one. Asserts get stripped
            # under `python -O`, so guard explicitly.
            typer.echo(
                f"Internal error: auth source {source!r} detected but no bearer "
                "token is configured. Please file an issue.",
                err=True,
            )
            raise typer.Exit(2)
        effective_bearer = auth.bearer_token.value
    elif source == "stored-session":
        if auth.oidc_client is None:
            typer.echo(
                "Internal error: auth source 'stored-session' detected but no "
                "OIDC client is configured. Please file an issue.",
                err=True,
            )
            raise typer.Exit(2)
        try:
            session = ensure_fresh_session(
                issuer=auth.oidc_client.issuer_url,
                client_id=auth.oidc_client.client_id,
            )
        except RefreshError as exc:
            typer.echo(
                f"Stored Pipefy session could not be refreshed: {exc}. "
                "Run `pipefy auth login` to sign in again.",
                err=True,
            )
            raise typer.Exit(2) from exc
        # ``detect_auth_source`` already confirmed a session is present; if it
        # vanished between the two reads, fall through to the missing-auth path.
        if session is None:
            typer.echo(_missing_auth_message(pipefy_settings), err=True)
            raise typer.Exit(2)
        effective_bearer = session.access_token

    key = _cache_key(pipefy_settings, effective_bearer)
    if _cached_client is not None and _cached_signature == key:
        return _cached_client

    if effective_bearer:
        # Priorities 1, 2, and 4 collapse to "use a static bearer".
        # The bearer slot does not build an InternalApiClient — same
        # limitation as ``--token``/``PIPEFY_TOKEN`` today.
        client: PipefyClient = PipefyClient(
            pipefy_settings, bearer_token=effective_bearer.strip()
        )
        _cached_signature = key
        _cached_client = client
        return client

    # source == "service-account": client-credentials grant.
    client = PipefyClient(pipefy_settings)
    internal_client = InternalApiClient(
        url=pipefy_settings.internal_api_url,
        oauth_url=pipefy_settings.oauth_url,
        oauth_client=pipefy_settings.oauth_client,
        oauth_secret=pipefy_settings.oauth_secret,
        allow_insecure_urls=pipefy_settings.allow_insecure_urls,
    )
    client.set_internal_api_client(internal_client)
    client.set_ai_automation_service(AiAutomationService(client=internal_client))
    _cached_signature = key
    _cached_client = client
    return client


__all__ = [
    "AuthContext",
    "AuthSource",
    "BearerToken",
    "OidcClient",
    "clear_authenticated_client_cache",
    "detect_all_sources",
    "detect_auth_source",
    "get_authenticated_client",
]
