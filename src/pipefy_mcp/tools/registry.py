from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.tools.ai_agent_tools import AiAgentTools
from pipefy_mcp.tools.ai_automation_tools import AiAutomationTools
from pipefy_mcp.tools.automation_tools import AutomationTools
from pipefy_mcp.tools.field_condition_tools import FieldConditionTools
from pipefy_mcp.tools.introspection_tools import IntrospectionTools
from pipefy_mcp.tools.pipe_config_tools import PipeConfigTools
from pipefy_mcp.tools.pipe_tools import PipeTools
from pipefy_mcp.tools.relation_tools import RelationTools
from pipefy_mcp.tools.table_tools import TableTools


class ToolRegistry:
    """Responsible for registering tools with the MCP server."""

    def __init__(self, mcp: FastMCP, services_container: ServicesContainer):
        self.mcp = mcp
        self.services_container = services_container

    def register_tools(self) -> FastMCP:
        """Register tools with the MCP server."""
        if self.services_container.pipefy_client is None:
            raise ValueError("Pipefy client is not initialized in services container")

        PipeTools.register(self.mcp, self.services_container.pipefy_client)
        PipeConfigTools.register(self.mcp, self.services_container.pipefy_client)
        FieldConditionTools.register(self.mcp, self.services_container.pipefy_client)
        TableTools.register(self.mcp, self.services_container.pipefy_client)
        RelationTools.register(self.mcp, self.services_container.pipefy_client)
        AutomationTools.register(self.mcp, self.services_container.pipefy_client)
        IntrospectionTools.register(self.mcp, self.services_container.pipefy_client)

        if self.services_container.ai_automation_service is not None:
            AiAutomationTools.register(
                self.mcp, self.services_container.ai_automation_service
            )

        if self.services_container.ai_agent_service is not None:
            AiAgentTools.register(self.mcp, self.services_container.ai_agent_service)

        return self.mcp
