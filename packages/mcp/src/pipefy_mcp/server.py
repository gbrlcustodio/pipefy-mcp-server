from __future__ import annotations

import logging
import textwrap
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.registry import ToolRegistry
from pipefy_mcp.tools.validation_envelope import install_pipefy_validation_envelope

logger = logging.getLogger(__name__)

PIPEFY_INSTRUCTIONS = textwrap.dedent("""
    You are connected to a Pipefy MCP server for managing Kanban-style workflow processes.
    """).strip()


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
            "enabled" if settings.pipefy.mcp_unified_envelope else "disabled",
        )
        logger.info(
            "PIPEFY_MCP_REMOTE_MODE=%s",
            "enabled" if settings.pipefy.mcp_remote_mode else "disabled",
        )
        container = ServicesContainer.get_instance()
        await container.initialize_services(settings)
    except Exception:
        logger.exception("Fatal error during server lifespan initialization")
        raise

    yield container


def _register_pipefy_tools(app: FastMCP, *, remote_mode: bool) -> None:
    """Register every Pipefy tool on ``app`` exactly once, at construction.

    Tools take no client at registration: each resolves the live client per
    request from the lifespan context (see
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
    """Build the FastMCP app with its tools registered once, before serving.

    ``remote_mode`` defaults to the configured ``PIPEFY_MCP_REMOTE_MODE``; pass
    an explicit value to override (used by tests and the HTTP transport).
    """
    resolved = settings.pipefy.mcp_remote_mode if remote_mode is None else remote_mode
    app = FastMCP("pipefy", instructions=PIPEFY_INSTRUCTIONS, lifespan=lifespan)
    _register_pipefy_tools(app, remote_mode=resolved)
    return app


def run_server():
    """Run the MCP server over stdio (the local profile).

    The server is built here, at startup, rather than at import. Building
    registers every tool and reads ``PIPEFY_MCP_REMOTE_MODE``, so building at
    import would make ``--version``/``--help`` pay the full cost and turn any
    registration error into an import failure.
    """
    logger.info("Starting Pipefy MCP server")

    build_pipefy_mcp_server().run()
