from __future__ import annotations

import logging
import textwrap
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.registry import ToolRegistry
from pipefy_mcp.tools.validation_envelope import install_pipefy_validation_envelope

logger = logging.getLogger(__name__)

PIPEFY_INSTRUCTIONS = textwrap.dedent("""
    You are connected to a Pipefy MCP server for managing Kanban-style workflow processes.
    """).strip()

# Hosts that keep the server reachable only from the local machine. Binding
# anywhere else (a routable interface or 0.0.0.0) is treated as public and
# gates the full tool surface behind the remote profile or an escape hatch.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[ServicesContainer]:
    """Manage the server's resource lifecycle (not tool registration).

    Following the FastMCP lifespan contract, this owns resources only: it
    initializes services and yields the container as the request
    ``lifespan_context``. Tools are registered once, up front, by
    :func:`_register_pipefy_tools`, so re-entering this context manager (which
    Streamable HTTP does per session) never re-registers and cannot race on the
    tool table. Tools resolve the live client per request from this
    ``lifespan_context`` (see :func:`pipefy_mcp.tools.tool_context.get_pipefy_client`),
    so a re-entry that rebuilds the client is picked up without re-registration.
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
        container = ServicesContainer.get_instance()
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


def build_pipefy_mcp_server(*, remote_mode: bool | None = None) -> FastMCP:
    """Build the stdio FastMCP app with its tools registered once, before serving.

    ``remote_mode`` defaults to the configured ``PIPEFY_MCP_REMOTE_MODE``; pass
    an explicit value to override (used by tests).
    """
    resolved = settings.mcp.remote_mode if remote_mode is None else remote_mode
    app = FastMCP("pipefy", instructions=PIPEFY_INSTRUCTIONS, lifespan=lifespan)
    _register_pipefy_tools(app, remote_mode=resolved)
    return app


def _assert_http_surface_is_safe(*, host: str, remote_mode: bool) -> None:
    """Refuse to serve the full tool surface on a public HTTP host.

    The default-deny remote profile (``remote_mode``) is the safe surface; the
    escape hatch is an explicit operator opt-in. Loopback binds are always
    allowed so local development is unaffected.
    """
    if remote_mode or host in _LOOPBACK_HOSTS:
        return
    if settings.mcp.allow_full_surface_over_http:
        logger.warning(
            "Serving the full tool surface over HTTP on %s because "
            "PIPEFY_MCP_ALLOW_FULL_SURFACE_OVER_HTTP is set.",
            host,
        )
        return
    raise RuntimeError(
        f"Refusing to serve the full tool surface over HTTP on a public host "
        f"({host}). Launch with --remote to expose only the default-deny "
        f"remote-safe tools, or set PIPEFY_MCP_ALLOW_FULL_SURFACE_OVER_HTTP=true "
        f"to override."
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
    stdio. With ``http=True`` (the hosted profile) it serves over Streamable HTTP
    on ``host``/``port``, defaulting to the configured ``PIPEFY_MCP_HOST`` /
    ``PIPEFY_MCP_PORT``.

    ``remote_mode`` selects the default-deny remote tool surface and defaults to
    the configured ``PIPEFY_MCP_REMOTE_MODE``. It is orthogonal to the transport:
    stdio can run the remote profile, and HTTP can serve the full surface on a
    loopback host (or behind the escape hatch).

    The server is built here, at startup rather than at import. Building registers
    every tool and reads ``PIPEFY_MCP_REMOTE_MODE``, so building at import would
    make ``--version``/``--help`` pay the full cost and turn any registration
    error into an import failure.

    The two transports diverge only in how the app is wired: stdio reuses
    :func:`build_pipefy_mcp_server` (which keeps the resource-only ``lifespan``);
    HTTP builds a dedicated app with no constructor ``lifespan`` (which Streamable
    HTTP would run per session) and initializes services once before serving.
    Both register tools through the shared :func:`_register_pipefy_tools`.
    """
    if not http:
        logger.info("Starting Pipefy MCP server")
        build_pipefy_mcp_server(remote_mode=remote_mode).run()
        return

    resolved_remote = settings.mcp.remote_mode if remote_mode is None else remote_mode
    resolved_host = host or settings.mcp.host
    resolved_port = port or settings.mcp.port
    logger.info(
        "Starting Pipefy MCP server over HTTP on %s:%d (remote_mode=%s)",
        resolved_host,
        resolved_port,
        "enabled" if resolved_remote else "disabled",
    )
    _assert_http_surface_is_safe(host=resolved_host, remote_mode=resolved_remote)

    container = ServicesContainer.get_instance()
    anyio.run(container.initialize_services, settings)

    http_app = FastMCP(
        "pipefy",
        instructions=PIPEFY_INSTRUCTIONS,
        host=resolved_host,
        port=resolved_port,
    )
    _register_pipefy_tools(http_app, remote_mode=resolved_remote)
    http_app.run("streamable-http")
