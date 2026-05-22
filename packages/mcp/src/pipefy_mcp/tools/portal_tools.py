"""MCP tools for Pipefy portal read operations."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations
from pipefy_sdk import PipefyClient, PipefyId

from pipefy_mcp.tools.introspection_tool_helpers import (
    build_error_payload,
    build_success_payload,
)
from pipefy_mcp.tools.validation_helpers import validate_tool_id


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
            organization_uuid: PipefyId,
            search_term: str | None = None,
        ) -> dict[str, Any]:
            """List portals for an organization.

            Each organization has at most one main portal; additional entries may be
            sub-portals. Returns uuid, name, visibility, and subType for each
            portal (use ``get_portal`` for ``published`` and page detail). The
            response includes both ``result`` (pretty-printed JSON string)
            and ``data`` (parsed dict) for convenience.

            Args:
                organization_uuid: Organization UUID, or numeric organization id
                    (string or unquoted integer via MCP clients).
                search_term: Optional name filter.
            """
            organization_uuid, err = validate_tool_id(
                organization_uuid, "organization_uuid"
            )
            if err is not None:
                return err
            await ctx.debug(
                f"list_portals: organization_uuid={organization_uuid}, "
                f"search_term={search_term}"
            )
            try:
                portals = await client.list_portals(
                    organization_uuid, search_term=search_term
                )
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(str(exc))
            return build_success_payload({"portals": portals}, include_parsed=True)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_portal(
            ctx: Context[ServerSession, None],
            portal_uuid: str,
        ) -> dict[str, Any]:
            """Fetch a portal by UUID with pages, elements, and sub-portals.

            Returns uuid, name, visibility, published, pages (with elements), and
            subPortals. The response includes both ``result`` (pretty-printed JSON
            string) and ``data`` (parsed dict) for convenience.

            Page elements include a ``metadata`` JSON object whose shape depends on
            ``type`` (non-exhaustive):

            - ``forms`` -> ``{ formId: str }``
            - ``pipe`` -> ``{ pipeId: str }``
            - ``link`` -> ``{ url: str, label?: str }``

            Additional element types may appear; treat unknown keys as opaque.

            Args:
                portal_uuid: Portal interface UUID.
            """
            await ctx.debug(f"get_portal: portal_uuid={portal_uuid}")
            try:
                portal = await client.get_portal(portal_uuid)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(str(exc))
            return build_success_payload(portal, include_parsed=True)
