from __future__ import annotations

from typing import Self

from pipefy_auth import AuthSettings, JwtValidationSettings
from pipefy_infra import security
from pipefy_infra.config import InsecureUrlSettings, PipefyBaseSettings
from pipefy_sdk import ClientSettings
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class McpSettings(PipefyBaseSettings):
    """MCP-server runtime knobs: transport, tool exposure, and envelope shape.

    These are consumed only by the MCP server, so they live here rather than in
    the SDK's API-connection settings. Fields drop the ``mcp_`` prefix because
    the ``settings.mcp`` namespace already supplies it; ``env_prefix="PIPEFY_MCP_"``
    re-attaches it so the operator-facing ``PIPEFY_MCP_*`` env vars stay
    byte-identical. The shared ``config.toml`` source keys off the bare field
    names, so TOML keys are ``unified_envelope``, ``remote_mode``, ``host``,
    ``port``.
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


class ResourceServerSettings(InsecureUrlSettings):
    """This MCP server's identity as an OAuth protected resource (HTTP profile).

    The resource-server profile activates when ``resource_server_url`` is set: the
    ``--remote`` transport then validates inbound bearers and serves RFC 9728
    metadata, and the unauthenticated foundation profile is left untouched.

    Token *validation* knobs (issuer, audience, JWKS) are an auth concern and live
    in :class:`pipefy_auth.JwtValidationSettings`, alongside the validator they
    feed. This model carries only what is specific to *this* server's resource
    identity: its public URL and the scopes it requires.

    ``env_prefix="PIPEFY_MCP_RS_"`` does not collide with ``McpSettings``'
    ``PIPEFY_MCP_``: that model has no ``rs_*`` fields, so ``PIPEFY_MCP_RS_*``
    vars fall through its ``extra="ignore"`` gate.
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_MCP_RS_")

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

    @model_validator(mode="after")
    def _validate_configuration(self) -> Self:
        if self.resource_server_url is None:
            return self
        self.resource_server_url = security.sanitize_url(
            self.resource_server_url,
            field_label="resource_server_url",
            allow_insecure=self.allow_insecure_urls,
        )
        return self


class Settings(BaseSettings):
    """Application configuration via pydantic-settings.

    Each nested model owns its own env loading under its own ``env_prefix``
    (``PIPEFY_``, ``PIPEFY_AUTH_``, ``PIPEFY_MCP_``, ``PIPEFY_JWT_``,
    ``PIPEFY_MCP_RS_``). The composition deliberately does NOT set
    ``env_nested_delimiter``: that flag would split a matching env var (e.g.
    ``AUTH_BASE_URL``) into a nested path, bypassing each model's prefix gate and
    letting unprefixed env vars hijack auth fields. Each nested model runs its
    own SSRF / shape checks at construction.
    """

    model_config = SettingsConfigDict(extra="ignore")

    sdk: ClientSettings = Field(default_factory=ClientSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    mcp: McpSettings = Field(default_factory=McpSettings)
    jwt: JwtValidationSettings = Field(default_factory=JwtValidationSettings)
    rs: ResourceServerSettings = Field(default_factory=ResourceServerSettings)


settings = Settings()

__all__ = [
    "AuthSettings",
    "JwtValidationSettings",
    "ClientSettings",
    "McpSettings",
    "ResourceServerSettings",
    "Settings",
    "settings",
]
