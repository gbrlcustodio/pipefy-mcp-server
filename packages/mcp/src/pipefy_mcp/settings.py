"""Resolve Pipefy + auth + MCP settings (the MCP application's env edge).

One of the two composition roots that own env reading (the other is
``pipefy_cli``). The library value objects read no env; here each concept gets a
thin ``pydantic-settings`` reader that adds only its ``env_prefix`` (and TOML
section) on top of :class:`~pipefy_infra.settings_base.PipefyBaseSettings`.

``resolve_mcp_settings`` builds ONE :class:`DeploymentConfig` and injects it by
reference into the SDK / auth / jwt / resource-server readers, so host topology
and the insecure-URL posture cannot diverge. Resolution is lazy: importing this
module does no env / file IO; :func:`get_settings` resolves on first call and
caches; :func:`reset_settings` clears the cache (tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from pipefy_auth import AuthConfig, JwtValidationConfig, ServiceAccountCredentials
from pipefy_infra import security
from pipefy_infra.coerce import OPAQUE_CREDENTIAL_PATTERN, strip_if_str
from pipefy_infra.deployment import DeploymentConfig
from pipefy_infra.settings_base import PipefyBaseSettings
from pipefy_sdk import SdkConfig
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict


class DeploymentSettings(DeploymentConfig, PipefyBaseSettings):
    """Reads the deployment values under the ``PIPEFY_`` prefix / top-level TOML."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")


class SdkEnvSettings(SdkConfig, PipefyBaseSettings):
    """Reads the SDK knobs under ``PIPEFY_``; ``deployment`` is injected."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")


class AuthEnvSettings(AuthConfig, PipefyBaseSettings):
    """Reads the login-subsystem fields under ``PIPEFY_AUTH_`` / ``[auth]``.

    ``static_token`` keeps its product-root env name (``PIPEFY_TOKEN``) via a
    cross-prefix alias; ``deployment`` / ``service_account`` are injected.
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_AUTH_")
    _toml_section = "auth"

    static_token: str | None = Field(
        default=None,
        pattern=OPAQUE_CREDENTIAL_PATTERN,
        validation_alias=AliasChoices("PIPEFY_TOKEN"),
    )

    _strip_static = field_validator("static_token", mode="before")(strip_if_str)


class JwtEnvSettings(JwtValidationConfig, PipefyBaseSettings):
    """Reads the inbound-validation fields under ``PIPEFY_JWT_`` / ``[jwt]``."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_JWT_")
    _toml_section = "jwt"


class ServiceAccountEnvSettings(PipefyBaseSettings):
    """Reads the service-account credentials under ``PIPEFY_SERVICE_ACCOUNT_`` / ``[service_account]``.

    Fields are optional so absence is representable; ``to_credentials()`` builds
    the both-required :class:`ServiceAccountCredentials`, ``None`` when both are
    unset, and raises when exactly one is set (fail-loud on partial config).
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_SERVICE_ACCOUNT_")
    _toml_section = "service_account"

    client_id: str | None = None
    client_secret: str | None = None

    def to_credentials(self) -> ServiceAccountCredentials | None:
        if self.client_id is None and self.client_secret is None:
            return None
        return ServiceAccountCredentials(
            client_id=self.client_id,  # type: ignore[arg-type]
            client_secret=self.client_secret,  # type: ignore[arg-type]
        )


class McpSettings(PipefyBaseSettings):
    """MCP-server runtime knobs: transport, tool exposure, and envelope shape.

    Consumed only by the MCP server. ``env_prefix="PIPEFY_MCP_"`` keeps the
    operator-facing ``PIPEFY_MCP_*`` env vars; the shared ``config.toml`` source
    keys off the bare field names. ``permission_denied_enrichment_timeout_seconds``
    is MCP-only but keeps its un-prefixed env name via a ``validation_alias``.
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_MCP_")

    unified_envelope: bool = Field(
        default=True,
        description=(
            "When true (env: PIPEFY_MCP_UNIFIED_ENVELOPE), migrated MCP tools return "
            "{success, data, message?, pagination?}. When false, legacy shapes. "
            "Read at call time, not cached at import."
        ),
    )

    remote_mode: bool = Field(
        default=False,
        description=(
            "When true (env: PIPEFY_MCP_REMOTE_MODE), the server runs the hosted/remote "
            "profile and exposes ONLY tools explicitly marked remote-safe (default-deny). "
            "When false (default), all tools register (local stdio profile). Read at "
            "registration time, a startup decision, not per call."
        ),
    )

    host: str = Field(
        default="127.0.0.1",
        description=(
            "Bind host for the Streamable HTTP transport (env: PIPEFY_MCP_HOST). "
            "Only consulted when the server is launched with --remote; the stdio "
            "profile ignores it. Must stay loopback (the default): the HTTP "
            "transport refuses a non-loopback bind while it is unauthenticated."
        ),
    )

    port: int = Field(
        default=8000,
        description=(
            "Bind port for the Streamable HTTP transport (env: PIPEFY_MCP_PORT). "
            "Only consulted when the server is launched with --remote."
        ),
    )

    permission_denied_enrichment_timeout_seconds: float = Field(
        default=5.0,
        ge=0.1,
        le=120.0,
        validation_alias=AliasChoices(
            "PIPEFY_PERMISSION_DENIED_ENRICHMENT_TIMEOUT_SECONDS"
        ),
        description=(
            "Max wall time (seconds) for membership lookups when enriching GraphQL "
            "PERMISSION_DENIED errors (env: PIPEFY_PERMISSION_DENIED_ENRICHMENT_TIMEOUT_SECONDS, "
            "kept un-prefixed for back-compat)."
        ),
    )


class ResourceServerSettings(PipefyBaseSettings):
    """This MCP server's identity as an OAuth protected resource (HTTP profile).

    The resource-server profile activates when ``resource_server_url`` is set: the
    ``--remote`` transport then validates inbound bearers and serves RFC 9728
    metadata. Token *validation* knobs (issuer, audience, JWKS) are an auth
    concern and live in :class:`pipefy_auth.JwtValidationConfig`; this model
    carries only this server's resource identity. ``deployment`` is injected so
    the insecure-URL posture forwards off the one shared instance.
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_MCP_RS_")

    deployment: DeploymentConfig = Field(
        description="Host topology + insecure-URL posture, injected by reference.",
    )

    resource_server_url: str | None = Field(
        default=None,
        description=(
            "Public canonical URL of this MCP server as an OAuth protected "
            "resource (env: PIPEFY_MCP_RS_RESOURCE_SERVER_URL). Decoupled from the "
            "bind host, so behind a proxy it is the public origin, not host/port. "
            "Include the /mcp endpoint path, e.g. https://mcp.pipefy.com/mcp: it "
            "becomes the RFC 9728 resource identifier and the base for the "
            "protected-resource metadata route. Setting it activates the profile."
        ),
    )

    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "Scopes a token must carry (env: PIPEFY_MCP_RS_REQUIRED_SCOPES as "
            "JSON). FastMCP returns 403 when any is missing."
        ),
    )

    @property
    def allow_insecure_urls(self) -> bool:
        """Shared insecure-URL posture (forwarded from ``deployment``)."""
        return self.deployment.allow_insecure_urls

    @model_validator(mode="after")
    def _validate_configuration(self) -> Self:
        if self.resource_server_url is None:
            return self
        # Persist the stripped value: surrounding whitespace in an env var would
        # otherwise survive into the RFC 9728 resource identifier. The /mcp
        # endpoint path is expected, so only a query or fragment is forbidden.
        stripped = self.resource_server_url.strip()
        self.resource_server_url = stripped
        security.assert_url_has_no_query_or_fragment(
            stripped, field_label="resource_server_url"
        )
        security.validate_https_url(
            stripped,
            "resource_server_url",
            allow_insecure=self.deployment.allow_insecure_urls,
        )
        return self


@dataclass(frozen=True)
class Settings:
    """The resolved MCP configuration: the library value objects + MCP-edge models.

    A plain composite built by :func:`resolve_mcp_settings`; ``pipefy`` / ``auth``
    / ``jwt`` / ``rs`` all share the one injected DeploymentConfig.
    """

    pipefy: SdkConfig
    auth: AuthConfig
    mcp: McpSettings
    jwt: JwtValidationConfig
    rs: ResourceServerSettings


def resolve_mcp_settings() -> Settings:
    """Build the MCP :class:`Settings`, reading env / dotenv / config.toml.

    Raises:
        ValueError / ValidationError: When any reader fails validation (SSRF guard,
            partial service-account pair, bad URL shape).
    """
    deployment = DeploymentSettings()
    service_account = ServiceAccountEnvSettings().to_credentials()
    return Settings(
        pipefy=SdkEnvSettings(deployment=deployment),
        auth=AuthEnvSettings(deployment=deployment, service_account=service_account),
        mcp=McpSettings(),
        jwt=JwtEnvSettings(deployment=deployment),
        rs=ResourceServerSettings(deployment=deployment),
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide MCP settings, resolving + caching on first call."""
    global _settings
    if _settings is None:
        _settings = resolve_mcp_settings()
    return _settings


def reset_settings() -> None:
    """Clear the cached settings so the next :func:`get_settings` re-resolves (tests)."""
    global _settings
    _settings = None


__all__ = [
    "AuthEnvSettings",
    "DeploymentSettings",
    "JwtEnvSettings",
    "McpSettings",
    "ResourceServerSettings",
    "SdkEnvSettings",
    "ServiceAccountEnvSettings",
    "Settings",
    "get_settings",
    "reset_settings",
    "resolve_mcp_settings",
]
