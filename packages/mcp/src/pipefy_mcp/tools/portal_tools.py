"""MCP tools for Pipefy portal read operations."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations
from pipefy_sdk import PipefyClient

from pipefy_mcp.tools.portal_tool_helpers import (
    build_get_portal_success_payload,
    build_list_portals_success_payload,
    build_portal_error_payload,
    map_portal_error_to_message,
)


class PortalTools:
    """Registers MCP tools for portal read operations."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        """Register portal-related tools on the MCP server."""

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def list_portals(
            ctx: Context[ServerSession, None],
            org_uuid: str,
            search_term: str | None = None,
        ) -> dict[str, Any]:
            """List portals for an organization.

            Each organization has at most one main portal; additional entries may be
            sub-portals. Returns uuid, name, visibility, and published status for each
            portal. The response includes both ``result`` (pretty-printed JSON string)
            and ``data`` (parsed dict) for convenience.

            Args:
                org_uuid: Organization UUID.
                search_term: Optional name filter.
            """
            await ctx.debug(
                f"list_portals: org_uuid={org_uuid}, search_term={search_term}"
            )
            try:
                portals = await client.list_portals(org_uuid, search_term=search_term)
            except ValueError as exc:
                return build_portal_error_payload(map_portal_error_to_message(exc))
            return build_list_portals_success_payload(portals)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_portal(
            ctx: Context[ServerSession, None],
            uuid: str,
        ) -> dict[str, Any]:
            """Fetch a portal by UUID with pages, elements, and sub-portals.

            Returns uuid, name, visibility, published, pages (with elements), and
            subPortals. The response includes both ``result`` (pretty-printed JSON
            string) and ``data`` (parsed dict) for convenience.

            Args:
                uuid: Portal interface UUID.
            """
            await ctx.debug(f"get_portal: uuid={uuid}")
            try:
                portal = await client.get_portal(uuid)
            except ValueError as exc:
                return build_portal_error_payload(map_portal_error_to_message(exc))
            return build_get_portal_success_payload(portal)
