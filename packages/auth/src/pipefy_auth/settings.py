"""Pydantic model for auth-related settings (env vars, config file fields).

Owns every value that describes *how* to authenticate against Pipefy. Its own
knobs are namespaced under ``PIPEFY_AUTH_*``:

* ``PIPEFY_AUTH_ISSUER_URL`` — full OIDC issuer URL for the stored-session tier
  (default ``https://signin.pipefy.com/realms/pipefy``).
* ``PIPEFY_AUTH_CLIENT_ID`` — OIDC public client id (defaults to
  :data:`pipefy_auth.identity.DEFAULT_AUTH_CLIENT_ID`).
* ``PIPEFY_AUTH_DISABLE_STORED_SESSION`` / ``PIPEFY_AUTH_KEYCHAIN_BACKEND`` —
  stored-session tier opt-out and keyring backend selection.

The service-account credentials keep their established names
(``PIPEFY_SERVICE_ACCOUNT_CLIENT_ID`` / ``_SECRET``), as does the static bearer
(``PIPEFY_TOKEN``). ``PIPEFY_BASE_URL`` (API host root that drives the OAuth
token endpoint) and ``PIPEFY_ALLOW_INSECURE_URLS`` are deployment-wide: the same
vars drive :class:`pipefy_sdk.PipefySettings`, and both models load them
independently so they stay in sync without cross-package coupling.
"""

from __future__ import annotations

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
DEFAULT_ISSUER_URL = "https://signin.pipefy.com/realms/pipefy"
DEFAULT_BASE_URL = "https://app.pipefy.com"

# Opaque secret / identifier strings: reject leading / trailing whitespace and
# blank values. Anything in between is opaque to us (the IdP defines the format).
_OPAQUE_CREDENTIAL_PATTERN = r"^\S(?:.*\S)?$"


class AuthSettings(InsecureUrlSettings):
    """Auth-related configuration loaded from env / config files.

    Auth-domain knobs are namespaced under ``PIPEFY_AUTH_*`` via the env prefix;
    the credentials and the deployment-wide ``base_url`` / ``allow_insecure_urls``
    keep their canonical names through explicit aliases. Self-contained: SSRF
    validation runs inline as a ``model_validator(mode="after")`` hook, so direct
    construction (`AuthSettings()`) is safe even when not composed under
    :class:`CliSettings` / :class:`Settings`. The ``base_url`` field mirrors
    :class:`pipefy_sdk.PipefySettings` via ``PIPEFY_BASE_URL`` (both models load
    it independently so they stay in sync) and drives the OAuth token endpoint.
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_AUTH_")

    @field_validator(
        "static_token",
        "service_account_client_id",
        "service_account_client_secret",
        "issuer_url",
        "client_id",
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
        # values like ``PIPEFY_AUTH_KEYCHAIN_BACKEND=' AUTO '`` should normalize to
        # ``"auto"`` rather than fail Literal validation with a cryptic enum
        # error. Case is meaningful for credential fields (kept strict via
        # ``_strip_str``), so the lowering applies only here.
        if isinstance(value, str):
            return value.strip().lower()
        return value

    # The credentials and the shared ``base_url`` carry explicit ``AliasChoices``
    # so their canonical names survive the ``PIPEFY_AUTH_`` prefix (which would
    # otherwise mangle them into ``PIPEFY_AUTH_STATIC_TOKEN`` etc.). The aliases
    # list ONLY the fully-qualified env names: an unprefixed entry would let
    # pydantic-settings pick up a bare-name env var (``TOKEN``, ``BASE_URL``) —
    # a credential-leak primitive for any host whose env carries those common
    # names. Kwarg construction by field name (``AuthSettings(static_token=...)``)
    # still works via ``populate_by_name=True``. The remaining fields
    # (``issuer_url``, ``client_id``, ``disable_stored_session``,
    # ``keychain_backend``) take their env names from the prefix.
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
        validation_alias=AliasChoices("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID"),
        description="Service-account OAuth client_id (env: PIPEFY_SERVICE_ACCOUNT_CLIENT_ID).",
    )

    service_account_client_secret: str | None = Field(
        default=None,
        pattern=_OPAQUE_CREDENTIAL_PATTERN,
        validation_alias=AliasChoices("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET"),
        description="Service-account OAuth client_secret (env: PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET).",
    )

    issuer_url: str = Field(
        default=DEFAULT_ISSUER_URL,
        pattern=security.URL_SHAPE_PATTERN,
        description=(
            "OIDC issuer URL for the stored-session tier "
            "(env: PIPEFY_AUTH_ISSUER_URL). Defaults to "
            f"'{DEFAULT_ISSUER_URL}' (canonical Pipefy production IdP). Set to "
            "the full issuer URL for a non-prod IdP."
        ),
    )

    client_id: str = Field(
        default=DEFAULT_AUTH_CLIENT_ID,
        pattern=_OPAQUE_CREDENTIAL_PATTERN,
        description=(
            "OIDC public client id registered at the issuer "
            "(env: PIPEFY_AUTH_CLIENT_ID; rarely overridden)."
        ),
    )

    base_url: str = Field(
        default=DEFAULT_BASE_URL,
        pattern=security.URL_SHAPE_PATTERN,
        validation_alias=AliasChoices("PIPEFY_BASE_URL"),
        description=(
            "Pipefy API host root (env: PIPEFY_BASE_URL, shared with the SDK). "
            "Drives the service-account OAuth token endpoint via the "
            "``service_account_url`` computed property. Mirrors the field of "
            "the same name on :class:`pipefy_sdk.PipefySettings`; both models "
            "load it independently from the same env var so they stay in sync."
        ),
    )

    disable_stored_session: bool = Field(
        default=False,
        description=(
            "When true (env: PIPEFY_AUTH_DISABLE_STORED_SESSION), the stored-session "
            "tier is never probed: ``to_oidc_client()`` returns None, tier "
            "resolution skips the keychain, and ``pipefy auth login`` refuses. "
            "Use to avoid the keychain backend-discovery cost on cold start "
            "(headless Linux, CI) or to opt out of OS-keychain storage entirely."
        ),
    )

    keychain_backend: Literal["auto", "file"] = Field(
        default="auto",
        description=(
            "Active ``keyring`` backend (env: PIPEFY_AUTH_KEYCHAIN_BACKEND). ``auto`` "
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
        OIDC field. Otherwise returns a real client because ``issuer_url`` has
        a non-empty default.
        """
        if self.disable_stored_session:
            return None
        return OidcClient(
            issuer_url=self.issuer_url.strip(),
            client_id=self.client_id.strip(),
        )

    @model_validator(mode="after")
    def _validate_endpoint_urls(self) -> Self:
        # Self-validate so direct ``AuthSettings()`` construction (outside
        # ``CliSettings`` / ``Settings``) is safe. ``base_url`` derives the
        # OAuth token endpoint via ``<base_url>/oauth/token`` so it must be a
        # host root; ``issuer_url`` is the OIDC issuer and may carry a realm path.
        self.base_url = security.sanitize_url(
            self.base_url,
            field_label="base_url",
            allow_insecure=self.allow_insecure_urls,
            require_host_root=True,
        )
        self.issuer_url = security.sanitize_url(
            self.issuer_url,
            field_label="issuer_url",
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
    ``PIPEFY_AUTH_*`` vars (so ``PIPEFY_JWT_ISSUER_URL`` is the inbound override,
    ``PIPEFY_AUTH_ISSUER_URL`` the outbound issuer); ``allow_insecure_urls`` (from
    the base) is the one exception, reading the shared ``PIPEFY_ALLOW_INSECURE_URLS``.
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
