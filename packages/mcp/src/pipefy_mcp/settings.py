from __future__ import annotations

from typing import Self

from pipefy_auth import AuthSettings
from pipefy_infra import security
from pipefy_infra.config import PipefyTomlConfigSource
from pipefy_sdk import PipefySettings
from pydantic import Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class McpSettings(BaseSettings):
    """MCP-server runtime knobs: transport, tool exposure, and envelope shape.

    These are consumed only by the MCP server, so they live here rather than in
    the SDK's API-connection settings. Fields drop the ``mcp_`` prefix because
    the ``settings.mcp`` namespace already supplies it; ``env_prefix="PIPEFY_MCP_"``
    re-attaches it so the operator-facing ``PIPEFY_MCP_*`` env vars stay
    byte-identical. The shared ``config.toml`` source keys off the bare field
    names, so TOML keys are ``unified_envelope``, ``remote_mode``, ``host``,
    ``port``.
    """

    model_config = SettingsConfigDict(
        env_prefix="PIPEFY_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence: init_kwargs > env > dotenv > config.toml > file_secret.
        # Reads the shared config.toml; keys are this class's bare field names.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            PipefyTomlConfigSource(settings_cls),
            file_secret_settings,
        )

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


class ResourceServerSettings(BaseSettings):
    """OAuth resource-server knobs for inbound bearer validation (HTTP profile).

    Off by default: only the ``--remote`` HTTP transport consults these, and
    only when ``enabled`` so the unauthenticated foundation profile is
    unaffected. Kept separate from :class:`McpSettings` (transport knobs) and the
    repo ``AuthSettings`` (outbound: how this process authenticates *to* Pipefy):
    ``issuer_url`` here is the *inbound* issuer that signs caller tokens, which
    can differ from the issuer this process logs into.

    ``env_prefix="PIPEFY_MCP_RS_"`` does not collide with ``McpSettings``'
    ``PIPEFY_MCP_``: that model has no ``rs_*`` fields, so ``PIPEFY_MCP_RS_*``
    vars fall through its ``extra="ignore"`` gate.
    """

    model_config = SettingsConfigDict(
        env_prefix="PIPEFY_MCP_RS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence: init_kwargs > env > dotenv > config.toml > file_secret.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            PipefyTomlConfigSource(settings_cls),
            file_secret_settings,
        )

    enabled: bool = Field(
        default=False,
        description=(
            "Master switch (env: PIPEFY_MCP_RS_ENABLED). When true, the HTTP "
            "transport validates an inbound bearer on every request and may bind "
            "off-loopback. When false (default), the HTTP profile stays "
            "unauthenticated and loopback-only."
        ),
    )

    issuer_url: str | None = Field(
        default=None,
        description=(
            "Inbound OIDC issuer that signs caller tokens (env: "
            "PIPEFY_MCP_RS_ISSUER_URL). The JWKS endpoint is resolved from its "
            "discovery document. Required when enabled."
        ),
    )

    audience: str | None = Field(
        default=None,
        description=(
            "Expected token audience (env: PIPEFY_MCP_RS_AUDIENCE). Required when "
            "verify_audience is true."
        ),
    )

    verify_audience: bool = Field(
        default=False,
        description=(
            "When true (env: PIPEFY_MCP_RS_VERIFY_AUDIENCE), reject tokens whose "
            "aud does not include audience. Defaults false for the same-audience "
            "interim, which runs before the IdP issues an aud claim."
        ),
    )

    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "Scopes a token must carry (env: PIPEFY_MCP_RS_REQUIRED_SCOPES as "
            "JSON). FastMCP returns 403 when any is missing."
        ),
    )

    resource_server_url: str | None = Field(
        default=None,
        description=(
            "Public canonical URL of this MCP server as an OAuth protected "
            "resource (env: PIPEFY_MCP_RS_RESOURCE_SERVER_URL). Decoupled from the "
            "bind host, so behind a proxy it is the public origin, not host/port. "
            "Include the /mcp endpoint path, e.g. https://mcp.pipefy.com/mcp: it "
            "becomes the RFC 9728 resource identifier and the base for the "
            "protected-resource metadata route. Required when enabled."
        ),
    )

    allow_insecure_urls: bool = Field(
        default=False,
        description=(
            "When true (env: PIPEFY_MCP_RS_ALLOW_INSECURE_URLS), resource-server "
            "URLs may use http:// and internal hosts; local development only."
        ),
    )

    jwks_uri: str | None = Field(
        default=None,
        description=(
            "Explicit JWKS endpoint override (env: PIPEFY_MCP_RS_JWKS_URI). When "
            "unset, resolved from the issuer's discovery document."
        ),
    )

    @model_validator(mode="after")
    def _validate_when_enabled(self) -> Self:
        # Inert unless enabled, so the default (disabled) profile never trips on
        # absent URLs. ``issuer_url`` and ``resource_server_url`` may carry a path
        # (a Keycloak realm; the /mcp endpoint), so they only forbid a query or
        # fragment that would corrupt downstream concatenation, not any path.
        if not self.enabled:
            return self
        if not self.issuer_url or not self.resource_server_url:
            raise ValueError(
                "resource-server profile requires issuer_url and "
                "resource_server_url when enabled "
                "(PIPEFY_MCP_RS_ISSUER_URL / PIPEFY_MCP_RS_RESOURCE_SERVER_URL)."
            )
        if self.verify_audience and not self.audience:
            raise ValueError(
                "verify_audience requires audience (PIPEFY_MCP_RS_AUDIENCE)."
            )
        for value, label in (
            (self.issuer_url, "issuer_url"),
            (self.resource_server_url, "resource_server_url"),
            (self.jwks_uri, "jwks_uri"),
        ):
            if value is None:
                continue
            stripped = value.strip()
            security.assert_url_has_no_query_or_fragment(stripped, field_label=label)
            security.validate_https_url(
                stripped, label, allow_insecure=self.allow_insecure_urls
            )
        return self


class Settings(BaseSettings):
    """Application configuration via pydantic-settings.

    Each nested model owns its own env loading (``env_prefix="PIPEFY_"``).
    The composition deliberately does NOT set ``env_nested_delimiter`` — that
    flag splits any matching env var (e.g. ``AUTH_BASE_URL``) into a nested
    path, which would bypass each model's prefix gate and let unprefixed env
    vars hijack auth fields. Both nested models run their own SSRF / shape
    checks at construction; no parent-side ``_validate_*`` validator is needed.
    """

    model_config = SettingsConfigDict(extra="ignore")

    pipefy: PipefySettings = Field(default_factory=PipefySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    mcp: McpSettings = Field(default_factory=McpSettings)
    rs: ResourceServerSettings = Field(default_factory=ResourceServerSettings)


settings = Settings()

__all__ = [
    "AuthSettings",
    "McpSettings",
    "PipefySettings",
    "ResourceServerSettings",
    "Settings",
    "settings",
]
