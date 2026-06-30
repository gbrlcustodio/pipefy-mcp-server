"""Parse the environment into auth value objects (the auth env edge).

The auth stage of the settings parse pipeline. Given the one
:class:`~pipefy_infra.deployment.DeploymentConfig` (already parsed by
``pipefy_infra.env``), these loaders read ``PIPEFY_TOKEN`` /
``PIPEFY_SERVICE_ACCOUNT_*`` / ``PIPEFY_AUTH_*`` / ``PIPEFY_JWT_*`` and project
them into the refined value objects the auth API consumes: a
:class:`~pipefy_auth.resolver.CredentialSources` bundle for outbound auth and a
:class:`~pipefy_auth.verification.JwtValidationInputs` witness for inbound
validation.

The readers are transient parser scaffolding. The both-or-neither service-account
parse, the OIDC projection, and the issuer override-or-default resolution all live
here as loader internals, so the value objects stay free of env concerns.

Importing this module pulls ``pydantic-settings``; it is the auth env edge,
deliberately kept out of the env-free ``import pipefy_auth`` path.
"""

from __future__ import annotations

from pipefy_infra import security
from pipefy_infra.coerce import OPAQUE_CREDENTIAL_PATTERN, lower_if_str
from pipefy_infra.deployment import DeploymentConfig
from pipefy_infra.settings_base import PipefyBaseSettings
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import SettingsConfigDict  # noqa: TID251

from pipefy_auth.identity import DEFAULT_AUTH_CLIENT_ID, OidcClient
from pipefy_auth.resolver import CredentialSources, ServiceAccount
from pipefy_auth.verification import JwtValidationInputs

# Production default OIDC issuer (canonical Pipefy production IdP).
DEFAULT_ISSUER_URL = "https://signin.pipefy.com/realms/pipefy"


class _LoginReader(PipefyBaseSettings):
    """Reads the login-subsystem fields under ``PIPEFY_AUTH_`` / ``[auth]``.

    ``static_token`` keeps its product-root env name (``PIPEFY_TOKEN``) via a
    cross-prefix alias.
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_AUTH_")
    _toml_section = "auth"

    static_token: str | None = Field(
        default=None,
        pattern=OPAQUE_CREDENTIAL_PATTERN,
        validation_alias=AliasChoices("PIPEFY_TOKEN"),
    )
    issuer_url: str = Field(
        default=DEFAULT_ISSUER_URL, pattern=security.URL_SHAPE_PATTERN
    )
    public_client_id: str = Field(
        default=DEFAULT_AUTH_CLIENT_ID, pattern=OPAQUE_CREDENTIAL_PATTERN
    )
    disable_stored_session: bool = False
    keychain_backend: str = Field(default="auto")

    _fold_keychain_backend = field_validator("keychain_backend", mode="before")(
        lower_if_str
    )


class _ServiceAccountReader(PipefyBaseSettings):
    """Reads the service-account credentials under ``PIPEFY_SERVICE_ACCOUNT_``."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_SERVICE_ACCOUNT_")
    _toml_section = "service_account"

    client_id: str | None = None
    client_secret: str | None = None


class _JwtReader(PipefyBaseSettings):
    """Reads the inbound-validation fields under ``PIPEFY_JWT_`` / ``[jwt]``."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_JWT_")
    _toml_section = "jwt"

    issuer_url: str | None = Field(default=None, pattern=security.URL_SHAPE_PATTERN)
    audience: str | None = None
    verify_audience: bool = False
    jwks_uri: str | None = Field(default=None, pattern=security.URL_SHAPE_PATTERN)


def _service_account(
    reader: _ServiceAccountReader, deployment: DeploymentConfig
) -> ServiceAccount | None:
    """Project the service-account credential pair, or ``None`` (both-or-neither).

    Raises:
        ValueError: When exactly one of client_id / client_secret is set.
    """
    if reader.client_id is None and reader.client_secret is None:
        return None
    if reader.client_id is None or reader.client_secret is None:
        raise ValueError(
            "Service-account tier needs both PIPEFY_SERVICE_ACCOUNT_CLIENT_ID and "
            "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET (or neither)."
        )
    return ServiceAccount(
        token_url=deployment.oauth_token_url,
        client_id=reader.client_id,
        client_secret=reader.client_secret,
    )


def load_auth(
    deployment: DeploymentConfig,
) -> tuple[CredentialSources, str]:
    """Parse outbound-auth credentials from the environment.

    Returns the :class:`CredentialSources` bundle alongside ``keychain_backend``
    (a pre-resolve side-effect config, applied by the consumer before any
    keychain probe, not a credential source). The HTTPS/SSRF posture is applied
    to the OIDC issuer here, using the shared ``deployment`` posture.

    Returns:
        ``(sources, keychain_backend)``.

    Raises:
        pydantic.ValidationError / ValueError: On bad shape, partial
            service-account pair, or an issuer that violates the posture policy.
    """
    login = _LoginReader()
    service_account = _service_account(_ServiceAccountReader(), deployment)

    oidc_client: OidcClient | None = None
    if not login.disable_stored_session:
        security.validate_https_url(
            login.issuer_url,
            "issuer_url",
            allow_insecure=deployment.allow_insecure_urls,
        )
        oidc_client = OidcClient(
            issuer_url=login.issuer_url, client_id=login.public_client_id
        )

    sources = CredentialSources(
        static_token=login.static_token,
        service_account=service_account,
        oidc_client=oidc_client,
    )
    return sources, login.keychain_backend


def load_jwt_validation(
    deployment: DeploymentConfig,
    *,
    default_issuer_url: str | None,
) -> JwtValidationInputs | None:
    """Parse inbound JWT-validation inputs, resolving the issuer fallback.

    The inbound issuer is the ``PIPEFY_JWT_ISSUER_URL`` override if set, else
    ``default_issuer_url`` (the issuer this process logs into, reused in a
    single-realm deployment). Returns ``None`` when neither is available: the
    consumer treats that as "no issuer to validate against". The HTTPS/SSRF
    posture is applied to the resolved issuer and any ``jwks_uri`` override.

    Raises:
        pydantic.ValidationError / ValueError: On bad shape or posture violation.
    """
    jwt = _JwtReader()
    issuer_url = jwt.issuer_url or default_issuer_url
    if issuer_url is None:
        return None

    for value, label in ((issuer_url, "issuer_url"), (jwt.jwks_uri, "jwks_uri")):
        if value is not None:
            security.validate_https_url(
                value, label, allow_insecure=deployment.allow_insecure_urls
            )

    return JwtValidationInputs(
        issuer_url=issuer_url,
        jwks_uri=jwt.jwks_uri,
        audience=jwt.audience,
        verify_audience=jwt.verify_audience,
        allow_insecure_urls=deployment.allow_insecure_urls,
    )


__all__ = ["DEFAULT_ISSUER_URL", "load_auth", "load_jwt_validation"]
