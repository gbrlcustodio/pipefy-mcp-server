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

import typer
from pipefy_auth import (
    STATIC_TOKEN_TIER,
    STORED_SESSION_TIER,
    CredentialSources,
    RefreshError,
    detect_pipefy_tiers,
    ensure_fresh_session,
    missing_auth_message,
    resolve_pipefy_auth,
    tier_for,
)
from pipefy_sdk import PipefyClient

from pipefy_cli._docs import DOCS_CLI_AUTH_REF
from pipefy_cli.runtime import CliRuntime, TokenSource

# Display labels for ``pipefy auth status``. The resolver knows the
# static-token tier; the CLI restores the flag-vs-env distinction here.
FLAG_TOKEN_SOURCE = "flag-token"
ENV_TOKEN_SOURCE = "env-token"


_cached_signature: str | None = None
# One-shot CLIs reuse this; long-lived programmatic use should call
# ``clear_authenticated_client_cache`` between logical sessions (tests reset via fixture).
_cached_client: PipefyClient | None = None


def clear_authenticated_client_cache() -> None:
    """Drop the in-process client cache (tests and rare reload scenarios)."""
    global _cached_signature, _cached_client
    _cached_signature = None
    _cached_client = None


def _to_display_source(tier: str, token_source: TokenSource | None) -> str:
    """Map a resolver tier name to the locked JSON wire schema for ``auth status``."""
    if tier == STATIC_TOKEN_TIER:
        return FLAG_TOKEN_SOURCE if token_source == "flag" else ENV_TOKEN_SOURCE
    return tier


def detect_cli_sources(runtime: CliRuntime) -> list[str]:
    """Return detected sources mapped to CLI display labels."""
    detected = detect_pipefy_tiers(runtime.credentials)
    return [_to_display_source(tier, runtime.token_source) for tier in detected]


def _cache_key(
    endpoints_dump: str,
    credentials: CredentialSources,
    tier: str,
) -> str:
    """SHA-256 digest of every input that could change the cached client.

    Hashed (not stored as plaintext) so the credentials — the bearer token, the
    service-account ``client_secret`` — don't linger in module state for the
    process lifetime. The endpoints and credential bundle, plus the resolved
    tier, are the only inputs that vary the wired client.
    """
    payload = json.dumps(
        {
            "endpoints": endpoints_dump,
            "credentials": credentials.model_dump(mode="json"),
            "tier": tier,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_authenticated_client(runtime: CliRuntime) -> PipefyClient:
    """Return a facade client using the highest-precedence available auth source.

    Raises:
        typer.Exit: Code 2 when no auth source resolves, or when refreshing a
            stored session fails.
    """
    global _cached_signature, _cached_client

    resolved = resolve_pipefy_auth(runtime.credentials)
    if resolved is None:
        typer.echo(f"{missing_auth_message()} See {DOCS_CLI_AUTH_REF}.", err=True)
        raise typer.Exit(2)
    tier = tier_for(resolved)

    # Stored-session: warm up eagerly so refresh failures surface as a clean
    # exit(2) with a "run `pipefy auth login` again" hint instead of leaking
    # out as a transport error on the first GraphQL call.
    if tier == STORED_SESSION_TIER:
        oidc = runtime.credentials.oidc_client
        if oidc is None:
            # Resolver only picks STORED_SESSION_TIER when oidc_client is non-None;
            # reaching here means that invariant is broken.
            raise RuntimeError(
                "STORED_SESSION_TIER resolved without an OIDC client "
                "(resolver invariant broken)."
            )
        try:
            ensure_fresh_session(
                issuer=oidc.issuer_url,
                client_id=oidc.client_id,
            )
        except RefreshError as exc:
            typer.echo(
                f"Stored Pipefy session could not be refreshed: {exc}. "
                "Run `pipefy auth login` to sign in again.",
                err=True,
            )
            raise typer.Exit(2) from exc

    key = _cache_key(runtime.endpoints.model_dump_json(), runtime.credentials, tier)
    if _cached_client is not None and _cached_signature == key:
        return _cached_client

    client = PipefyClient(
        runtime.endpoints,
        auth=resolved,
        allow_insecure_urls=runtime.allow_insecure_urls,
        reuse_schema=runtime.reuse_schema,
        default_webhook_name=runtime.default_webhook_name,
    )
    _cached_signature = key
    _cached_client = client
    return client


__all__ = [
    "ENV_TOKEN_SOURCE",
    "FLAG_TOKEN_SOURCE",
    "clear_authenticated_client_cache",
    "detect_cli_sources",
    "get_authenticated_client",
]
