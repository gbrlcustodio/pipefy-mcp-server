import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[FastMCP, None]:
    """Lifespan function to manage the lifecycle of the server."""
    try:
        logger.info("Initializing services")

        # Initialize services
        services_container = ServicesContainer.get_instance()
        services_container.initialize_services(settings)

        # Register tools
        mcp = ToolRegistry(
            mcp=app,
            services_container=services_container,
        ).register_tools()

        yield mcp
    except Exception as e:
        logger.error(f"Error during server lifespan: {e}")
    finally:
        logger.info("Shutting down services")

        # Force kill the entire process - doesn't care about async contexts
        import os

        os._exit(0)  # Use 0 for sucessful termination


# Create an MCP server
mcp = FastMCP("pipefy", lifespan=lifespan)


def run_server():
    """Run the MCP server."""
    logger.info("Starting Pipefy MCP server")

    mcp.run()
