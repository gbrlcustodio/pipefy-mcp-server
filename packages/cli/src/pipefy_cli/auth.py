"""Build an authenticated :class:`PipefyClient` from CLI configuration.

The precedence chain — most explicit wins:

1. ``bearer_token`` arg (CLI ``--token`` flag or ``PIPEFY_TOKEN`` env).
2. ``PIPEFY_OAUTH_*`` triple → client-credentials grant (service account).
3. Stored user session from ``pipefy auth login`` (keychain) — refreshed
   eagerly when the access token is within the leeway window.

The cache key includes whichever bearer ultimately reaches the SDK, so a
refresh-rotated access token naturally invalidates the cached client.
"""

from __future__ import annotations

import typer
from pipefy_sdk import (
    AiAutomationService,
    InternalApiClient,
    PipefyClient,
    PipefySettings,
)

from pipefy_cli._docs import DOCS_SETUP_REF
from pipefy_cli.config import (
    describe_missing_oauth_vars,
    ensure_public_graphql_configured,
)
from pipefy_cli.oauth import RefreshError, ensure_fresh_session

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


def _missing_auth_message(pipefy_settings: PipefySettings) -> str:
    missing = describe_missing_oauth_vars(pipefy_settings)
    return (
        "Missing authentication. Use --token, set PIPEFY_TOKEN, configure "
        f"PIPEFY_OAUTH_* ({missing}), or run `pipefy auth login`. "
        f"See {DOCS_SETUP_REF}."
    )


def get_authenticated_client(
    pipefy_settings: PipefySettings,
    *,
    bearer_token: str | None = None,
    auth_url: str | None = None,
    auth_client_id: str | None = None,
) -> PipefyClient:
    """Return a facade client using the highest-precedence available auth source.

    Args:
        pipefy_settings: Validated Pipefy endpoint settings (``PIPEFY_*``).
        bearer_token: When set (``--token`` / ``PIPEFY_TOKEN``), skips OAuth and
            uses this bearer directly. Highest precedence.
        auth_url: Issuer URL for the stored user session lookup. From
            ``PIPEFY_AUTH_URL``.
        auth_client_id: Public client id for the stored session lookup.

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

    # Resolve the effective bearer BEFORE the cache lookup so a refresh-rotated
    # access token produces the right (new) cache signature.
    effective_bearer = bearer_token
    if not effective_bearer and describe_missing_oauth_vars(pipefy_settings):
        if auth_url and auth_client_id:
            try:
                session = ensure_fresh_session(
                    issuer=auth_url, client_id=auth_client_id
                )
            except RefreshError as exc:
                typer.echo(
                    f"Stored Pipefy session could not be refreshed: {exc}. "
                    "Run `pipefy auth login` to sign in again.",
                    err=True,
                )
                raise typer.Exit(2) from exc
            if session is not None:
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

    if describe_missing_oauth_vars(pipefy_settings):
        typer.echo(_missing_auth_message(pipefy_settings), err=True)
        raise typer.Exit(2)

    # Priority 3: client-credentials grant.
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
