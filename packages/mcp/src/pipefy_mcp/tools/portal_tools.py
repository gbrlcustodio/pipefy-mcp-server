"""MCP tools for Pipefy portal operations."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations
from pipefy_sdk import PipefyClient, PipefyId

from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.introspection_tool_helpers import (
    build_error_payload,
    build_success_payload,
)
from pipefy_mcp.tools.portal_tool_helpers import (
    map_portal_error_to_message,
    validate_portal_optional_string,
    validate_portal_page_index,
    validate_sort_page_ids_no_duplicates,
)
from pipefy_mcp.tools.tool_error_envelope import tool_error
from pipefy_mcp.tools.validation_helpers import validate_tool_id

PortalVisibility = Literal["internal", "private", "public"]


class PortalTools:
    """Registers MCP tools for portal read, metadata CRUD, and page operations."""

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
            portal_uuid, err = validate_tool_id(portal_uuid, "portal_uuid")
            if err is not None:
                return err
            await ctx.debug(f"get_portal: portal_uuid={portal_uuid}")
            try:
                portal = await client.get_portal(portal_uuid)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(str(exc))
            return build_success_payload(portal, include_parsed=True)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_portal(
            ctx: Context[ServerSession, None],
            organization_uuid: PipefyId,
        ) -> dict[str, Any]:
            """Create or fetch the organization's main portal (idempotent).

            Uses the same template bootstrap as the Pipefy product
            (``findOrCreateInterfaceByTemplate``). Each organization allows at most
            one main portal; a second call returns the existing portal UUID.

            Args:
                organization_uuid: Organization UUID, or numeric organization id.
            """
            organization_uuid, err = validate_tool_id(
                organization_uuid, "organization_uuid"
            )
            if err is not None:
                return err
            await ctx.debug(f"create_portal: organization_uuid={organization_uuid}")
            try:
                portal = await client.create_portal(organization_uuid)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(map_portal_error_to_message(exc))
            return build_success_payload(portal, include_parsed=True)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_portal(
            ctx: Context[ServerSession, None],
            portal_uuid: str,
            name: str | None = None,
            visibility: PortalVisibility | None = None,
            color: str | None = None,
            icon: str | None = None,
            display_pipefy_header: bool | None = None,
        ) -> dict[str, Any]:
            """Update portal metadata (name, visibility, theme).

            Pass only fields you want to change. ``visibility`` must be one of
            ``internal``, ``private``, or ``public``.

            Args:
                portal_uuid: Portal interface UUID.
                name: Optional display name.
                visibility: ``internal``, ``private``, or ``public``.
                color: Optional theme color.
                icon: Optional icon identifier.
                display_pipefy_header: Whether to show the Pipefy header.
            """
            portal_uuid, err = validate_tool_id(portal_uuid, "portal_uuid")
            if err is not None:
                return err
            await ctx.debug(f"update_portal: portal_uuid={portal_uuid}")
            if all(
                x is None
                for x in (name, visibility, color, icon, display_pipefy_header)
            ):
                return tool_error(
                    "Provide at least one of: name, visibility, color, icon, "
                    "display_pipefy_header.",
                    code="INVALID_ARGUMENTS",
                )
            update_kwargs: dict[str, Any] = {}
            for field_name, raw_value in (
                ("name", name),
                ("color", color),
                ("icon", icon),
            ):
                cleaned, field_err = validate_portal_optional_string(
                    raw_value, field_name
                )
                if field_err is not None:
                    return field_err
                if cleaned is not None:
                    update_kwargs[field_name] = cleaned
            if visibility is not None:
                update_kwargs["visibility"] = visibility
            if display_pipefy_header is not None:
                update_kwargs["display_pipefy_header"] = display_pipefy_header
            try:
                portal = await client.update_portal(portal_uuid, **update_kwargs)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(map_portal_error_to_message(exc))
            return build_success_payload(portal, include_parsed=True)

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_portal(
            ctx: Context[ServerSession, None],
            portal_uuid: str,
            confirm: bool = False,
        ) -> dict[str, Any]:
            """Delete a portal interface (irreversible).

            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval. Elicitation does not authorize
            deletion (only ``confirm=True`` does).

            Args:
                portal_uuid: Portal interface UUID to delete.
                confirm: Set to True to execute the deletion (step 2).
            """
            portal_uuid, err = validate_tool_id(portal_uuid, "portal_uuid")
            if err is not None:
                return err
            await ctx.debug(f"delete_portal: portal_uuid={portal_uuid}")
            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"portal (UUID: {portal_uuid})",
            )
            if guard is not None:
                return guard

            try:
                result = await client.delete_portal(portal_uuid)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(map_portal_error_to_message(exc))

            delete_data = result.get("deleteInterface", {})
            if delete_data.get("success"):
                return build_success_payload(result, include_parsed=True)
            return build_error_payload(
                f"Failed to delete portal '{portal_uuid}'. "
                "Please try again or contact support."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_portal_page(
            ctx: Context[ServerSession, None],
            portal_uuid: str,
            title: str,
            description: str | None = None,
            index: int | None = None,
        ) -> dict[str, Any]:
            """Create a portal page on the Interfaces schema.

            On an empty main portal skeleton, ``createPage`` without an ``elements``
            array often auto-provisions a templated page with multiple elements — the
            supported way to bootstrap a landing page when template create was skipped.

            Args:
                portal_uuid: Parent portal interface UUID.
                title: Page title.
                description: Optional page description.
                index: Optional sort index.
            """
            portal_uuid, err = validate_tool_id(portal_uuid, "portal_uuid")
            if err is not None:
                return err
            if not isinstance(title, str) or not title.strip():
                return tool_error(
                    "Invalid 'title': must be a non-empty string.",
                    code="INVALID_ARGUMENTS",
                )
            title = title.strip()
            description, desc_err = validate_portal_optional_string(
                description, "description"
            )
            if desc_err is not None:
                return desc_err
            index_err = validate_portal_page_index(index)
            if index_err is not None:
                return index_err
            await ctx.debug(
                f"create_portal_page: portal_uuid={portal_uuid}, title={title}"
            )
            try:
                page = await client.create_portal_page(
                    portal_uuid,
                    title,
                    description=description,
                    index=index,
                )
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(map_portal_error_to_message(exc))
            return build_success_payload(page, include_parsed=True)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_portal_page(
            ctx: Context[ServerSession, None],
            portal_uuid: str,
            page_id: str,
            title: str | None = None,
            description: str | None = None,
            index: int | None = None,
        ) -> dict[str, Any]:
            """Update portal page metadata (title, description, sort index).

            Pass only fields you want to change.

            Args:
                portal_uuid: Parent portal interface UUID.
                page_id: Page UUID.
                title: Optional new title.
                description: Optional new description.
                index: Optional sort index.
            """
            portal_uuid, err = validate_tool_id(portal_uuid, "portal_uuid")
            if err is not None:
                return err
            page_id, err = validate_tool_id(page_id, "page_id")
            if err is not None:
                return err
            await ctx.debug(
                f"update_portal_page: portal_uuid={portal_uuid}, page_id={page_id}"
            )
            if all(x is None for x in (title, description, index)):
                return tool_error(
                    "Provide at least one of: title, description, index.",
                    code="INVALID_ARGUMENTS",
                )
            update_kwargs: dict[str, Any] = {}
            cleaned_title, title_err = validate_portal_optional_string(title, "title")
            if title_err is not None:
                return title_err
            if cleaned_title is not None:
                update_kwargs["title"] = cleaned_title
            cleaned_description, desc_err = validate_portal_optional_string(
                description, "description"
            )
            if desc_err is not None:
                return desc_err
            if cleaned_description is not None:
                update_kwargs["description"] = cleaned_description
            index_err = validate_portal_page_index(index)
            if index_err is not None:
                return index_err
            if index is not None:
                update_kwargs["index"] = index
            try:
                page = await client.update_portal_page(
                    portal_uuid,
                    page_id,
                    **update_kwargs,
                )
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(map_portal_error_to_message(exc))
            return build_success_payload(page, include_parsed=True)

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_portal_page(
            ctx: Context[ServerSession, None],
            portal_uuid: str,
            page_id: str,
            confirm: bool = False,
        ) -> dict[str, Any]:
            """Delete a portal page (irreversible).

            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval.

            Args:
                portal_uuid: Parent portal interface UUID.
                page_id: Page UUID to delete.
                confirm: Set to True to execute the deletion (step 2).
            """
            portal_uuid, err = validate_tool_id(portal_uuid, "portal_uuid")
            if err is not None:
                return err
            page_id, err = validate_tool_id(page_id, "page_id")
            if err is not None:
                return err
            await ctx.debug(
                f"delete_portal_page: portal_uuid={portal_uuid}, page_id={page_id}"
            )
            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=(
                    f"portal page (UUID: {page_id}) in portal (UUID: {portal_uuid})"
                ),
            )
            if guard is not None:
                return guard

            try:
                result = await client.delete_portal_page(portal_uuid, page_id)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(map_portal_error_to_message(exc))

            delete_data = result.get("deletePage", {})
            if delete_data.get("success"):
                return build_success_payload(result, include_parsed=True)
            return build_error_payload(
                f"Failed to delete portal page '{page_id}'. "
                "Please try again or contact support."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def sort_portal_pages(
            ctx: Context[ServerSession, None],
            portal_uuid: str,
            page_ids: list[str],
        ) -> dict[str, Any]:
            """Reorder portal pages.

            Args:
                portal_uuid: Parent portal interface UUID.
                page_ids: Ordered list of page UUIDs (new sort order).
            """
            portal_uuid, err = validate_tool_id(portal_uuid, "portal_uuid")
            if err is not None:
                return err
            if not page_ids:
                return tool_error(
                    "Invalid 'page_ids': must be a non-empty list of page UUIDs.",
                    code="INVALID_ARGUMENTS",
                )
            cleaned_page_ids: list[str] = []
            for page_id in page_ids:
                cleaned_id, id_err = validate_tool_id(page_id, "page_ids")
                if id_err is not None:
                    return id_err
                cleaned_page_ids.append(cleaned_id)
            dup_err = validate_sort_page_ids_no_duplicates(cleaned_page_ids)
            if dup_err is not None:
                return dup_err
            await ctx.debug(
                f"sort_portal_pages: portal_uuid={portal_uuid}, "
                f"page_ids_count={len(cleaned_page_ids)}"
            )
            try:
                result = await client.sort_portal_pages(portal_uuid, cleaned_page_ids)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(map_portal_error_to_message(exc))
            if result.get("sortPages", {}).get("success"):
                return build_success_payload(result, include_parsed=True)
            return build_error_payload(
                "Failed to reorder portal pages. Please try again or contact support."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_portal_page_layout(
            ctx: Context[ServerSession, None],
            page_id: str,
            layout: dict[str, Any],
        ) -> dict[str, Any]:
            """Update a portal page grid layout.

            Uses ``updatePageLayout`` on the Interfaces schema. Does not require the
            parent portal UUID — only ``page_id`` and ``layout``.

            Args:
                page_id: Page UUID.
                layout: Layout JSON (full layout object for the page).
            """
            page_id, err = validate_tool_id(page_id, "page_id")
            if err is not None:
                return err
            await ctx.debug(f"update_portal_page_layout: page_id={page_id}")
            try:
                result = await client.update_portal_page_layout(page_id, layout)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(map_portal_error_to_message(exc))
            if result.get("updatePageLayout", {}).get("success"):
                return build_success_payload(result, include_parsed=True)
            return build_error_payload(
                f"Failed to update layout for portal page '{page_id}'. "
                "Please try again or contact support."
            )
