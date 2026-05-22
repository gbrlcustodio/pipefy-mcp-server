"""Build an authenticated :class:`PipefyClient` from CLI configuration.

The precedence chain lives in :func:`pipefy_auth.resolve_pipefy_auth`; this
module collapses the CLI's two static-token surfaces (``--token`` flag and
``PIPEFY_TOKEN`` env var) into a single value before calling the resolver, and
translates resolver failures into Typer exits. The flag-vs-env distinction
survives only as a diagnostic label for ``pipefy auth status``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal

import typer
from httpx import Auth
from pipefy_auth import (
    STATIC_TOKEN_TIER,
    STORED_SESSION_TIER,
    OidcClient,
    RefreshError,
    ServiceAccount,
    detect_pipefy_tiers,
    ensure_fresh_session,
    missing_auth_message,
    resolve_pipefy_auth,
    tier_for,
)
from pipefy_sdk import (
    AiAutomationService,
    InternalApiClient,
    PipefyClient,
    PipefySettings,
)

from pipefy_cli._docs import DOCS_CLI_AUTH_REF
from pipefy_cli.config import ensure_public_graphql_configured

# Display labels for ``pipefy auth status``. The resolver knows the
# static-token tier; the CLI restores the flag-vs-env distinction here.
FLAG_TOKEN_SOURCE = "flag-token"
ENV_TOKEN_SOURCE = "env-token"


@dataclass(frozen=True)
class BearerToken:
    """Static bearer token plus the surface that produced it (``--token`` or env)."""

    value: str
    source: Literal["flag", "env"]


@dataclass(frozen=True)
class AuthContext:
    """Auth inputs for a single CLI invocation.

    Each field maps to one resolver tier (bearer-token, service-account,
    stored-session). Built once at startup from the loaded
    :class:`pipefy_auth.AuthSettings` plus the per-invocation ``--token`` /
    ``PIPEFY_TOKEN`` resolution.
    """

    bearer_token: BearerToken | None
    service_account: ServiceAccount | None
    oidc_client: OidcClient | None


_cached_signature: str | None = None
# One-shot CLIs reuse this; long-lived programmatic use should call
# ``clear_authenticated_client_cache`` between logical sessions (tests reset via fixture).
_cached_client: PipefyClient | None = None


def clear_authenticated_client_cache() -> None:
    """Drop the in-process client cache (tests and rare reload scenarios)."""
    global _cached_signature, _cached_client
    _cached_signature = None
    _cached_client = None


def _resolve(auth: AuthContext) -> Auth | None:
    return resolve_pipefy_auth(
        static_token=auth.bearer_token.value if auth.bearer_token else None,
        service_account=auth.service_account,
        oidc_client=auth.oidc_client,
    )


def _to_display_source(tier: str, bearer: BearerToken | None) -> str:
    """Map a resolver tier name to the locked JSON wire schema for ``auth status``."""
    if tier == STATIC_TOKEN_TIER:
        return (
            FLAG_TOKEN_SOURCE
            if bearer and bearer.source == "flag"
            else ENV_TOKEN_SOURCE
        )
    return tier


def detect_cli_sources(auth: AuthContext) -> list[str]:
    """Return detected sources mapped to CLI display labels."""
    detected = detect_pipefy_tiers(
        static_token=auth.bearer_token.value if auth.bearer_token else None,
        service_account=auth.service_account,
        oidc_client=auth.oidc_client,
    )
    return [_to_display_source(tier, auth.bearer_token) for tier in detected]


def _cache_key(
    pipefy_settings: PipefySettings,
    auth: AuthContext,
    tier: str,
) -> str:
    """SHA-256 digest of every input that could change the cached client.

    Hashed (not stored as plaintext) so the dump's secrets — the bearer
    token, the service-account ``client_secret`` — don't linger in module
    state for the process lifetime. Adding a new field to
    :class:`PipefySettings` or :class:`AuthContext` automatically participates
    in the key without touching this function.
    """
    payload = json.dumps(
        {
            "settings": pipefy_settings.model_dump(mode="json"),
            "auth": asdict(auth),
            "tier": tier,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_authenticated_client(
    pipefy_settings: PipefySettings,
    auth: AuthContext,
) -> PipefyClient:
    """Return a facade client using the highest-precedence available auth source.

    Raises:
        typer.Exit: Code 2 when no auth source resolves, or when refreshing a
            stored session fails.
    """
    global _cached_signature, _cached_client

    try:
        ensure_public_graphql_configured(pipefy_settings)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc

    resolved = _resolve(auth)
    if resolved is None:
        typer.echo(f"{missing_auth_message()} See {DOCS_CLI_AUTH_REF}.", err=True)
        raise typer.Exit(2)
    tier = tier_for(resolved)

    # Stored-session: warm up eagerly so refresh failures surface as a clean
    # exit(2) with a "run `pipefy auth login` again" hint instead of leaking
    # out as a transport error on the first GraphQL call. ``CallableBearerAuth``
    # observes the rotated token on subsequent requests.
    if tier == STORED_SESSION_TIER:
        if auth.oidc_client is None:
            # Unreachable per the resolver contract; guard kept so the
            # invariant holds under ``python -O``.
            raise typer.Exit(2)
        try:
            ensure_fresh_session(
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

    key = _cache_key(pipefy_settings, auth, tier)
    if _cached_client is not None and _cached_signature == key:
        return _cached_client

    client = PipefyClient(pipefy_settings, auth=resolved)
    if pipefy_settings.internal_api_url:
        internal_client = InternalApiClient(
            url=pipefy_settings.internal_api_url,
            auth=resolved,
            allow_insecure_urls=pipefy_settings.allow_insecure_urls,
        )
        client.set_internal_api_client(internal_client)
        client.set_ai_automation_service(AiAutomationService(client=internal_client))
    _cached_signature = key
    _cached_client = client
    return client


__all__ = [
    "AuthContext",
    "BearerToken",
    "ENV_TOKEN_SOURCE",
    "FLAG_TOKEN_SOURCE",
    "clear_authenticated_client_cache",
    "detect_cli_sources",
    "get_authenticated_client",
]
