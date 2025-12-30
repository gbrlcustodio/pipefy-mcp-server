from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.tools.pipe_tools import PipeTools


class ToolRegistry:
    """Responsible for registering tools with the MCP server"""

    def __init__(self, mcp: FastMCP, services_container: ServicesContainer):
        self.mcp = mcp
        self.services_container = services_container

    def register_tools(self) -> FastMCP:
        """Register tools with the MCP server"""
        PipeTools.register(self.mcp)

        mcp = self.mcp

        return mcp
