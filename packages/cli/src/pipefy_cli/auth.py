"""Build an authenticated :class:`PipefyClient` from CLI configuration (OAuth or ``--token``)."""

from __future__ import annotations

import typer
from pipefy_sdk import (
    AiAutomationService,
    InternalApiClient,
    PipefyClient,
    PipefySettings,
)

from pipefy_cli._docs import DOCS_QUICKSTART_REF
from pipefy_cli.config import (
    describe_missing_oauth_vars,
    ensure_public_graphql_configured,
)

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


def get_authenticated_client(
    pipefy_settings: PipefySettings,
    *,
    bearer_token: str | None = None,
) -> PipefyClient:
    """Return a facade client using OAuth client-credentials or a static bearer token.

    Uses the same OAuth wiring as ``pipefy-mcp-server`` via :class:`PipefyClient`
    (``httpx_auth.OAuth2ClientCredentials`` when no bearer is supplied).

    Args:
        pipefy_settings: Validated Pipefy endpoint settings (``PIPEFY_*``).
        bearer_token: When set, skips OAuth and uses this bearer for GraphQL transports.

    Returns:
        Shared in-process instance when settings match a prior call; otherwise a new
        client. Tokens are not written to disk.

    Raises:
        typer.Exit: Code 2 when configuration is incomplete for the chosen auth mode.
    """
    global _cached_signature, _cached_client

    try:
        ensure_public_graphql_configured(pipefy_settings)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc

    key = _cache_key(pipefy_settings, bearer_token)
    if _cached_client is not None and _cached_signature == key:
        return _cached_client

    if bearer_token:
        client: PipefyClient = PipefyClient(
            pipefy_settings, bearer_token=bearer_token.strip()
        )
        _cached_signature = key
        _cached_client = client
        return client

    missing_msg = describe_missing_oauth_vars(pipefy_settings)
    if missing_msg:
        typer.echo(
            f"Missing OAuth configuration ({missing_msg}). "
            f"Use --token or PIPEFY_TOKEN for a bearer token, or set OAuth per {DOCS_QUICKSTART_REF}.",
            err=True,
        )
        raise typer.Exit(2)

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
    "clear_authenticated_client_cache",
    "get_authenticated_client",
]
