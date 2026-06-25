from __future__ import annotations

import logging
import textwrap
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.auth import ResourceServerAuth, build_resource_server_auth
from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.settings import settings
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


def build_pipefy_mcp_server(
    *,
    remote_mode: bool | None = None,
    host: str | None = None,
    port: int | None = None,
    resource_server: ResourceServerAuth | None = None,
) -> FastMCP:
    """Build the FastMCP app with its tools registered once, before serving.

    Used by both transports: the resource-only :func:`lifespan` is the same, only
    the transport ``run`` differs. ``remote_mode`` defaults to the configured
    ``PIPEFY_MCP_REMOTE_MODE``; pass an explicit value to override (used by
    tests). ``host``/``port`` default to ``PIPEFY_MCP_HOST`` / ``PIPEFY_MCP_PORT``
    and matter only for the HTTP transport; stdio ignores them.

    ``resource_server`` is the ``(verifier, auth)`` pair from
    :func:`pipefy_mcp.auth.build_resource_server_auth`. When present, FastMCP
    validates the inbound bearer per request and serves the resource-server
    metadata; when ``None`` (stdio, or the disabled HTTP profile) the app has no
    inbound auth.
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


def _assert_safe_http_bind(*, host: str) -> None:
    """Refuse to bind the HTTP transport to a non-loopback host.

    The HTTP transport is restricted to loopback for now. Even with the
    resource-server profile validating an inbound bearer, there is no
    per-request on-behalf-of identity yet, so every call still runs as the
    single identity resolved at startup. A network-reachable bind would hand
    that identity to anyone who can reach the port. (The filesystem tools, e.g.
    the attachment uploads, also only make sense on loopback, where the server
    shares the client's disk.)

    Off-loopback binding stays off until the hosted on-behalf-of profile lands
    (per-request identity and the DNS-rebinding host/Origin allowlist); see
    experiments/hosted-obo/RFC-OUTLINE.md.
    """
    if host in _LOOPBACK_HOSTS:
        return
    raise RuntimeError(
        f"Refusing to serve over HTTP on a non-loopback host ({host}). The HTTP "
        f"transport is restricted to loopback (127.0.0.1/localhost/::1) until "
        f"the hosted on-behalf-of profile lands."
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
    is restricted to a loopback bind until the hosted on-behalf-of profile lands
    (see :func:`_assert_safe_http_bind`).

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
    resource_server = build_resource_server_auth(
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
    _assert_safe_http_bind(host=resolved_host)

    app = build_pipefy_mcp_server(
        remote_mode=resolved_remote,
        host=resolved_host,
        port=resolved_port,
        resource_server=resource_server,
    )
    app.run("streamable-http")
