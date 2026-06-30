"""Resolve the MCP runtime: parse the environment into value objects (the MCP edge).

One of the two composition roots that own env reading (the other is
``pipefy_cli``). It composes the libraries' loaders around one
:class:`~pipefy_infra.deployment.DeploymentConfig` and adds the MCP-only knobs
(transport, envelope shape) and resource-server identity, which are genuinely
app-specific and stay app-edge parsers.

The result, :class:`McpRuntime`, holds only parsed value objects and primitives.
Resolution is lazy: importing this module does no env / file IO;
:func:`get_runtime` resolves on first call and caches; :func:`reset_runtime`
clears the cache (tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from pipefy_auth.env import load_auth, load_jwt_validation
from pipefy_auth.resolver import CredentialSources
from pipefy_auth.verification import JwtValidationInputs
from pipefy_infra import security
from pipefy_infra.env import load_deployment
from pipefy_infra.settings_base import PipefyBaseSettings
from pipefy_sdk.endpoints import PipefyEndpoints
from pipefy_sdk.env import load_sdk
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import SettingsConfigDict  # noqa: TID251


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


class ResourceServerIdentity(BaseModel):
    """This MCP server's identity as an OAuth protected resource (HTTP profile).

    A frozen value object. The resource-server profile activates when
    ``resource_server_url`` is set: the ``--remote`` transport then validates
    inbound bearers and serves RFC 9728 metadata. Token *validation* knobs live
    in :class:`~pipefy_auth.JwtValidationInputs`; this carries only the resource
    identity. Shape is validated here; the HTTPS/insecure posture is applied at
    the loader.
    """

    model_config = ConfigDict(frozen=True)

    resource_server_url: str | None = Field(
        default=None, pattern=security.URL_SHAPE_PATTERN
    )
    required_scopes: list[str] | None = None

    @model_validator(mode="after")
    def _validate_url_shape(self) -> Self:
        if self.resource_server_url is not None:
            # The /mcp endpoint path is expected in the RFC 9728 resource
            # identifier, so only a query or fragment is forbidden.
            security.assert_url_has_no_query_or_fragment(
                self.resource_server_url, field_label="resource_server_url"
            )
        return self


class _ResourceServerReader(PipefyBaseSettings):
    """Reads this server's resource identity under ``PIPEFY_MCP_RS_``."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_MCP_RS_")

    resource_server_url: str | None = Field(
        default=None, pattern=security.URL_SHAPE_PATTERN
    )
    required_scopes: list[str] | None = None


@dataclass(frozen=True)
class McpRuntime:
    """The resolved MCP runtime: parsed value objects + MCP-only knobs.

    Built by :func:`resolve_mcp_runtime`; the endpoints, credentials, and JWT
    inputs all derive from the one DeploymentConfig, so host and posture cannot
    diverge.
    """

    endpoints: PipefyEndpoints
    allow_insecure_urls: bool
    reuse_schema: bool
    default_webhook_name: str
    credentials: CredentialSources
    keychain_backend: str
    mcp: McpSettings
    jwt: JwtValidationInputs | None
    resource_server: ResourceServerIdentity


def resolve_mcp_runtime() -> McpRuntime:
    """Build the MCP :class:`McpRuntime`, reading env / dotenv / config.toml.

    Raises:
        ValueError / ValidationError: When any loader fails validation (SSRF
            guard, partial service-account pair, bad URL shape).
    """
    deployment = load_deployment()
    endpoints, allow_insecure_urls, reuse_schema, default_webhook_name = load_sdk(
        deployment
    )
    credentials, keychain_backend = load_auth(deployment)
    # The inbound issuer falls back to the issuer this process logs into.
    default_issuer_url = (
        credentials.oidc_client.issuer_url if credentials.oidc_client else None
    )
    jwt = load_jwt_validation(deployment, default_issuer_url=default_issuer_url)

    rs_reader = _ResourceServerReader()
    if rs_reader.resource_server_url is not None:
        security.validate_https_url(
            rs_reader.resource_server_url,
            "resource_server_url",
            allow_insecure=deployment.allow_insecure_urls,
        )
    resource_server = ResourceServerIdentity(
        resource_server_url=rs_reader.resource_server_url,
        required_scopes=rs_reader.required_scopes,
    )

    return McpRuntime(
        endpoints=endpoints,
        allow_insecure_urls=allow_insecure_urls,
        reuse_schema=reuse_schema,
        default_webhook_name=default_webhook_name,
        credentials=credentials,
        keychain_backend=keychain_backend,
        mcp=McpSettings(),
        jwt=jwt,
        resource_server=resource_server,
    )


_runtime: McpRuntime | None = None


def get_runtime() -> McpRuntime:
    """Return the process-wide MCP runtime, resolving + caching on first call."""
    global _runtime
    if _runtime is None:
        _runtime = resolve_mcp_runtime()
    return _runtime


def reset_runtime() -> None:
    """Clear the cached runtime so the next :func:`get_runtime` re-resolves (tests)."""
    global _runtime
    _runtime = None


__all__ = [
    "McpRuntime",
    "McpSettings",
    "ResourceServerIdentity",
    "get_runtime",
    "reset_runtime",
    "resolve_mcp_runtime",
]
