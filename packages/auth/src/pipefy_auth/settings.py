"""Pure value objects for auth settings (outbound auth + inbound JWT validation).

Owns every value that describes *how* to authenticate against Pipefy. These are
plain :class:`pydantic.BaseModel` value objects: they validate themselves but
read no env / file (the application edge owns env reading and injects the
values). Host topology and the insecure-URL posture live on the injected
:class:`~pipefy_infra.deployment.DeploymentConfig`:

* the service-account OAuth token endpoint is ``deployment.oauth_token_url``
  (derived from the one ``base_url``), so the host root is read once;
* ``deployment.allow_insecure_urls`` is the shared SSRF posture, so the whole
  deployment toggles together.

The OAuth client-credentials pair is modeled as the nested
:class:`ServiceAccountCredentials` value object: the two are validated as a
cohesive unit (both-or-neither), and the edge injects the whole block or
``None`` (that tier unconfigured).
"""

from __future__ import annotations

from typing import Literal, Self

from pipefy_infra import security
from pipefy_infra.coerce import OPAQUE_CREDENTIAL_PATTERN
from pipefy_infra.deployment import DeploymentConfig
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from pipefy_auth.identity import (
    DEFAULT_AUTH_CLIENT_ID,
    OidcClient,
)
from pipefy_auth.resolver import ServiceAccount

# Production default OIDC issuer.
DEFAULT_ISSUER_URL = "https://signin.pipefy.com/realms/pipefy"


class ServiceAccountCredentials(BaseModel):
    """The OAuth client-credentials pair for the service-account tier.

    A cohesive unit: ``client_id`` and ``client_secret`` are both required, so
    the both-or-neither rule lives in the type rather than in scattered field
    checks. The application edge builds this only when both env vars
    (``PIPEFY_SERVICE_ACCOUNT_CLIENT_ID`` / ``_SECRET``) are present, else passes
    ``None``; the token endpoint is supplied separately from the deployment.
    """

    client_id: str = Field(
        pattern=OPAQUE_CREDENTIAL_PATTERN,
        description="Service-account OAuth client_id (env: PIPEFY_SERVICE_ACCOUNT_CLIENT_ID).",
    )

    client_secret: str = Field(
        pattern=OPAQUE_CREDENTIAL_PATTERN,
        description="Service-account OAuth client_secret (env: PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET).",
    )


class AuthConfig(BaseModel):
    """Outbound auth configuration: how this process authenticates *to* Pipefy.

    A pure value object. ``deployment`` (host topology + posture) and
    ``service_account`` (the credential pair, or ``None``) are injected by the
    edge; the OIDC login knobs are this model's own values. SSRF validation runs
    inline as a ``model_validator(mode="after")`` so direct construction is safe.
    """

    deployment: DeploymentConfig = Field(
        description=(
            "Host topology + insecure-URL posture, injected by reference from the "
            "one DeploymentConfig the application edge builds (shared with the SDK)."
        ),
    )

    service_account: ServiceAccountCredentials | None = Field(
        default=None,
        description=(
            "The service-account tier's OAuth client-credentials pair, injected "
            "by the edge; ``None`` means that tier is unconfigured."
        ),
    )

    static_token: str | None = Field(
        default=None,
        pattern=OPAQUE_CREDENTIAL_PATTERN,
        description=(
            "Pre-issued bearer for the static-token tier (env: PIPEFY_TOKEN). "
            "When set, outranks both the service-account tier and any stored session."
        ),
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

    public_client_id: str = Field(
        default=DEFAULT_AUTH_CLIENT_ID,
        pattern=OPAQUE_CREDENTIAL_PATTERN,
        description=(
            "OIDC public client id registered at the issuer "
            "(env: PIPEFY_AUTH_PUBLIC_CLIENT_ID; rarely overridden)."
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

    @property
    def allow_insecure_urls(self) -> bool:
        """Shared insecure-URL posture (forwarded from ``deployment``)."""
        return self.deployment.allow_insecure_urls

    @field_validator("keychain_backend", mode="before")
    @classmethod
    def _normalize_keychain_backend(cls, value: object) -> object:
        # ``keychain_backend`` is ``Literal["auto", "file"]``; copy-pasted env
        # values like ``PIPEFY_AUTH_KEYCHAIN_BACKEND=' AUTO '`` should normalize
        # to ``"auto"`` rather than fail Literal validation with a cryptic enum
        # error. Case-fold only here: case is meaningful for the credential
        # fields, so they are validated as-is and never lowered.
        if isinstance(value, str):
            return value.strip().lower()
        return value

    def to_service_account(self) -> ServiceAccount | None:
        """Project the injected credentials into a :class:`ServiceAccount`, or ``None``.

        Returns ``None`` when the service-account tier is unconfigured; otherwise
        pairs the credentials with the token endpoint derived from ``deployment``.
        """
        if self.service_account is None:
            return None
        return ServiceAccount(
            token_url=self.deployment.oauth_token_url,
            client_id=self.service_account.client_id,
            client_secret=self.service_account.client_secret,
        )

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
            issuer_url=self.issuer_url,
            client_id=self.public_client_id,
        )

    @model_validator(mode="after")
    def _validate_endpoint_urls(self) -> Self:
        # ``issuer_url`` is the OIDC issuer and may carry a realm path
        # (Keycloak-style), but a stray query or fragment would corrupt the
        # ``.well-known/openid-configuration`` concatenation. The token endpoint
        # is derived (and gated) on the injected deployment, not re-checked here.
        security.assert_url_has_no_query_or_fragment(
            self.issuer_url, field_label="issuer_url"
        )
        security.validate_https_url(
            self.issuer_url,
            "issuer_url",
            allow_insecure=self.deployment.allow_insecure_urls,
        )
        return self


class JwtValidationConfig(BaseModel):
    """How this process validates an inbound bearer when it acts as a resource server.

    :class:`AuthConfig` configures the *outbound* side: how this process
    authenticates *to* Pipefy. This is the inbound counterpart that feeds
    :class:`~pipefy_auth.JwtValidator`. A pure value object; the edge sources its
    fields from ``PIPEFY_JWT_*`` and injects ``deployment`` (for the shared
    insecure-URL posture, forwarded via :attr:`allow_insecure_urls`).

    ``issuer_url`` is an override. Left unset, the consumer falls back to the
    issuer this process already logs into (the :class:`OidcClient` issuer): in a
    single-realm deployment the IdP that signs caller tokens is the same one we
    authenticate to, so it need not be configured twice. Set it only when inbound
    and outbound issuers diverge (token exchange, multi-tenant federation).
    """

    deployment: DeploymentConfig = Field(
        description=(
            "Host topology + insecure-URL posture, injected by reference (shared "
            "with the outbound side so the whole deployment toggles together)."
        ),
    )

    issuer_url: str | None = Field(
        default=None,
        pattern=security.URL_SHAPE_PATTERN,
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
        pattern=security.URL_SHAPE_PATTERN,
        description=(
            "Explicit JWKS endpoint override (env: PIPEFY_JWT_JWKS_URI). When "
            "unset, resolved from the issuer's discovery document."
        ),
    )

    @property
    def allow_insecure_urls(self) -> bool:
        """Shared insecure-URL posture (forwarded from ``deployment``)."""
        return self.deployment.allow_insecure_urls

    def resolve_issuer_url(self, default: str | None) -> str | None:
        """The inbound issuer: the explicit override, else ``default`` (the login issuer)."""
        return self.issuer_url or default

    @model_validator(mode="after")
    def _validate_configuration(self) -> Self:
        if self.verify_audience and not self.audience:
            raise ValueError("verify_audience requires audience (PIPEFY_JWT_AUDIENCE).")

        # Shape-check the URL fields: a realm path is allowed, so only a query
        # or fragment (which would corrupt URL building) is rejected.
        def _gate(value: str | None, label: str) -> None:
            if value is None:
                return
            security.assert_url_has_no_query_or_fragment(value, field_label=label)
            security.validate_https_url(
                value, label, allow_insecure=self.deployment.allow_insecure_urls
            )

        _gate(self.issuer_url, "issuer_url")
        _gate(self.jwks_uri, "jwks_uri")
        return self


__all__ = [
    "AuthConfig",
    "JwtValidationConfig",
    "ServiceAccountCredentials",
]
