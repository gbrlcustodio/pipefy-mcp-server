"""Pydantic model for auth-related settings (env vars, config file fields).

Owns every value that describes *how* to authenticate against Pipefy:

* ``PIPEFY_SERVICE_ACCOUNT_CLIENT_ID`` / ``PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET``
  — OAuth2 client-credentials grant inputs (legacy ``PIPEFY_OAUTH_CLIENT`` /
  ``_SECRET`` names still honoured via :class:`AliasChoices`).
* ``PIPEFY_AUTH_URL`` — full OIDC issuer URL for the stored-session tier
  (default ``https://signin.pipefy.com/realms/pipefy``).
* ``PIPEFY_AUTH_CLIENT_ID`` — OIDC public client id (defaults to
  :data:`pipefy_auth.identity.DEFAULT_AUTH_CLIENT_ID`).
* ``PIPEFY_BASE_URL`` — API host root that drives the OAuth token endpoint
  (default ``https://app.pipefy.com``). Same env var that drives the SDK's
  ``base_url`` field on :class:`pipefy_sdk.PipefySettings`; both models load
  it independently so they stay in sync without cross-package coupling.

Per-URL env vars from earlier betas (``PIPEFY_GRAPHQL_URL``,
``PIPEFY_INTERNAL_API_URL``, ``PIPEFY_INTERFACES_GRAPHQL_URL``,
``PIPEFY_SERVICE_ACCOUNT_URL``, ``PIPEFY_TENANT``, ``PIPEFY_AUTH_REALM``,
``PIPEFY_OAUTH_URL``) are no longer recognized — set ``PIPEFY_BASE_URL`` to
the API host and ``PIPEFY_AUTH_URL`` to the full OIDC issuer URL instead.
"""

from __future__ import annotations

import os
import sys
from typing import Self

from pydantic import (
    AliasChoices,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipefy_auth.identity import (
    DEFAULT_AUTH_CLIENT_ID,
    OidcClient,
)
from pipefy_auth.resolver import ServiceAccount

# Production defaults.
DEFAULT_AUTH_URL = "https://signin.pipefy.com/realms/pipefy"
DEFAULT_BASE_URL = "https://app.pipefy.com"

# Opaque secret / identifier strings: reject leading / trailing whitespace and
# blank values. Anything in between is opaque to us (the IdP defines the format).
_OPAQUE_CREDENTIAL_PATTERN = r"^\S(?:.*\S)?$"

# URL-shape gate. ``pipefy_auth._url_ssrf.validate_https_service_endpoint_url``
# does the deeper SSRF + scheme check after settings construction. The
# scheme part is case-insensitive (RFC 3986 §3.1) so `HTTPS://...` from
# operator copy-paste passes the shape gate; httpx + gql normalize the
# scheme downstream.
_URL_SHAPE_PATTERN = r"^(?i:https?)://\S+$"

# Legacy ``PIPEFY_OAUTH_*`` env vars still resolve to the new
# ``PIPEFY_SERVICE_ACCOUNT_*`` fields. The mapping is exported for
# diagnostics (e.g. CLI's ``pipefy auth status`` lists which legacy keys
# would still mask a stored session). The legacy ``PIPEFY_OAUTH_URL`` alias
# was dropped in the ``PIPEFY_BASE_URL`` rewrite — the token endpoint now
# derives from ``base_url``.
_LEGACY_ENV_KEYS_TO_NEW: dict[str, str] = {
    "PIPEFY_OAUTH_CLIENT": "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID",
    "PIPEFY_OAUTH_SECRET": "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET",
}

_warned_legacy_env_keys: set[str] = set()


def _warn_once_for_legacy_oauth_env_keys() -> None:
    """Emit a one-shot stderr deprecation warning for each legacy env var still set."""
    if len(_warned_legacy_env_keys) == len(_LEGACY_ENV_KEYS_TO_NEW):
        return
    for legacy, new in _LEGACY_ENV_KEYS_TO_NEW.items():
        if legacy in _warned_legacy_env_keys:
            continue
        if legacy in os.environ:
            sys.stderr.write(
                f"warning: {legacy} is deprecated; rename to {new}. "
                "The legacy name will be removed in a future beta.\n"
            )
            _warned_legacy_env_keys.add(legacy)


def _reset_legacy_oauth_warning_state() -> None:
    """Test helper: clear the one-shot dedup so a fixture can re-trigger the warning."""
    _warned_legacy_env_keys.clear()


class AuthSettings(BaseSettings):
    """Auth-related configuration loaded from env / config files.

    Reads its own ``PIPEFY_*`` env vars directly (with the ``PIPEFY_`` prefix
    folded into the field names). Self-contained: SSRF validation runs inline
    as a ``model_validator(mode="after")`` hook, so direct construction
    (`AuthSettings()`) is safe even when not composed under
    :class:`CliSettings` / :class:`Settings`. The ``allow_insecure_urls``
    field mirrors :class:`pipefy_sdk.PipefySettings`'s field of the same name
    and is read from ``PIPEFY_ALLOW_INSECURE_URLS``; the ``base_url`` field
    likewise mirrors PipefySettings via ``PIPEFY_BASE_URL`` and drives the
    OAuth token endpoint.
    """

    model_config = SettingsConfigDict(
        env_prefix="PIPEFY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Required so ``env_prefix`` is applied to the field name on top of the
        # ``AliasChoices`` lookups (otherwise env lookups would only consider
        # the aliases, and ``PIPEFY_SERVICE_ACCOUNT_CLIENT_ID`` would be ignored).
        populate_by_name=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _emit_legacy_oauth_env_var_warning(cls, data: object) -> object:
        # Mirrors the pre-split behaviour: warn once per legacy env key still set.
        _warn_once_for_legacy_oauth_env_keys()
        return data

    @field_validator(
        "static_token",
        "service_account_client_id",
        "service_account_client_secret",
        "auth_url",
        "auth_client_id",
        "base_url",
        mode="before",
    )
    @classmethod
    def _strip_str(cls, value: object) -> object:
        # Strip surrounding whitespace on every env-loaded string so a stray
        # leading / trailing space from copy-paste does not trip the per-field
        # ``pattern`` constraint. Empty-after-strip still fails the pattern
        # (the "empty raises" contract).
        if isinstance(value, str):
            return value.strip()
        return value

    # ``AliasChoices`` lists ONLY fully-prefixed env-var names. Unprefixed
    # entries would let pydantic-settings pick up bare-name env vars
    # (e.g. ``BASE_URL``, ``STATIC_TOKEN``, ``OAUTH_CLIENT``) — an
    # auth-redirect / credential-leak primitive for any host whose env
    # accidentally carries those common names. Kwarg construction by
    # field name (e.g. ``AuthSettings(static_token=...)``) still works
    # via ``populate_by_name=True``.
    static_token: str | None = Field(
        default=None,
        pattern=_OPAQUE_CREDENTIAL_PATTERN,
        validation_alias=AliasChoices("PIPEFY_TOKEN"),
        description=(
            "Pre-issued bearer for the static-token tier (env: PIPEFY_TOKEN). "
            "When set, outranks both the service-account triple and any stored session."
        ),
    )

    service_account_client_id: str | None = Field(
        default=None,
        pattern=_OPAQUE_CREDENTIAL_PATTERN,
        validation_alias=AliasChoices(
            "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID",
            "PIPEFY_OAUTH_CLIENT",
        ),
        description=(
            "Service-account OAuth client_id "
            "(env: PIPEFY_SERVICE_ACCOUNT_CLIENT_ID; legacy PIPEFY_OAUTH_CLIENT still honored)."
        ),
    )

    service_account_client_secret: str | None = Field(
        default=None,
        pattern=_OPAQUE_CREDENTIAL_PATTERN,
        validation_alias=AliasChoices(
            "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET",
            "PIPEFY_OAUTH_SECRET",
        ),
        description=(
            "Service-account OAuth client_secret "
            "(env: PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET; legacy PIPEFY_OAUTH_SECRET still honored)."
        ),
    )

    auth_url: str = Field(
        default=DEFAULT_AUTH_URL,
        pattern=_URL_SHAPE_PATTERN,
        description=(
            "OIDC issuer URL for the stored-session tier "
            "(env: PIPEFY_AUTH_URL). Defaults to "
            f"'{DEFAULT_AUTH_URL}' (canonical Pipefy production IdP). Set to "
            "the full issuer URL for a non-prod IdP."
        ),
    )

    auth_client_id: str = Field(
        default=DEFAULT_AUTH_CLIENT_ID,
        pattern=_OPAQUE_CREDENTIAL_PATTERN,
        description=(
            "OIDC public client id registered at the issuer "
            "(env: PIPEFY_AUTH_CLIENT_ID; rarely overridden)."
        ),
    )

    base_url: str = Field(
        default=DEFAULT_BASE_URL,
        pattern=_URL_SHAPE_PATTERN,
        validation_alias=AliasChoices("PIPEFY_BASE_URL"),
        description=(
            "Pipefy API host root (env: PIPEFY_BASE_URL). Drives the "
            "service-account OAuth token endpoint via the "
            "``service_account_url`` computed property. Mirrors the field of "
            "the same name on :class:`pipefy_sdk.PipefySettings`; both models "
            "load it independently from the same env var so they stay in sync."
        ),
    )

    allow_insecure_urls: bool = Field(
        default=False,
        validation_alias=AliasChoices("PIPEFY_ALLOW_INSECURE_URLS"),
        description=(
            "When true (env: PIPEFY_ALLOW_INSECURE_URLS), auth-related URLs "
            "may use http:// and internal hosts; local development only; do "
            "not enable in production. Mirrors the field of the same name on "
            ":class:`pipefy_sdk.PipefySettings` so this model can run its own "
            "inline SSRF check without consulting the parent composition."
        ),
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def service_account_url(self) -> str:
        """OAuth 2.0 token endpoint for the service-account tier."""
        return f"{self.base_url.rstrip('/')}/oauth/token"

    def to_service_account(self) -> ServiceAccount | None:
        """Project the triple into a :class:`ServiceAccount`, or ``None`` if incomplete."""
        if (
            self.service_account_url
            and self.service_account_client_id
            and self.service_account_client_secret
        ):
            return ServiceAccount(
                token_url=self.service_account_url,
                client_id=self.service_account_client_id,
                client_secret=self.service_account_client_secret,
            )
        return None

    def to_oidc_client(self) -> OidcClient:
        """Project the OIDC fields into an :class:`OidcClient` (never returns None)."""
        return OidcClient(
            issuer_url=self.auth_url.strip(),
            client_id=self.auth_client_id.strip(),
        )

    @model_validator(mode="after")
    def _validate_endpoint_urls(self) -> Self:
        # Self-validate so direct ``AuthSettings()`` construction (outside
        # ``CliSettings`` / ``Settings``) is safe.
        from pipefy_auth._url_ssrf import validate_https_service_endpoint_url

        validate_https_service_endpoint_url(
            self.base_url.strip(),
            "base_url",
            allow_insecure=self.allow_insecure_urls,
        )
        validate_https_service_endpoint_url(
            self.auth_url.strip(),
            "auth_url",
            allow_insecure=self.allow_insecure_urls,
        )
        return self


__all__ = ["AuthSettings"]
