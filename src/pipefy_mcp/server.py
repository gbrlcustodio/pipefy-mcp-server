import logging
import textwrap
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_PIPEFY_APP_TOOLS_ATTR = "_pipefy_cleared_tools_once"


def _clear_fastmcp_tools_if_repeat_visit(app: FastMCP) -> None:
    """Ensure tool handlers are re-bound when lifespan runs again on the same app.

    FastMCP's ToolManager keeps the first registered callable when names collide.
    In-process MCP sessions (tests, Cursor) can enter lifespan multiple times;
    ``initialize_services`` then updates the container but tools would still call
    the old client unless we remove stale tools before ``register_tools``.
    """
    if getattr(app, _PIPEFY_APP_TOOLS_ATTR, False):
        for tool in list(app._tool_manager.list_tools()):
            app._tool_manager.remove_tool(tool.name)
    setattr(app, _PIPEFY_APP_TOOLS_ATTR, True)


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[FastMCP]:
    """Lifespan function to manage the lifecycle of the server."""
    try:
        logger.info("Initializing services")
        services_container = ServicesContainer.get_instance()
        services_container.initialize_services(settings)
        _clear_fastmcp_tools_if_repeat_visit(app)
        mcp = ToolRegistry(
            mcp=app,
            services_container=services_container,
        ).register_tools()

        yield mcp
    except Exception as e:
        logger.error(f"Error during server lifespan: {e}")


PIPEFY_INSTRUCTIONS = textwrap.dedent("""
    You are connected to a Pipefy MCP server for managing Kanban-style workflow processes.
    """).strip()

mcp = FastMCP("pipefy", instructions=PIPEFY_INSTRUCTIONS, lifespan=lifespan)


def run_server():
    """Run the MCP server."""
    logger.info("Starting Pipefy MCP server")

    mcp.run()
