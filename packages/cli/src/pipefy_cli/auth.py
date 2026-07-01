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
from dataclasses import asdict, dataclass, field
from typing import Any, Final, Literal, assert_never

import typer
from pipefy_auth import (
    OidcClient,
    RefreshError,
    ResolvedAuth,
    ServiceAccount,
    ServiceAccountAuth,
    StaticTokenAuth,
    StoredSessionAuth,
    build_httpx_auth,
    detect_pipefy_auth_methods,
    ensure_fresh_session,
    missing_auth_message,
    resolve_pipefy_auth,
)
from pipefy_sdk import (
    PipefyClient,
    PipefySettings,
)

from pipefy_cli._docs import DOCS_CLI_AUTH_REF

# Display labels for ``pipefy auth status``. The resolver knows the
# static-token method; the CLI restores the flag-vs-env distinction here.
FLAG_TOKEN_SOURCE: Final = "flag-token"
ENV_TOKEN_SOURCE: Final = "env-token"

# Locked JSON wire schema for ``pipefy auth status``: the auth-method names,
# with the static-token method split into the CLI's flag-vs-env surfaces, plus
# an explicit ``"none"`` sentinel for when no method resolved. Produced by
# :func:`detect_cli_auth_methods` / :func:`to_display_source`; ``commands.auth``
# renders it.
DisplaySource = Literal[
    "flag-token",
    "env-token",
    "service-account",
    "stored-session",
    "none",
]


@dataclass(frozen=True)
class BearerToken:
    """Static bearer token plus the surface that produced it (``--token`` or env)."""

    value: str = field(repr=False)
    source: Literal["flag", "env"]


@dataclass(frozen=True)
class AuthContext:
    """Auth inputs for a single CLI invocation.

    Each field maps to one auth method (bearer-token, service-account,
    stored-session). Built once at startup from the loaded
    :class:`pipefy_auth.AuthSettings` plus the per-invocation ``--token`` /
    ``PIPEFY_TOKEN`` resolution.

    ``oidc_client`` is ``None`` only when ``AuthSettings.disable_stored_session``
    is set (env: PIPEFY_DISABLE_STORED_SESSION); the stored-session method is
    then skipped end-to-end. Otherwise ``auth_url`` defaults to the prod IdP
    and the client is always present.
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


def _resolver_kwargs(auth: AuthContext) -> dict[str, Any]:
    """Map an :class:`AuthContext` onto the keyword inputs the resolver takes."""
    return {
        "static_token": auth.bearer_token.value if auth.bearer_token else None,
        "service_account": auth.service_account,
        "oidc_client": auth.oidc_client,
    }


def _resolve(auth: AuthContext) -> ResolvedAuth | None:
    return resolve_pipefy_auth(**_resolver_kwargs(auth))


def to_display_source(
    resolved: ResolvedAuth, bearer: BearerToken | None
) -> DisplaySource:
    """Map a resolved auth method to its locked ``auth status`` wire value.

    The static-token method splits into the flag-vs-env distinction the CLI
    surfaces; the other methods map to their resolver wire name unchanged.
    """
    match resolved:
        case StaticTokenAuth():
            return (
                FLAG_TOKEN_SOURCE
                if bearer and bearer.source == "flag"
                else ENV_TOKEN_SOURCE
            )
        case ServiceAccountAuth():
            return "service-account"
        case StoredSessionAuth():
            return "stored-session"
        case _:
            assert_never(resolved)


def detect_cli_auth_methods(auth: AuthContext) -> list[ResolvedAuth]:
    """Return the detected auth methods for a CLI invocation, precedence-first.

    The non-short-circuiting view of the chain: every configured method, not
    just the winner. ``pipefy auth status`` renders each via
    :func:`to_display_source` and treats the first as the active source.
    """
    return detect_pipefy_auth_methods(**_resolver_kwargs(auth))


def _cache_key(
    pipefy_settings: PipefySettings,
    auth: AuthContext,
) -> str:
    """SHA-256 digest of every input that could change the cached client.

    Hashed (not stored as plaintext) so the dump's secrets — the bearer
    token, the service-account ``client_secret`` — don't linger in module
    state for the process lifetime. Adding a new field to
    :class:`PipefySettings` or :class:`AuthContext` automatically participates
    in the key without touching this function. The resolved method is omitted:
    it is a pure function of the auth fields above, so it adds no distinction.
    """
    payload = json.dumps(
        {
            "settings": pipefy_settings.model_dump(mode="json"),
            "auth": asdict(auth),
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

    resolved = _resolve(auth)
    if resolved is None:
        typer.echo(f"{missing_auth_message()} See {DOCS_CLI_AUTH_REF}.", err=True)
        raise typer.Exit(2)

    # Stored-session: warm up eagerly so refresh failures surface as a clean
    # exit(2) with a "run `pipefy auth login` again" hint instead of leaking
    # out as a transport error on the first GraphQL call.
    if isinstance(resolved, StoredSessionAuth):
        try:
            ensure_fresh_session(
                issuer=resolved.oidc_client.issuer_url,
                client_id=resolved.oidc_client.client_id,
            )
        except RefreshError as exc:
            typer.echo(
                f"Stored Pipefy session could not be refreshed: {exc}. "
                "Run `pipefy auth login` to sign in again.",
                err=True,
            )
            raise typer.Exit(2) from exc

    key = _cache_key(pipefy_settings, auth)
    if _cached_client is not None and _cached_signature == key:
        return _cached_client

    client = PipefyClient(
        pipefy_settings, auth=build_httpx_auth(resolved), surface="cli"
    )
    _cached_signature = key
    _cached_client = client
    return client


__all__ = [
    "AuthContext",
    "BearerToken",
    "DisplaySource",
    "ENV_TOKEN_SOURCE",
    "FLAG_TOKEN_SOURCE",
    "clear_authenticated_client_cache",
    "detect_cli_auth_methods",
    "get_authenticated_client",
    "to_display_source",
]
