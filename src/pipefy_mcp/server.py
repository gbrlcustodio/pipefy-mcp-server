from __future__ import annotations

import logging
import textwrap
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.core.pipefy_tool_lifecycle import (
    cleanup_failed_pipefy_tool_registration,
    mark_pipefy_tool_registration_complete,
    mark_pipefy_tool_registration_started,
    prepare_app_for_repeat_pipefy_tool_registration,
)
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[FastMCP]:
    """Lifespan function to manage the lifecycle of the server."""
    try:
        logger.info("Initializing services")
        services_container = ServicesContainer.get_instance()
        services_container.initialize_services(settings)
        prepare_app_for_repeat_pipefy_tool_registration(app)
        registry = ToolRegistry(
            mcp=app,
            services_container=services_container,
        )
        registry.check_for_name_collisions()
        mark_pipefy_tool_registration_started(app, set(registry.pipefy_tool_names))
        mcp = registry.register_tools()
        mark_pipefy_tool_registration_complete(app, set(registry.pipefy_tool_names))
    except Exception:
        cleanup_failed_pipefy_tool_registration(app)
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
