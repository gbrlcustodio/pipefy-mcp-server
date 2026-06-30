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

from typing import Self

from httpx import Auth
from httpx_auth import OAuth2ClientCredentials
from pipefy_infra import security
from pipefy_infra.coerce import OPAQUE_CREDENTIAL_PATTERN
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipefy_auth.bearer import (
    CallableBearerAuth,
    RefreshableBearerAuth,
    StaticBearerAuth,
)
from pipefy_auth.identity import OidcClient
from pipefy_auth.refresh import RefreshError, ensure_fresh_session
from pipefy_auth.storage import load_session

STATIC_TOKEN_TIER = "static-token"
SERVICE_ACCOUNT_TIER = "service-account"
STORED_SESSION_TIER = "stored-session"


class ServiceAccount(BaseModel):
    """OAuth2 client-credentials inputs for the service-account tier.

    A frozen, refined value object: construction witnesses a well-shaped token
    endpoint and opaque credentials. The token endpoint is derived from the one
    deployment host root (already HTTPS/SSRF-gated there), so only shape is
    checked here.
    """

    model_config = ConfigDict(frozen=True)

    token_url: str = Field(pattern=security.URL_SHAPE_PATTERN)
    client_id: str = Field(pattern=OPAQUE_CREDENTIAL_PATTERN)
    client_secret: str = Field(pattern=OPAQUE_CREDENTIAL_PATTERN)

    @model_validator(mode="after")
    def _validate_url_shape(self) -> Self:
        security.assert_url_has_no_query_or_fragment(
            self.token_url, field_label="token_url"
        )
        return self


class CredentialSources(BaseModel):
    """The parsed credentials for every tier, bundled as one input.

    A frozen value object the application edge resolves once (via
    ``pipefy_auth.env.load_auth``) and hands to :func:`resolve_pipefy_auth` /
    :func:`detect_pipefy_tiers`. Each field is the witness for one tier, or
    ``None`` when that tier is unconfigured. ``keychain_backend`` is NOT here: it
    is a pre-resolve side effect (backend selection), not a credential source.
    """

    model_config = ConfigDict(frozen=True)

    static_token: str | None = Field(default=None, pattern=OPAQUE_CREDENTIAL_PATTERN)
    service_account: ServiceAccount | None = None
    oidc_client: OidcClient | None = None


# Maps each ``httpx.Auth`` implementation back to the resolver-tier name that
# produced it. ``tier_for`` is the public lookup; the mapping itself is the
# single source of truth so the wire-schema strings (e.g. ``"stored-session"``)
# stay in one place. ``CallableBearerAuth`` is listed alongside
# ``RefreshableBearerAuth`` so consumers who build one directly still resolve
# to the stored-session tier.
_TIER_BY_AUTH_TYPE: dict[type[Auth], str] = {
    StaticBearerAuth: STATIC_TOKEN_TIER,
    OAuth2ClientCredentials: SERVICE_ACCOUNT_TIER,
    RefreshableBearerAuth: STORED_SESSION_TIER,
    CallableBearerAuth: STORED_SESSION_TIER,
}


def tier_for(auth: Auth) -> str:
    """Return the resolver-tier name that produced ``auth``.

    Raises:
        ValueError: When ``auth`` is not an instance produced by
            :func:`resolve_pipefy_auth` (e.g. a consumer-provided
            ``httpx.Auth`` for tests or a custom integration).
    """
    for cls, source in _TIER_BY_AUTH_TYPE.items():
        if isinstance(auth, cls):
            return source
    raise ValueError(
        f"No resolver-tier name for httpx.Auth of type {type(auth).__name__}"
    )


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


def resolve_pipefy_auth(sources: CredentialSources) -> Auth | None:
    """Resolve the highest-precedence tier with credentials available.

    Short-circuits at the first tier that resolves — lower tiers are never
    inspected. The returned ``httpx.Auth`` carries the tier identity in its
    concrete type; use :func:`tier_for` to recover the resolver-tier name
    (e.g. for the ``pipefy auth status`` wire schema).

    For an enumeration of every detected tier (e.g. for diagnostics), call
    :func:`detect_pipefy_tiers` instead.

    Args:
        sources: The parsed credentials for every tier. ``static_token`` is the
            pre-resolved bearer (consumers collapse their own per-source
            precedence, e.g. CLI ``--token`` vs ``PIPEFY_TOKEN``, before
            building it). ``oidc_client`` gates the stored-session tier: the
            session is loaded from the keychain at detection time, and a fresh
            access token is fetched per request via
            :class:`pipefy_auth.bearer.RefreshableBearerAuth`, which also forces
            a refresh + retry on a 401 response.
    """
    if sources.static_token:
        return StaticBearerAuth(sources.static_token)
    if sources.service_account is not None:
        return OAuth2ClientCredentials(
            token_url=sources.service_account.token_url,
            client_id=sources.service_account.client_id,
            client_secret=sources.service_account.client_secret,
        )
    if sources.oidc_client is not None and _has_stored_session(sources.oidc_client):
        return _stored_session_provider(sources.oidc_client)
    return None


def detect_pipefy_tiers(sources: CredentialSources) -> list[str]:
    """Return every tier with credentials available, highest-precedence first.

    Used by ``pipefy auth status`` to surface masked sources alongside the
    winner. Does not short-circuit — every tier's detection runs (including
    the keychain read for the stored-session tier).
    """
    detected: list[str] = []
    if sources.static_token:
        detected.append(STATIC_TOKEN_TIER)
    if sources.service_account is not None:
        detected.append(SERVICE_ACCOUNT_TIER)
    if sources.oidc_client is not None and _has_stored_session(sources.oidc_client):
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
    "CredentialSources",
    "ServiceAccount",
    "detect_pipefy_tiers",
    "missing_auth_message",
    "resolve_pipefy_auth",
    "tier_for",
]
