"""MCP tools for Pipefy organization operations."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from pipefy_mcp.models.validators import PipefyId
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.introspection_tool_helpers import (
    build_error_payload,
    build_success_payload,
)


class OrganizationTools:
    """Registers MCP tools for organization operations."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        """Register organization-related tools on the MCP server."""

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_organization(organization_id: PipefyId) -> dict:
            """Fetch Pipefy organization details by ID.

            Returns id, uuid, name, plan, role, members count, pipes count,
            and creation date.

            Args:
                organization_id: Numeric organization ID.
            """
            try:
                result = await client.get_organization(organization_id)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(str(exc))
            err = result.get("error")
            if isinstance(err, str) and err:
                return build_error_payload(err)
            return build_success_payload(result)
