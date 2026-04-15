"""MCP tools for Pipefy pipe and organization reports."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from pipefy_mcp.models.validators import PipefyId
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.report_tool_helpers import (
    build_report_error_payload,
    build_report_mutation_success_payload,
    build_report_read_success_payload,
    handle_report_tool_graphql_error,
)
from pipefy_mcp.tools.validation_helpers import validate_tool_id


def _blank_field_error(value: str, field: str) -> dict[str, Any] | None:
    """Return an error payload when ``value`` is blank."""
    if not value.strip():
        return build_report_error_payload(message=f"'{field}' must be non-empty.")
    return None


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
            report_id: PipefyId | None = None,
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
            err = _blank_field_error(pipe_uuid, "pipe_uuid")
            if err is not None:
                return err
            if first < 1:
                return build_report_error_payload(
                    message="'first' must be a positive integer.",
                )
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
        async def get_pipe_report(
            ctx: Context[ServerSession, None],
            pipe_uuid: str,
            report_id: PipefyId,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Fetch one pipe report by ID.

            Uses a filtered list query (``report_id`` + ``first: 1``) — Pipefy exposes no
            dedicated single-report read field for pipe reports.

            Args:
                pipe_uuid: Pipe UUID (not numeric ID).
                report_id: Pipe report ID.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            await ctx.debug(
                f"get_pipe_report: pipe_uuid={pipe_uuid}, report_id={report_id}"
            )
            err = _blank_field_error(pipe_uuid, "pipe_uuid")
            if err is not None:
                return err
            err = _blank_field_error(report_id, "report_id")
            if err is not None:
                return err
            try:
                raw = await client.get_pipe_reports(
                    pipe_uuid,
                    first=1,
                    report_id=report_id,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_report_tool_graphql_error(
                    exc, "Get pipe report failed.", debug=debug
                )
            edges = (raw.get("pipeReports") or {}).get("edges") or []
            node: dict[str, Any] | None = None
            if edges:
                first_edge = edges[0]
                if isinstance(first_edge, dict):
                    node = first_edge.get("node")
            if not node:
                return build_report_error_payload(
                    message=f"Pipe report not found (report_id={report_id}).",
                )
            return build_report_read_success_payload(
                {"pipeReport": node},
                message="Pipe report retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_pipe_report_columns(
            pipe_uuid: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Get available columns for a pipe report. Each item includes `name` (internal field id for `fields`) and `label`.

            The ``name`` values here are for **report** configuration and exports only; they are
            not the same slugs used by ``find_cards`` (use ``get_phase_fields`` / ``get_start_form_fields`` for that).

            Args:
                pipe_uuid: Pipe UUID.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            err = _blank_field_error(pipe_uuid, "pipe_uuid")
            if err is not None:
                return err
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

            Like ``get_pipe_report_columns``, the ``name`` keys are for **reports**, not for ``find_cards``.

            Args:
                pipe_uuid: Pipe UUID.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            err = _blank_field_error(pipe_uuid, "pipe_uuid")
            if err is not None:
                return err
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
            report_id: PipefyId,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Get a single organization report by ID.

            Args:
                report_id: Organization report ID.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            err = _blank_field_error(report_id, "report_id")
            if err is not None:
                return err
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
            organization_id: PipefyId,
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
            err = _blank_field_error(organization_id, "organization_id")
            if err is not None:
                return err
            if first < 1:
                return build_report_error_payload(
                    message="'first' must be a positive integer.",
                )
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
            export_id: PipefyId,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Check the status of a pipe report export. Poll this after calling `export_pipe_report`. States: processing -> done (with fileURL) -> failed.

            Args:
                export_id: Pipe report export ID.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            err = _blank_field_error(export_id, "export_id")
            if err is not None:
                return err
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
            export_id: PipefyId,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Check the status of an org report export. Poll this after calling `export_organization_report`.

            Args:
                export_id: Organization report export ID.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            err = _blank_field_error(export_id, "export_id")
            if err is not None:
                return err
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

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_pipe_report(
            pipe_id: PipefyId,
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
            err = _blank_field_error(pipe_id, "pipe_id")
            if err is not None:
                return err
            err = _blank_field_error(name, "name")
            if err is not None:
                return err
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
            report_id: PipefyId,
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
            err = _blank_field_error(report_id, "report_id")
            if err is not None:
                return err
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
            ctx: Context[ServerSession, None],
            report_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a pipe report. This action is irreversible.

            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval. Elicitation does not authorize
            deletion (only ``confirm=True`` does).

            Args:
                report_id: Pipe report ID to delete.
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            err = _blank_field_error(report_id, "report_id")
            if err is not None:
                return err

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"pipe report (ID: {report_id})",
            )
            if guard is not None:
                return guard

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
            organization_id: PipefyId,
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
            err = _blank_field_error(organization_id, "organization_id")
            if err is not None:
                return err
            err = _blank_field_error(name, "name")
            if err is not None:
                return err
            if not pipe_ids or not isinstance(pipe_ids, list):
                return build_report_error_payload(
                    message="'pipe_ids' must be a non-empty list.",
                )
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
            report_id: PipefyId,
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
            err = _blank_field_error(report_id, "report_id")
            if err is not None:
                return err
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
            ctx: Context[ServerSession, None],
            report_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete an organization report. This action is irreversible.

            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval. Elicitation does not authorize
            deletion (only ``confirm=True`` does).

            Args:
                report_id: Organization report ID to delete.
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            err = _blank_field_error(report_id, "report_id")
            if err is not None:
                return err

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"organization report (ID: {report_id})",
            )
            if guard is not None:
                return guard

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

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def export_pipe_report(
            pipe_id: PipefyId,
            pipe_report_id: PipefyId,
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
            err = _blank_field_error(pipe_id, "pipe_id")
            if err is not None:
                return err
            err = _blank_field_error(pipe_report_id, "pipe_report_id")
            if err is not None:
                return err
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
            organization_id: PipefyId,
            organization_report_id: PipefyId | None = None,
            pipe_ids: list[PipefyId] | None = None,
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
            _, err = validate_tool_id(organization_id, "organization_id")
            if err is not None:
                return err
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
            err = _blank_field_error(pipe_uuid, "pipe_uuid")
            if err is not None:
                return err
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
