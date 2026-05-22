"""Pydantic model for auth-related settings (env vars, config file fields).

Owns every value that describes *how* to authenticate against Pipefy:

* ``PIPEFY_SERVICE_ACCOUNT_*`` — OAuth2 client-credentials grant inputs
  (legacy ``PIPEFY_OAUTH_*`` names still honoured via :class:`AliasChoices`).
* ``PIPEFY_AUTH_URL`` — OIDC issuer URL for the stored-session tier.
* ``PIPEFY_AUTH_CLIENT_ID`` — OIDC public client id (defaults to
  :data:`pipefy_auth.identity.DEFAULT_AUTH_CLIENT_ID`).

Endpoint settings (``PIPEFY_GRAPHQL_URL``, ``PIPEFY_INTERNAL_API_URL``) live
on :class:`pipefy_sdk.PipefySettings` — they are SDK concerns, not auth.
Consumers compose both models side by side in their own settings type.
"""

from __future__ import annotations

import os
import sys

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipefy_auth.identity import DEFAULT_AUTH_CLIENT_ID, OidcClient
from pipefy_auth.resolver import ServiceAccount

# Legacy ``PIPEFY_OAUTH_*`` env vars still resolve to the new
# ``PIPEFY_SERVICE_ACCOUNT_*`` fields. The mapping is exported for
# diagnostics (e.g. CLI's ``pipefy auth status`` lists which legacy keys
# would still mask a stored session).
_LEGACY_ENV_KEYS_TO_NEW: dict[str, str] = {
    "PIPEFY_OAUTH_URL": "PIPEFY_SERVICE_ACCOUNT_URL",
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
    folded into the field names). Pure data — SSRF validation happens via
    :meth:`validate_urls` once the surrounding settings know whether insecure
    URLs are allowed.
    """

    model_config = SettingsConfigDict(
        env_prefix="PIPEFY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Required so ``env_prefix`` is applied to the field name on top of the
        # ``AliasChoices`` lookups (otherwise env lookups would only consider
        # the aliases, and ``PIPEFY_SERVICE_ACCOUNT_URL`` would be ignored).
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
        "service_account_url",
        "service_account_client_id",
        "service_account_client_secret",
        "auth_url",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        # Empty / whitespace-only env values mean "not set", not "set to ''".
        if isinstance(value, str) and not value.strip():
            return None
        return value

    # ``AliasChoices`` precedence is left-to-right. The fully-prefixed
    # canonical env var comes first to outrank the legacy ``PIPEFY_OAUTH_*``
    # name. The unprefixed form (e.g. ``oauth_url``) keeps direct kwarg
    # construction working (``AuthSettings(oauth_url=...)``).
    static_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PIPEFY_TOKEN", "static_token"),
        description=(
            "Pre-issued bearer for the static-token tier (env: PIPEFY_TOKEN). "
            "When set, outranks both the service-account triple and any stored session."
        ),
    )

    service_account_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PIPEFY_SERVICE_ACCOUNT_URL",
            "service_account_url",
            "oauth_url",
            "PIPEFY_OAUTH_URL",
        ),
        description=(
            "Service-account token endpoint (OAuth 2.0 client-credentials grant) "
            "(env: PIPEFY_SERVICE_ACCOUNT_URL; legacy PIPEFY_OAUTH_URL still honored)."
        ),
    )

    service_account_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID",
            "service_account_client_id",
            "oauth_client",
            "PIPEFY_OAUTH_CLIENT",
        ),
        description=(
            "Service-account OAuth client_id "
            "(env: PIPEFY_SERVICE_ACCOUNT_CLIENT_ID; legacy PIPEFY_OAUTH_CLIENT still honored)."
        ),
    )

    service_account_client_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET",
            "service_account_client_secret",
            "oauth_secret",
            "PIPEFY_OAUTH_SECRET",
        ),
        description=(
            "Service-account OAuth client_secret "
            "(env: PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET; legacy PIPEFY_OAUTH_SECRET still honored)."
        ),
    )

    auth_url: str | None = Field(
        default=None,
        description=(
            "OIDC issuer URL for the stored-session tier "
            "(env: PIPEFY_AUTH_URL, e.g. https://signin.pipefy.com/realms/pipefy)."
        ),
    )

    auth_client_id: str = Field(
        default=DEFAULT_AUTH_CLIENT_ID,
        description=(
            "OIDC public client id registered at the issuer "
            "(env: PIPEFY_AUTH_CLIENT_ID; rarely overridden)."
        ),
    )

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

    def to_oidc_client(self) -> OidcClient | None:
        """Project the OIDC fields into an :class:`OidcClient`, or ``None`` without ``auth_url``."""
        if self.auth_url and self.auth_url.strip():
            return OidcClient(
                issuer_url=self.auth_url.strip(),
                client_id=self.auth_client_id.strip() or DEFAULT_AUTH_CLIENT_ID,
            )
        return None

    def validate_urls(self, *, allow_insecure: bool) -> None:
        """Run SSRF checks on every URL this model carries. Call after composing."""
        from pipefy_auth._url_ssrf import validate_https_service_endpoint_url

        if self.service_account_url and (u := self.service_account_url.strip()):
            validate_https_service_endpoint_url(
                u, "service_account_url", allow_insecure=allow_insecure
            )
        if self.auth_url and (u := self.auth_url.strip()):
            validate_https_service_endpoint_url(
                u, "auth_url", allow_insecure=allow_insecure
            )


__all__ = ["AuthSettings"]
