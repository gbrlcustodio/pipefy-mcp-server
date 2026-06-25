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
from typing import Literal, Self

from pipefy_infra import security
from pipefy_infra.config import InsecureUrlSettings
from pydantic import (
    AliasChoices,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import SettingsConfigDict

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

# Env vars that earlier betas honored but this release no longer reads (``extra="ignore"``
# silently drops them). Emit a one-shot stderr warning so operators upgrading from a
# non-prod configuration get a runtime breadcrumb instead of silently authenticating
# against the prod default.
_LEGACY_DROPPED_ENV_KEYS: dict[str, str] = {
    "PIPEFY_OAUTH_URL": (
        "no replacement — the OAuth token endpoint now derives from PIPEFY_BASE_URL "
        "(default https://app.pipefy.com)"
    ),
}

_warned_legacy_env_keys: set[str] = set()
_warned_dropped_env_keys: set[str] = set()


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


def _warn_once_for_dropped_oauth_env_keys() -> None:
    """Emit a one-shot stderr warning for each removed env var still present in the environment."""
    if len(_warned_dropped_env_keys) == len(_LEGACY_DROPPED_ENV_KEYS):
        return
    for legacy, note in _LEGACY_DROPPED_ENV_KEYS.items():
        if legacy in _warned_dropped_env_keys:
            continue
        if legacy in os.environ:
            sys.stderr.write(
                f"warning: {legacy} is no longer recognized — {note}. "
                "The stale value is silently ignored; remove it from your env / .env.\n"
            )
            _warned_dropped_env_keys.add(legacy)


def _reset_legacy_oauth_warning_state() -> None:
    """Test helper: clear the one-shot dedup so a fixture can re-trigger the warning."""
    _warned_legacy_env_keys.clear()
    _warned_dropped_env_keys.clear()


class AuthSettings(InsecureUrlSettings):
    """Auth-related configuration loaded from env / config files.

    Reads its own ``PIPEFY_*`` env vars directly (with the ``PIPEFY_`` prefix
    folded into the field names). Self-contained: SSRF validation runs inline
    as a ``model_validator(mode="after")`` hook, so direct construction
    (`AuthSettings()`) is safe even when not composed under
    :class:`CliSettings` / :class:`Settings`. The ``base_url`` field mirrors
    :class:`pipefy_sdk.PipefySettings` via ``PIPEFY_BASE_URL`` (both models load
    it independently so they stay in sync) and drives the OAuth token endpoint.
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")

    @model_validator(mode="before")
    @classmethod
    def _emit_legacy_oauth_env_var_warning(cls, data: object) -> object:
        # Mirrors the pre-split behaviour: warn once per legacy env key still set.
        _warn_once_for_legacy_oauth_env_keys()
        _warn_once_for_dropped_oauth_env_keys()
        return data

    @field_validator(
        "static_token",
        "service_account_client_id",
        "service_account_client_secret",
        "auth_url",
        "auth_client_id",
        "base_url",
        "disable_stored_session",
        mode="before",
    )
    @classmethod
    def _strip_str(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("keychain_backend", mode="before")
    @classmethod
    def _normalize_keychain_backend(cls, value: object) -> object:
        # ``keychain_backend`` is ``Literal["auto", "file"]``; copy-pasted env
        # values like ``PIPEFY_KEYCHAIN_BACKEND=' AUTO '`` should normalize to
        # ``"auto"`` rather than fail Literal validation with a cryptic enum
        # error. Case is meaningful for credential fields (kept strict via
        # ``_strip_str``), so the lowering applies only here.
        if isinstance(value, str):
            return value.strip().lower()
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
        pattern=security.URL_SHAPE_PATTERN,
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

    # ``base_url`` uses the ``env_prefix="PIPEFY_"`` mapping directly (env name =
    # ``PIPEFY_BASE_URL``) — no ``AliasChoices`` needed. Field-name init kwargs
    # (``AuthSettings(base_url=...)``) win over env on the source chain, matching
    # the natural call site. ``allow_insecure_urls`` comes from the base.
    base_url: str = Field(
        default=DEFAULT_BASE_URL,
        pattern=security.URL_SHAPE_PATTERN,
        description=(
            "Pipefy API host root (env: PIPEFY_BASE_URL). Drives the "
            "service-account OAuth token endpoint via the "
            "``service_account_url`` computed property. Mirrors the field of "
            "the same name on :class:`pipefy_sdk.PipefySettings`; both models "
            "load it independently from the same env var so they stay in sync."
        ),
    )

    disable_stored_session: bool = Field(
        default=False,
        description=(
            "When true (env: PIPEFY_DISABLE_STORED_SESSION), the stored-session "
            "tier is never probed: ``to_oidc_client()`` returns None, tier "
            "resolution skips the keychain, and ``pipefy auth login`` refuses. "
            "Use to avoid the keychain backend-discovery cost on cold start "
            "(headless Linux, CI) or to opt out of OS-keychain storage entirely."
        ),
    )

    keychain_backend: Literal["auto", "file"] = Field(
        default="auto",
        description=(
            "Active ``keyring`` backend (env: PIPEFY_KEYCHAIN_BACKEND). ``auto`` "
            "uses the default OS keyring discovery; ``file`` swaps to "
            "``keyrings.alt.file.PlaintextKeyring`` writing under "
            "``config_dir()/keyring.cfg``. The file backend stores credentials "
            "in plaintext on disk; opt-in only, intended for headless Linux "
            "without Secret Service or for CI runners."
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

    def to_oidc_client(self) -> OidcClient | None:
        """Project the OIDC fields into an :class:`OidcClient`.

        Returns ``None`` when :attr:`disable_stored_session` is set: callers
        treat that as "the stored-session tier is off" without inspecting any
        OIDC field. Otherwise returns a real client because ``auth_url`` has
        a non-empty default.
        """
        if self.disable_stored_session:
            return None
        return OidcClient(
            issuer_url=self.auth_url.strip(),
            client_id=self.auth_client_id.strip(),
        )

    @model_validator(mode="after")
    def _validate_endpoint_urls(self) -> Self:
        # Self-validate so direct ``AuthSettings()`` construction (outside
        # ``CliSettings`` / ``Settings``) is safe. ``base_url`` derives the
        # OAuth token endpoint via ``<base_url>/oauth/token`` so it must be a
        # host root; ``auth_url`` is the OIDC issuer and may carry a realm path.
        self.base_url = security.sanitize_url(
            self.base_url,
            field_label="base_url",
            allow_insecure=self.allow_insecure_urls,
            require_host_root=True,
        )
        self.auth_url = security.sanitize_url(
            self.auth_url,
            field_label="auth_url",
            allow_insecure=self.allow_insecure_urls,
        )
        return self


class JwtValidationSettings(InsecureUrlSettings):
    """How this process validates an inbound bearer when it acts as a resource server.

    :class:`AuthSettings` configures the *outbound* side: how this process
    authenticates *to* Pipefy. This is the inbound counterpart that feeds
    :class:`~pipefy_auth.JwtValidator`. It is a separate model, not fields on
    :class:`AuthSettings`, because only a transport running the OAuth
    resource-server profile (today, the MCP ``--remote`` HTTP transport) consumes
    it: a CLI that only authenticates outbound never carries resource-server knobs.

    ``issuer_url`` is an override. Left unset, the consumer falls back to the
    issuer this process already logs into (the :class:`OidcClient` issuer): in a
    single-realm deployment the IdP that signs caller tokens is the same one we
    authenticate to, so it need not be configured twice. Set it only when inbound
    and outbound issuers diverge (token exchange, multi-tenant federation).

    ``env_prefix="PIPEFY_JWT_"`` keeps these distinct from ``AuthSettings``'
    ``PIPEFY_*`` vars; ``allow_insecure_urls`` (from the base) is the one
    exception, reading the shared ``PIPEFY_ALLOW_INSECURE_URLS``.
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_JWT_")

    issuer_url: str | None = Field(
        default=None,
        description=(
            "Override for the inbound OIDC issuer that signs caller tokens "
            "(env: PIPEFY_JWT_ISSUER_URL). Left unset, the consumer falls back "
            "to the issuer this process logs into; set it only when inbound and "
            "outbound issuers diverge. The JWKS endpoint is resolved from the "
            "issuer's discovery document unless jwks_uri is given."
        ),
    )

    audience: str | None = Field(
        default=None,
        description=(
            "Expected token audience (env: PIPEFY_JWT_AUDIENCE). Required when "
            "verify_audience is true."
        ),
    )

    verify_audience: bool = Field(
        default=False,
        description=(
            "When true (env: PIPEFY_JWT_VERIFY_AUDIENCE), reject tokens whose "
            "aud does not include audience. Defaults false for the same-audience "
            "interim, which runs before the IdP issues an aud claim."
        ),
    )

    jwks_uri: str | None = Field(
        default=None,
        description=(
            "Explicit JWKS endpoint override (env: PIPEFY_JWT_JWKS_URI). When "
            "unset, resolved from the issuer's discovery document."
        ),
    )

    def resolve_issuer_url(self, default: str | None) -> str | None:
        """The inbound issuer (override, else ``default``), with any trailing slash dropped.

        jwt.decode compares the iss claim by exact equality, so the issuer is
        canonicalized here, at the boundary that hands it to the validator.
        """
        issuer = self.issuer_url or default
        return issuer.rstrip("/") if issuer is not None else None

    @model_validator(mode="after")
    def _validate_configuration(self) -> Self:
        if self.verify_audience and not self.audience:
            raise ValueError("verify_audience requires audience (PIPEFY_JWT_AUDIENCE).")
        for label in ("issuer_url", "jwks_uri"):
            value = getattr(self, label)
            if value is None:
                continue
            setattr(
                self,
                label,
                security.sanitize_url(
                    value, field_label=label, allow_insecure=self.allow_insecure_urls
                ),
            )
        return self


__all__ = ["AuthSettings", "JwtValidationSettings"]
