from __future__ import annotations

import logging
import textwrap
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.auth.settings import AuthSettings as FastMcpAuthSettings
from mcp.server.fastmcp import FastMCP
from pipefy_auth import JwtValidationSettings, JwtValidator

from pipefy_mcp.auth import JwtTokenVerifier
from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.settings import ResourceServerSettings, settings
from pipefy_mcp.tools.registry import ToolRegistry
from pipefy_mcp.tools.validation_envelope import install_pipefy_validation_envelope

logger = logging.getLogger(__name__)

PIPEFY_INSTRUCTIONS = textwrap.dedent("""
    You are connected to a Pipefy MCP server for managing Kanban-style workflow processes.
    """).strip()

# Hosts that keep the server reachable only from the local machine. The HTTP
# transport refuses to bind anywhere else (a routable interface or 0.0.0.0)
# while it is unauthenticated.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[ServicesContainer]:
    """Manage the server's resource lifecycle (not tool registration).

    Following the FastMCP lifespan contract, this owns resources only: it builds a
    container, initializes its services, and yields it as the request
    ``lifespan_context``. Tools resolve the live client per request from this
    ``lifespan_context`` (see
    :func:`pipefy_mcp.tools.tool_context.get_pipefy_client`), so both transports
    must run a lifespan for tools to find a client.

    The container is built per entry. Streamable HTTP re-enters this context
    manager per session, so each session gets its own initialized container. That
    re-resolution is cheap (the stored-session warm-up only hits the network when
    the token is stale, serialized by the auth layer) and the HTTP profile is
    loopback validation-only; #302's per-request identity will build the client
    from the request here instead. See AGENTS.md for the fuller rationale.

    Tools are registered once, up front, by :func:`_register_pipefy_tools`, never
    here, so re-entry cannot race the tool table.
    """
    try:
        logger.info("Initializing services")
        logger.info(
            "PIPEFY_MCP_UNIFIED_ENVELOPE=%s",
            "enabled" if settings.mcp.unified_envelope else "disabled",
        )
        logger.info(
            "PIPEFY_MCP_REMOTE_MODE=%s",
            "enabled" if settings.mcp.remote_mode else "disabled",
        )
        container = ServicesContainer()
        await container.initialize_services(settings)
    except Exception:
        logger.exception("Fatal error during server lifespan initialization")
        raise

    yield container


def _register_pipefy_tools(app: FastMCP, *, remote_mode: bool) -> None:
    """Register every Pipefy tool on ``app`` exactly once, at construction.

    Shared by both transports. Tools take no client at registration: each
    resolves the live client per request from the lifespan context (see
    :func:`pipefy_mcp.tools.tool_context.get_pipefy_client`), so they can be
    registered before services are initialized and keep working across a service
    re-initialization. Registration never repeats, so there is no repeat-visit
    bookkeeping to maintain.
    """
    install_pipefy_validation_envelope()
    registry = ToolRegistry(mcp=app)
    registry.check_for_name_collisions()
    registry.register_tools()
    registry.apply_remote_profile(remote_mode=remote_mode)


def _resolve_bind(host: str | None, port: int | None) -> tuple[str, int]:
    """Fill an unset HTTP bind host/port from ``PIPEFY_MCP_HOST`` / ``PIPEFY_MCP_PORT``.

    The single owner of the default-source rule, shared by :func:`run_server` (which
    needs the resolved values for its log line and the loopback guard) and
    :func:`build_pipefy_mcp_server` (which passes them to ``FastMCP``).
    """
    return (
        host if host is not None else settings.mcp.host,
        port if port is not None else settings.mcp.port,
    )


def _build_resource_server_auth(
    rs: ResourceServerSettings,
    jwt_validation: JwtValidationSettings,
    *,
    default_issuer_url: str | None,
) -> tuple[JwtTokenVerifier, FastMcpAuthSettings] | None:
    """Build the inbound bearer verifier and FastMCP auth config, or ``None``.

    The resource-server profile has no enable flag: it is active when this
    server's ``resource_server_url`` is configured. Absent it, this returns
    ``None`` and the unauthenticated foundation profile constructs ``FastMCP``
    exactly as before.

    The inbound issuer is ``jwt_validation.issuer_url`` if set, else
    ``default_issuer_url`` (see :class:`JwtValidationSettings` for why the login
    issuer is the fallback). With ``resource_server_url`` set but no issuer
    resolvable (the stored-session login is disabled and no override is given),
    validation is impossible, so this raises rather than serve an open endpoint.

    The verifier consumes the inbound validation knobs (audience, verify_audience,
    jwks_uri); FastMCP's ``AuthSettings`` consumes the issuer, resource, and
    required scopes to serve RFC 9728 metadata and the ``401`` challenge.
    """
    if rs.resource_server_url is None:
        return None
    issuer_url = jwt_validation.resolve_issuer_url(default_issuer_url)
    if issuer_url is None:
        raise RuntimeError(
            "The resource-server profile is active "
            "(PIPEFY_MCP_RS_RESOURCE_SERVER_URL is set) but no inbound issuer is "
            "resolvable: set PIPEFY_JWT_ISSUER_URL, or leave the stored-session "
            "login enabled so its issuer can be reused."
        )
    verifier = JwtTokenVerifier(
        JwtValidator(
            issuer_url=issuer_url,
            audience=jwt_validation.audience,
            verify_audience=jwt_validation.verify_audience,
            allow_insecure_urls=jwt_validation.allow_insecure_urls,
            jwks_uri=jwt_validation.jwks_uri,
        )
    )
    auth = FastMcpAuthSettings(
        issuer_url=issuer_url,
        resource_server_url=rs.resource_server_url,
        required_scopes=rs.required_scopes,
    )
    return verifier, auth


def build_pipefy_mcp_server(
    *,
    remote_mode: bool | None = None,
    host: str | None = None,
    port: int | None = None,
    resource_server: tuple[JwtTokenVerifier, FastMcpAuthSettings] | None = None,
) -> FastMCP:
    """Build the FastMCP app with its tools registered once, before serving.

    Used by both transports: the resource-only :func:`lifespan` is the same, only
    the transport ``run`` differs. ``remote_mode`` defaults to the configured
    ``PIPEFY_MCP_REMOTE_MODE``; pass an explicit value to override (used by
    tests). ``host``/``port`` default to ``PIPEFY_MCP_HOST`` / ``PIPEFY_MCP_PORT``
    and matter only for the HTTP transport; stdio ignores them.

    ``resource_server`` is the ``(verifier, auth)`` pair from
    :func:`_build_resource_server_auth`. When present, FastMCP validates the
    inbound bearer per request and serves the resource-server metadata; when
    ``None`` (stdio, or the disabled HTTP profile) the app has no inbound auth.
    """
    resolved = settings.mcp.remote_mode if remote_mode is None else remote_mode
    resolved_host, resolved_port = _resolve_bind(host, port)
    verifier, auth = resource_server or (None, None)
    app = FastMCP(
        "pipefy",
        instructions=PIPEFY_INSTRUCTIONS,
        lifespan=lifespan,
        host=resolved_host,
        port=resolved_port,
        token_verifier=verifier,
        auth=auth,
    )
    _register_pipefy_tools(app, remote_mode=resolved)
    return app


def _assert_loopback_http_bind(*, host: str, resource_server_configured: bool) -> None:
    """Refuse to bind the HTTP transport to a non-loopback host while unauthenticated.

    Without the resource-server profile the HTTP transport validates no inbound
    bearer and carries no per-request identity, so every call runs as the single
    identity resolved at startup. A network-reachable bind would hand that
    identity to anyone who can reach the port, so it is restricted to loopback.
    (The filesystem tools, e.g. the attachment uploads, also only make sense on
    loopback, where the server shares the client's disk.)

    Once the resource-server profile is configured, every request carries a
    validated bearer, so a non-loopback bind is allowed. The configurable host /
    Origin allowlist for a proxied deployment is #303.
    """
    if host in _LOOPBACK_HOSTS or resource_server_configured:
        return
    raise RuntimeError(
        f"Refusing to serve over HTTP on a non-loopback host ({host}). The HTTP "
        f"transport is unauthenticated and is restricted to loopback "
        f"(127.0.0.1/localhost/::1). Set PIPEFY_MCP_RS_RESOURCE_SERVER_URL to "
        f"activate the resource-server profile, which validates inbound bearers "
        f"and may bind off-loopback."
    )


def run_server(
    *,
    http: bool = False,
    host: str | None = None,
    port: int | None = None,
    remote_mode: bool | None = None,
) -> None:
    """Run the Pipefy MCP server. The single serve entry point for both transports.

    With ``http=False`` (the default, local profile) the process speaks MCP over
    stdio. With ``http=True`` it serves over Streamable HTTP on ``host``/``port``,
    defaulting to the configured ``PIPEFY_MCP_HOST`` / ``PIPEFY_MCP_PORT``. HTTP
    is restricted to a loopback bind while it is unauthenticated foundation work
    (see :func:`_assert_loopback_http_bind`).

    ``remote_mode`` selects the default-deny remote tool surface and defaults to
    the configured ``PIPEFY_MCP_REMOTE_MODE``. It is orthogonal to the transport:
    stdio can run the remote profile too.

    The server is built here, at startup rather than at import. Building registers
    every tool and reads ``PIPEFY_MCP_REMOTE_MODE``, so building at import would
    make ``--version``/``--help`` pay the full cost and turn any registration
    error into an import failure.

    Both transports build the same app through :func:`build_pipefy_mcp_server`
    (same :func:`lifespan`, same :func:`_register_pipefy_tools`) and differ only
    in the transport ``run`` and HTTP's bind concerns.
    """
    if not http:
        logger.info("Starting Pipefy MCP server")
        build_pipefy_mcp_server(remote_mode=remote_mode).run()
        return

    resolved_remote = settings.mcp.remote_mode if remote_mode is None else remote_mode
    resolved_host, resolved_port = _resolve_bind(host, port)
    oidc_client = settings.auth.to_oidc_client()
    resource_server = _build_resource_server_auth(
        settings.rs,
        settings.jwt,
        default_issuer_url=oidc_client.issuer_url if oidc_client else None,
    )
    logger.info(
        "Starting Pipefy MCP server over HTTP on %s:%d (remote_mode=%s, resource_server=%s)",
        resolved_host,
        resolved_port,
        "enabled" if resolved_remote else "disabled",
        "active" if resource_server is not None else "inactive",
    )
    _assert_loopback_http_bind(
        host=resolved_host, resource_server_configured=resource_server is not None
    )

    app = build_pipefy_mcp_server(
        remote_mode=resolved_remote,
        host=resolved_host,
        port=resolved_port,
        resource_server=resource_server,
    )
    app.run("streamable-http")
