"""MCP tools for Pipefy organization operations."""

from __future__ import annotations

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pipefy_sdk import PipefyId

from pipefy_mcp.tools.graphql_error_helpers import ensure_non_empty_error_message
from pipefy_mcp.tools.introspection_tool_helpers import (
    build_error_payload,
    build_success_payload,
)
from pipefy_mcp.tools.remote_profile import REMOTE
from pipefy_mcp.tools.tool_context import get_pipefy_client

_ORGANIZATION_REQUEST_FAILED = (
    "Organization request failed. Re-read organization state "
    "before retrying; do not blind-retry."
)


class OrganizationTools:
    """Registers MCP tools for organization operations."""

    @staticmethod
    def register(mcp: MCPServer) -> None:
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
                return build_error_payload(
                    ensure_non_empty_error_message(
                        str(exc), _ORGANIZATION_REQUEST_FAILED
                    )
                )
            return build_success_payload(result, include_parsed=True)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
            meta=REMOTE,
        )
        async def list_organizations(ctx: Context) -> dict:
            """List the Pipefy organizations you can access.

            The zero-knowledge entry point for discovery: answers "which
            organizations do I have access to?" with no id required. Use it to
            obtain the ``id`` / ``uuid`` other tools need (reports, automations,
            observability, portals). Each entry has id, uuid, name, plan, your
            role in it, members count, pipes count, and creation date. An empty
            list means you belong to no organization.

            The response includes both ``result`` (pretty-printed JSON string)
            and ``data`` (parsed dict) for convenience.
            """
            client = get_pipefy_client(ctx)
            try:
                result = await client.list_organizations()
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(
                    ensure_non_empty_error_message(
                        str(exc), _ORGANIZATION_REQUEST_FAILED
                    )
                )
            return build_success_payload({"organizations": result}, include_parsed=True)
