"""MCP tools for Pipefy pipe and organization reports."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.report_tool_helpers import (
    build_report_mutation_success_payload,
    build_report_read_success_payload,
    handle_report_tool_graphql_error,
)


class ReportTools:
    """MCP tools for reading, managing, and exporting pipe and organization reports."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_pipe_reports(
            pipe_uuid: str,
            first: int = 30,
            after: str | None = None,
            search: str | None = None,
            report_id: str | None = None,
            order: dict | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """List pipe reports with pagination (query omits `cardCount`). Use `get_pipe_report_columns` and `get_pipe_report_filterable_fields` before creating reports.

            Args:
                pipe_uuid: Pipe UUID (not numeric ID).
                first: Page size (default 30).
                after: Cursor for next page.
                search: Free-text search on report name.
                report_id: Filter to a specific report ID.
                order: Sort order, e.g. {"field": "name", "direction": "asc"}.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.get_pipe_reports(
                    pipe_uuid,
                    first=first,
                    after=after,
                    search=search,
                    report_id=report_id,
                    order=order,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Get pipe reports failed.", debug=debug
                )
            return build_report_read_success_payload(
                raw,
                message="Pipe reports retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_pipe_report_columns(
            pipe_uuid: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Get available columns for a pipe report. Each item includes `name` (internal field id for `fields`) and `label`.

            Args:
                pipe_uuid: Pipe UUID.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.get_pipe_report_columns(pipe_uuid)
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Get pipe report columns failed.", debug=debug
                )
            return build_report_read_success_payload(
                raw,
                message="Pipe report columns retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_pipe_report_filterable_fields(
            pipe_uuid: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Get filterable fields for a pipe report (nested groups; use `name` for filter fields).

            Args:
                pipe_uuid: Pipe UUID.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.get_pipe_report_filterable_fields(pipe_uuid)
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Get pipe report filterable fields failed.", debug=debug
                )
            return build_report_read_success_payload(
                raw,
                message="Pipe report filterable fields retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_organization_report(
            report_id: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Get a single organization report by ID.

            Args:
                report_id: Organization report ID.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.get_organization_report(report_id)
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Get organization report failed.", debug=debug
                )
            return build_report_read_success_payload(
                raw,
                message="Organization report retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_organization_reports(
            organization_id: str,
            first: int = 30,
            after: str | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """List organization reports for an org with pagination.

            Args:
                organization_id: Organization ID.
                first: Page size (default 30).
                after: Cursor for next page.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.get_organization_reports(
                    organization_id, first=first, after=after
                )
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Get organization reports failed.", debug=debug
                )
            return build_report_read_success_payload(
                raw,
                message="Organization reports retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_pipe_report_export(
            export_id: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Check the status of a pipe report export. Poll this after calling `export_pipe_report`. States: processing -> done (with fileURL) -> failed.

            Args:
                export_id: Pipe report export ID.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.get_pipe_report_export(export_id)
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Get pipe report export failed.", debug=debug
                )
            return build_report_read_success_payload(
                raw,
                message="Pipe report export status retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_organization_report_export(
            export_id: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Check the status of an org report export. Poll this after calling `export_organization_report`.

            Args:
                export_id: Organization report export ID.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.get_organization_report_export(export_id)
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Get organization report export failed.", debug=debug
                )
            return build_report_read_success_payload(
                raw,
                message="Organization report export status retrieved.",
            )

        # --- CRUD tools ---

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_pipe_report(
            pipe_id: str,
            name: str,
            fields: list[str] | None = None,
            filter: dict | None = None,
            formulas: list[list[str]] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a pipe report. Use column `name` in `fields`; filter field names from `get_pipe_report_filterable_fields`.

            Args:
                pipe_id: Pipe ID (numeric string).
                name: Report name.
                fields: Internal field names (`name` from column discovery) to include as columns.
                filter: Report filter (ReportCardsFilter shape).
                formulas: Formula definitions (list of [field, operator, ...] tuples).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.create_pipe_report(
                    pipe_id, name, fields=fields, filter=filter, formulas=formulas
                )
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Create pipe report failed.", debug=debug
                )
            return build_report_mutation_success_payload(
                message="Pipe report created.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_pipe_report(
            report_id: str,
            name: str | None = None,
            color: str | None = None,
            fields: list[str] | None = None,
            filter: dict | None = None,
            formulas: list[list[str]] | None = None,
            featured_field: str | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update a pipe report. All params except `report_id` are optional -- only provided values are changed.

            Args:
                report_id: Pipe report ID.
                name: New report name.
                color: Report color.
                fields: Internal field names (`name` from column discovery).
                filter: Report filter (ReportCardsFilter shape).
                formulas: Formula definitions.
                featured_field: Featured field name.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.update_pipe_report(
                    report_id,
                    name=name,
                    color=color,
                    fields=fields,
                    filter=filter,
                    formulas=formulas,
                    featured_field=featured_field,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Update pipe report failed.", debug=debug
                )
            return build_report_mutation_success_payload(
                message="Pipe report updated.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_pipe_report(
            report_id: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a pipe report. This action is irreversible. Always confirm with the user before executing.

            Args:
                report_id: Pipe report ID to delete.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.delete_pipe_report(report_id)
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Delete pipe report failed.", debug=debug
                )
            return build_report_mutation_success_payload(
                message="Pipe report deleted.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_organization_report(
            organization_id: str,
            name: str,
            pipe_ids: list[str],
            fields: list[str] | None = None,
            filter: dict | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create an org-wide report spanning multiple pipes.

            Args:
                organization_id: Organization ID.
                name: Report name.
                pipe_ids: List of pipe IDs to include.
                fields: Column field IDs.
                filter: Report filter (ReportCardsFilter shape).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.create_organization_report(
                    organization_id, name, pipe_ids, fields=fields, filter=filter
                )
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Create organization report failed.", debug=debug
                )
            return build_report_mutation_success_payload(
                message="Organization report created.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_organization_report(
            report_id: str,
            name: str | None = None,
            color: str | None = None,
            fields: list[str] | None = None,
            filter: dict | None = None,
            pipe_ids: list[str] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update an organization report. All params except `report_id` are optional -- only provided values are changed.

            Args:
                report_id: Organization report ID.
                name: New report name.
                color: Report color.
                fields: Column field IDs.
                filter: Report filter (ReportCardsFilter shape).
                pipe_ids: Pipe IDs to include.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.update_organization_report(
                    report_id,
                    name=name,
                    color=color,
                    fields=fields,
                    filter=filter,
                    pipe_ids=pipe_ids,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Update organization report failed.", debug=debug
                )
            return build_report_mutation_success_payload(
                message="Organization report updated.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_organization_report(
            report_id: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete an organization report. This action is irreversible. Always confirm with the user before executing.

            Args:
                report_id: Organization report ID to delete.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.delete_organization_report(report_id)
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Delete organization report failed.", debug=debug
                )
            return build_report_mutation_success_payload(
                message="Organization report deleted.",
                data=raw,
            )

        # --- Export tools ---

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def export_pipe_report(
            pipe_id: str,
            pipe_report_id: str,
            sort_by: dict | None = None,
            filter: dict | None = None,
            columns: list[str] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Trigger an async pipe report export. Returns an export ID with state 'processing'. Poll `get_pipe_report_export(export_id)` to check when state becomes 'done' -- the response will include a `fileURL` to download the file.

            Args:
                pipe_id: Pipe ID (numeric string).
                pipe_report_id: Pipe report ID to export.
                sort_by: ReportSortDirectionInput (direction, field).
                filter: ReportCardsFilter shape.
                columns: Column field IDs for the export file.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.export_pipe_report(
                    pipe_id,
                    pipe_report_id,
                    sort_by=sort_by,
                    filter=filter,
                    columns=columns,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Export pipe report failed.", debug=debug
                )
            return build_report_mutation_success_payload(
                message="Pipe report export started.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def export_organization_report(
            organization_id: int,
            organization_report_id: int | None = None,
            pipe_ids: list[int] | None = None,
            sort_by: dict | None = None,
            filter: dict | None = None,
            columns: list[str] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Trigger an async organization report export. Poll `get_organization_report_export(export_id)` for completion.

            Args:
                organization_id: Organization numeric ID.
                organization_report_id: Report to export; omit to export by pipes only.
                pipe_ids: Pipe IDs to scope the export.
                sort_by: ReportSortDirectionInput.
                filter: ReportCardsFilter shape.
                columns: Column field IDs for the export file.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.export_organization_report(
                    organization_id,
                    organization_report_id=organization_report_id,
                    pipe_ids=pipe_ids,
                    sort_by=sort_by,
                    filter=filter,
                    columns=columns,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Export organization report failed.", debug=debug
                )
            return build_report_mutation_success_payload(
                message="Organization report export started.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def export_pipe_audit_logs(
            pipe_uuid: str,
            search_term: str | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Trigger an async export of pipe audit logs. Returns `success: true` when the export job is queued. Unlike report exports, there is no export ID to poll -- the file is delivered to the requesting user.

            Args:
                pipe_uuid: Pipe UUID.
                search_term: Optional filter on audit log content.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            try:
                raw = await client.export_pipe_audit_logs(
                    pipe_uuid,
                    search_term=search_term,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Export pipe audit logs failed.", debug=debug
                )
            return build_report_mutation_success_payload(
                message="Pipe audit logs export queued.",
                data=raw,
            )
