"""MCP tools for Pipefy organization operations."""

from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pipefy_sdk import PipefyId

from pipefy_mcp.tools.introspection_tool_helpers import (
    build_error_payload,
    build_success_payload,
)
from pipefy_mcp.tools.remote_profile import REMOTE
from pipefy_mcp.tools.tool_context import get_pipefy_client


class OrganizationTools:
    """Registers MCP tools for organization operations."""

    @staticmethod
    def register(mcp: FastMCP) -> None:
        """Register organization-related tools on the MCP server."""

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
            meta=REMOTE,
        )
        async def get_organization(organization_id: PipefyId, ctx: Context) -> dict:
            """Fetch Pipefy organization details by ID.

            Returns id, uuid, name, plan, role, members count, pipes count,
            and creation date. The response includes both ``result`` (pretty-printed
            JSON string) and ``data`` (parsed dict) for convenience.

            Args:
                organization_id: Numeric organization ID.
            """
            client = get_pipefy_client(ctx)
            try:
                result = await client.get_organization(organization_id)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(str(exc))
            return build_success_payload(result, include_parsed=True)
