"""MCP application settings: pure value objects built at the edge by a resolver.

The shared SDK / auth value objects are constructed from the ``pipefy_infra``
edge readers (:func:`read_client_env`, :func:`read_auth_env`); the MCP-only
models (``McpSettings``, ``JwtValidationSettings``, ``ResourceServerSettings``)
are built from MCP-owned readers in this module. ``base_url`` is read once (into
the SDK settings) and the auth OAuth token URL plus the shared insecure-URL
posture follow by injection.

The module-level ``settings`` is a lazily-built singleton (PEP 562
``__getattr__``): the first attribute access resolves it once, so importing this
module does no env / file IO and tests can set env before the first read.
"""

from __future__ import annotations

from typing import Any, Self

from pipefy_auth import AuthSettings, JwtValidationSettings
from pipefy_infra import security
from pipefy_infra.config import (
    PipefyBaseSettings,
    read_auth_env,
    read_client_env,
)
from pipefy_sdk import ClientSettings
from pydantic import AliasChoices, BaseModel, Field, ValidationError, model_validator
from pydantic_settings import SettingsConfigDict


class McpSettings(BaseModel):
    """MCP-server runtime knobs: transport, tool exposure, and envelope shape.

    A pure value object consumed only by the MCP server. The edge builds it from
    :func:`read_mcp_env`; see that reader for the ``PIPEFY_MCP_*`` env-name
    contract (and the one exception, the enrichment timeout, which keeps its
    historical ``PIPEFY_PERMISSION_DENIED_ENRICHMENT_TIMEOUT_SECONDS`` name).
    """

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
        description=(
            "Max wall time (seconds) for membership lookups when enriching GraphQL "
            "PERMISSION_DENIED errors (env: "
            "PIPEFY_PERMISSION_DENIED_ENRICHMENT_TIMEOUT_SECONDS). The enrichment "
            "code is MCP-only, so this lives here rather than on the SDK settings."
        ),
    )


class ResourceServerSettings(BaseModel):
    """This MCP server's identity as an OAuth protected resource (HTTP profile).

    The resource-server profile activates when ``resource_server_url`` is set: the
    ``--remote`` transport then validates inbound bearers and serves RFC 9728
    metadata, and the unauthenticated foundation profile is left untouched.

    Token *validation* knobs (issuer, audience, JWKS) are an auth concern and live
    in :class:`pipefy_auth.JwtValidationSettings`, alongside the validator they
    feed. This model carries only what is specific to *this* server's resource
    identity: its public URL and the scopes it requires. A pure value object;
    ``allow_insecure_urls`` is injected.
    """

    allow_insecure_urls: bool = Field(
        default=False,
        description="Shared insecure-URL posture, injected from PIPEFY_ALLOW_INSECURE_URLS.",
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


class Settings(BaseModel):
    """Composite of the MCP application's settings (pure value object).

    Built by :func:`resolve_settings` at the edge; it reads no env itself. The
    fields default to bare value objects so partial construction (e.g. in tests)
    works, but the resolver always supplies all five explicitly.
    """

    sdk: ClientSettings = Field(default_factory=ClientSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    mcp: McpSettings = Field(default_factory=McpSettings)
    jwt: JwtValidationSettings = Field(default_factory=JwtValidationSettings)
    rs: ResourceServerSettings = Field(default_factory=ResourceServerSettings)


# --------------------------------------------------------------------------- #
# Edge readers (MCP-owned): import no domain type, run no SSRF / shape gate.
# --------------------------------------------------------------------------- #
class _McpEnv(PipefyBaseSettings):
    """Reads the ``PIPEFY_MCP_*`` knobs (plus the historical enrichment-timeout var)."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_MCP_")

    unified_envelope: bool | None = Field(default=None)
    remote_mode: bool | None = Field(default=None)
    host: str | None = Field(default=None)
    port: int | None = Field(default=None)
    # Keeps its pre-relocation env name (not PIPEFY_MCP_*) so the move from the
    # SDK settings to McpSettings is structural, with no operator-facing change.
    permission_denied_enrichment_timeout_seconds: float | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PIPEFY_PERMISSION_DENIED_ENRICHMENT_TIMEOUT_SECONDS"
        ),
    )


class _RsEnv(PipefyBaseSettings):
    """Reads the ``PIPEFY_MCP_RS_*`` resource-server identity knobs."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_MCP_RS_")

    resource_server_url: str | None = Field(default=None)
    required_scopes: list[str] | None = Field(default=None)


class _JwtEnv(PipefyBaseSettings):
    """Reads the ``PIPEFY_JWT_*`` inbound-validation knobs.

    The inbound issuer override is read from the distinct TOML key
    ``jwt_issuer_url`` (env still ``PIPEFY_JWT_ISSUER_URL``) so it no longer
    collides with auth's outbound ``issuer_url`` TOML key; :func:`read_jwt_env`
    maps it back onto the model's ``issuer_url`` field.
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_JWT_")

    jwt_issuer_url: str | None = Field(
        default=None, validation_alias=AliasChoices("PIPEFY_JWT_ISSUER_URL")
    )
    audience: str | None = Field(default=None)
    verify_audience: bool | None = Field(default=None)
    jwks_uri: str | None = Field(default=None)


def read_mcp_env() -> dict[str, Any]:
    """Read the ``PIPEFY_MCP_*`` knobs as a raw mapping (operator-set keys only)."""
    return _McpEnv().model_dump(exclude_unset=True)


def read_rs_env() -> dict[str, Any]:
    """Read the ``PIPEFY_MCP_RS_*`` knobs as a raw mapping (operator-set keys only)."""
    return _RsEnv().model_dump(exclude_unset=True)


def read_jwt_env() -> dict[str, Any]:
    """Read the ``PIPEFY_JWT_*`` knobs, mapping ``jwt_issuer_url`` -> ``issuer_url``."""
    raw = _JwtEnv().model_dump(exclude_unset=True)
    if "jwt_issuer_url" in raw:
        raw["issuer_url"] = raw.pop("jwt_issuer_url")
    return raw


def resolve_settings() -> Settings:
    """Build the composite settings from the edge readers, with injection.

    Raises:
        ValueError: When validation fails (e.g. SSRF guard); message is user-facing.
    """
    try:
        sdk = ClientSettings(**read_client_env())
        auth = AuthSettings(
            **read_auth_env(),
            service_account_token_url=sdk.oauth_token_url,
            allow_insecure_urls=sdk.allow_insecure_urls,
        )
        mcp = McpSettings(**read_mcp_env())
        jwt = JwtValidationSettings(
            **read_jwt_env(), allow_insecure_urls=sdk.allow_insecure_urls
        )
        rs = ResourceServerSettings(
            **read_rs_env(), allow_insecure_urls=sdk.allow_insecure_urls
        )
        return Settings(sdk=sdk, auth=auth, mcp=mcp, jwt=jwt, rs=rs)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


_settings: Settings | None = None


def __getattr__(name: str) -> Any:
    # Lazily build and cache the singleton on first access, so importing this
    # module does no IO. ``from pipefy_mcp.settings import settings`` and
    # ``pipefy_mcp.settings.settings`` both route through here.
    if name == "settings":
        global _settings
        if _settings is None:
            _settings = resolve_settings()
        return _settings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AuthSettings",
    "ClientSettings",
    "JwtValidationSettings",
    "McpSettings",
    "ResourceServerSettings",
    "Settings",
    "read_jwt_env",
    "read_mcp_env",
    "read_rs_env",
    "resolve_settings",
]
# ``settings`` is intentionally omitted: it is a lazily-built singleton served by
# the module ``__getattr__`` above, not a module-level binding. Import it
# explicitly (``from pipefy_mcp.settings import settings``).
