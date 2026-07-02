from __future__ import annotations

from typing import Any, Literal, Self

from pipefy_auth import AuthSettings, JwtValidationSettings
from pipefy_infra import security
from pipefy_infra.config import PipefyTomlConfigSource
from pipefy_sdk import PipefySettings
from pydantic import AliasChoices, Field, ValidationError, model_validator
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
    names, so TOML keys are ``unified_envelope``, ``profile``, ``transport``,
    ``host``, ``port``.
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

    profile: Literal["local", "remote"] = Field(
        default="local",
        description=(
            "Launch profile (env: PIPEFY_MCP_PROFILE). 'local' (default) registers "
            "every tool and acts as one startup credential. 'remote' exposes ONLY "
            "tools explicitly marked remote-safe (default-deny) and validates an "
            "inbound bearer per request. Read at registration time, a startup "
            "decision, not per call."
        ),
    )

    transport: Literal["stdio", "http"] | None = Field(
        default=None,
        description=(
            "Wire the server speaks (env: PIPEFY_MCP_TRANSPORT). Left unset it "
            "defaults from the profile: 'local' speaks stdio, 'remote' serves over "
            "Streamable HTTP. Set it explicitly to run 'local' over loopback HTTP. "
            "'remote' over stdio is rejected: a per-request bearer has no stdio "
            "equivalent."
        ),
    )

    host: str = Field(
        default="127.0.0.1",
        description=(
            "Bind host for the Streamable HTTP transport (env: PIPEFY_MCP_HOST). "
            "Only consulted when serving over HTTP (--transport http); the stdio "
            "transport ignores it. Must stay loopback (the default): the HTTP "
            "transport refuses a non-loopback bind while it is unauthenticated."
        ),
    )

    port: int = Field(
        default=8000,
        description=(
            "Bind port for the Streamable HTTP transport (env: PIPEFY_MCP_PORT). "
            "Only consulted when serving over HTTP (--transport http)."
        ),
    )

    @model_validator(mode="after")
    def _resolve_transport(self) -> Self:
        """Fill the profile-derived transport default and reject 'remote' over stdio.

        Left unset, the transport follows the profile: 'local' speaks stdio,
        'remote' serves over HTTP. 'remote' cannot run over stdio, because it
        validates an inbound bearer per request and stdio carries none. After this
        runs, ``transport`` is always concrete.
        """
        if self.transport is None:
            self.transport = "http" if self.profile == "remote" else "stdio"
        elif self.profile == "remote" and self.transport == "stdio":
            raise ValueError(
                "the 'remote' profile requires the 'http' transport "
                "(a per-request bearer has no stdio equivalent)"
            )
        return self


class ResourceServerSettings(BaseSettings):
    """This MCP server's identity as an OAuth protected resource (HTTP profile).

    The resource-server profile activates when ``resource_server_url`` is set: the
    ``remote`` profile's HTTP transport then validates inbound bearers and serves
    RFC 9728 metadata, and the unauthenticated foundation profile is left untouched.

    Token *validation* knobs (issuer, audience, JWKS) are an auth concern and live
    in :class:`pipefy_auth.JwtValidationSettings`, alongside the validator they
    feed. This model carries only what is specific to *this* server's resource
    identity: its public URL and the scopes it requires.

    ``env_prefix="PIPEFY_MCP_RS_"`` does not collide with ``McpSettings``'
    ``PIPEFY_MCP_``: that model has no ``rs_*`` fields, so ``PIPEFY_MCP_RS_*``
    vars fall through its ``extra="ignore"`` gate. ``allow_insecure_urls`` is
    aliased to the shared ``PIPEFY_ALLOW_INSECURE_URLS`` so the whole deployment
    has a single insecure-URL posture.
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

    allow_insecure_urls: bool = Field(
        default=False,
        validation_alias=AliasChoices("PIPEFY_ALLOW_INSECURE_URLS"),
        description=(
            "When true (env: PIPEFY_ALLOW_INSECURE_URLS, shared across the "
            "deployment), resource_server_url may use http:// and internal hosts; "
            "local development only."
        ),
    )

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
            stripped, "resource_server_url", allow_insecure=self.allow_insecure_urls
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
    jwt: JwtValidationSettings = Field(default_factory=JwtValidationSettings)
    rs: ResourceServerSettings = Field(default_factory=ResourceServerSettings)


def resolve_mcp_settings(
    *,
    profile: str | None,
    transport: str | None,
    host: str | None,
    port: int | None,
) -> McpSettings:
    """Resolve :class:`McpSettings` honoring the launch flags as init-kwargs.

    The composition root for the launch surface, mirroring
    :func:`pipefy_cli.settings.resolve_cli_settings`: the flags are folded in as
    init-kwargs, so argv outranks the environment (``init_kwargs > env > dotenv >
    config.toml``, per ``settings_customise_sources``). Only the flags actually
    passed override the environment; the rest fall back to ``PIPEFY_MCP_*`` (or
    the field defaults). The returned settings have a concrete ``transport`` (the
    profile-derived default is applied by the model validator).

    Credential and resource-server config stay sourced from the process
    environment; this resolves only the launch surface the flags control.

    Raises:
        ValueError: On an unknown value or an incompatible profile/transport pair
            (e.g. 'remote' over stdio); the message is user-facing.
    """
    init: dict[str, Any] = {}
    if profile is not None:
        init["profile"] = profile
    if transport is not None:
        init["transport"] = transport
    if host is not None:
        init["host"] = host
    if port is not None:
        init["port"] = port
    try:
        return McpSettings(**init)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


settings = Settings()

__all__ = [
    "AuthSettings",
    "JwtValidationSettings",
    "McpSettings",
    "PipefySettings",
    "ResourceServerSettings",
    "Settings",
    "resolve_mcp_settings",
    "settings",
]
