"""Pure value objects for auth settings (outbound auth + inbound JWT validation).

Owns every value that describes *how* to authenticate against Pipefy. These are
plain :class:`pydantic.BaseModel` value objects: they validate themselves but
read no env / file. The application edge builds them from
:func:`pipefy_infra.config.read_auth_env` (which owns the ``PIPEFY_AUTH_*`` /
``PIPEFY_TOKEN`` / ``PIPEFY_SERVICE_ACCOUNT_*`` env-name contract) and injects the
deployment-derived values:

* ``service_account_token_url``: the OAuth token endpoint, derived from the SDK's
  ``base_url`` (``ClientSettings.oauth_token_url``). Auth never references the SDK
  type; the caller passes the resolved URL in, so the host root is read once.
* ``allow_insecure_urls``: the shared insecure-URL posture, injected so the whole
  deployment toggles together.
"""

from __future__ import annotations

from typing import Literal, Self

from pipefy_infra import security
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

# Production default.
DEFAULT_ISSUER_URL = "https://signin.pipefy.com/realms/pipefy"

# Opaque secret / identifier strings: reject leading / trailing whitespace and
# blank values. Anything in between is opaque to us (the IdP defines the format).
_OPAQUE_CREDENTIAL_PATTERN = r"^\S(?:.*\S)?$"


class AuthSettings(BaseModel):
    """Outbound auth configuration: how this process authenticates *to* Pipefy.

    A pure value object. The credentials and OIDC knobs are this model's own
    values (the edge sources them from ``PIPEFY_AUTH_*`` / ``PIPEFY_TOKEN`` /
    ``PIPEFY_SERVICE_ACCOUNT_*``); ``service_account_token_url`` and
    ``allow_insecure_urls`` are injected by the caller (see the module docstring).
    SSRF validation runs inline as a ``model_validator(mode="after")`` so direct
    construction is safe.
    """

    # Injected by the caller (host topology + shared flag).
    service_account_token_url: str | None = Field(
        default=None,
        description=(
            "OAuth 2.0 token endpoint for the service-account tier, derived from the "
            "SDK base_url (ClientSettings.oauth_token_url) and injected by the edge."
        ),
    )

    allow_insecure_urls: bool = Field(
        default=False,
        description=(
            "Shared insecure-URL posture, injected from PIPEFY_ALLOW_INSECURE_URLS "
            "so http:// and internal hosts are gated the same way deployment-wide."
        ),
    )

    static_token: str | None = Field(
        default=None,
        pattern=_OPAQUE_CREDENTIAL_PATTERN,
        description=(
            "Pre-issued bearer for the static-token tier (env: PIPEFY_TOKEN). "
            "When set, outranks both the service-account triple and any stored session."
        ),
    )

    service_account_client_id: str | None = Field(
        default=None,
        pattern=_OPAQUE_CREDENTIAL_PATTERN,
        description="Service-account OAuth client_id (env: PIPEFY_SERVICE_ACCOUNT_CLIENT_ID).",
    )

    service_account_client_secret: str | None = Field(
        default=None,
        pattern=_OPAQUE_CREDENTIAL_PATTERN,
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

    @field_validator(
        "static_token",
        "service_account_client_id",
        "service_account_client_secret",
        "issuer_url",
        "client_id",
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

    def to_service_account(self) -> ServiceAccount | None:
        """Project the triple into a :class:`ServiceAccount`, or ``None`` if incomplete."""
        if (
            self.service_account_token_url
            and self.service_account_client_id
            and self.service_account_client_secret
        ):
            return ServiceAccount(
                token_url=self.service_account_token_url,
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
        # ``issuer_url`` is the OIDC issuer and may carry a realm path. The
        # service-account token URL is injected already-derived from the SDK
        # base_url (validated there), so it is not re-gated here.
        self.issuer_url = security.sanitize_url(
            self.issuer_url,
            field_label="issuer_url",
            allow_insecure=self.allow_insecure_urls,
        )
        return self


class JwtValidationSettings(BaseModel):
    """How this process validates an inbound bearer when it acts as a resource server.

    :class:`AuthSettings` configures the *outbound* side: how this process
    authenticates *to* Pipefy. This is the inbound counterpart that feeds
    :class:`~pipefy_auth.JwtValidator`. A pure value object; the edge sources its
    fields from ``PIPEFY_JWT_*`` and injects ``allow_insecure_urls``.

    ``issuer_url`` is an override. Left unset, the consumer falls back to the
    issuer this process already logs into (the :class:`OidcClient` issuer): in a
    single-realm deployment the IdP that signs caller tokens is the same one we
    authenticate to, so it need not be configured twice. Set it only when inbound
    and outbound issuers diverge (token exchange, multi-tenant federation).
    """

    allow_insecure_urls: bool = Field(
        default=False,
        description=(
            "Shared insecure-URL posture, injected from PIPEFY_ALLOW_INSECURE_URLS."
        ),
    )

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
