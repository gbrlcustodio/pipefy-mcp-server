from __future__ import annotations

from pipefy_auth import AuthSettings
from pipefy_infra.config import PipefyTomlConfigSource
from pipefy_sdk import PipefySettings
from pydantic import Field
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
        # Reads the shared config.toml; keys are this model's bare field names.
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


settings = Settings()

__all__ = ["AuthSettings", "McpSettings", "PipefySettings", "Settings", "settings"]
