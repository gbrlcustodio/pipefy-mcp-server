from __future__ import annotations

import logging
import textwrap
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.core.fastmcp_tool_lifecycle import remove_fastmcp_tools_by_name
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_PIPEFY_APP_TOOLS_ATTR = "_pipefy_cleared_tools_once"
_PIPEFY_OWNED_TOOL_NAMES_ATTR = "_pipefy_tool_names"


def _prepare_app_for_repeat_pipefy_tool_registration(app: FastMCP) -> None:
    """Remove only Pipefy-owned tools before re-registering on a repeat lifespan visit.

    FastMCP's ToolManager keeps the first registered callable when names collide.
    In-process MCP sessions (tests, Cursor) can enter lifespan multiple times;
    ``initialize_services`` then updates the container but tools would still call
    the old client unless we remove stale Pipefy tools before ``register_tools``.

    Tools registered outside :class:`ToolRegistry` are left intact.
    """
    if getattr(app, _PIPEFY_APP_TOOLS_ATTR, False):
        owned = getattr(app, _PIPEFY_OWNED_TOOL_NAMES_ATTR, None)
        if not owned:
            logger.warning(
                "Repeat MCP lifespan visit but %s is missing or empty; "
                "skipping selective Pipefy tool cleanup.",
                _PIPEFY_OWNED_TOOL_NAMES_ATTR,
            )
        else:
            remove_fastmcp_tools_by_name(app, set(owned))
    setattr(app, _PIPEFY_APP_TOOLS_ATTR, True)


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[FastMCP]:
    """Lifespan function to manage the lifecycle of the server."""
    try:
        logger.info("Initializing services")
        services_container = ServicesContainer.get_instance()
        services_container.initialize_services(settings)
        _prepare_app_for_repeat_pipefy_tool_registration(app)
        registry = ToolRegistry(
            mcp=app,
            services_container=services_container,
        )
        mcp = registry.register_tools()
        setattr(app, _PIPEFY_OWNED_TOOL_NAMES_ATTR, set(registry.pipefy_tool_names))
    except Exception:
        logger.exception("Fatal error during server lifespan initialization")
        raise

    yield mcp


PIPEFY_INSTRUCTIONS = textwrap.dedent("""
    You are connected to a Pipefy MCP server for managing Kanban-style workflow processes.
    """).strip()

mcp = FastMCP("pipefy", instructions=PIPEFY_INSTRUCTIONS, lifespan=lifespan)


def run_server():
    """Run the MCP server."""
    logger.info("Starting Pipefy MCP server")

    mcp.run()
