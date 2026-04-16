"""GraphQL operations for Pipefy pipe and organization reports."""

from __future__ import annotations

from typing import Any

from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.report_queries import (
    CREATE_ORGANIZATION_REPORT_MUTATION,
    CREATE_PIPE_REPORT_MUTATION,
    DELETE_ORGANIZATION_REPORT_MUTATION,
    DELETE_PIPE_REPORT_MUTATION,
    EXPORT_ORGANIZATION_REPORT_MUTATION,
    EXPORT_PIPE_AUDIT_LOGS_MUTATION,
    EXPORT_PIPE_REPORT_MUTATION,
    GET_ORGANIZATION_REPORT_EXPORT_QUERY,
    GET_ORGANIZATION_REPORT_QUERY,
    GET_ORGANIZATION_REPORTS_QUERY,
    GET_PIPE_REPORT_COLUMNS_QUERY,
    GET_PIPE_REPORT_EXPORT_QUERY,
    GET_PIPE_REPORT_FILTERABLE_FIELDS_QUERY,
    GET_PIPE_REPORTS_QUERY,
    UPDATE_ORGANIZATION_REPORT_MUTATION,
    UPDATE_PIPE_REPORT_MUTATION,
)
from pipefy_mcp.settings import PipefySettings


class ReportService(BasePipefyClient):
    """Read, CRUD, and export operations for pipe and organization reports."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    async def get_pipe_reports(
        self,
        pipe_uuid: str,
        *,
        first: int = 30,
        after: str | None = None,
        search: str | None = None,
        report_id: str | None = None,
        order: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """List pipe reports with pagination and optional search/filter.

        The list query omits ``cardCount`` (Pipefy can error when resolving it).

        Args:
            pipe_uuid: Pipe UUID (not numeric ID).
            first: Page size (default 30).
            after: Cursor for next page.
            search: Free-text search on report name.
            report_id: Filter to a specific report ID.
            order: Sort order, e.g. ``{"field": "name", "direction": "asc"}``.
        """
        variables: dict[str, Any] = {"pipeUuid": pipe_uuid, "first": first}
        if after is not None:
            variables["after"] = after
        if search is not None:
            variables["search"] = search
        if report_id is not None:
            variables["reportId"] = report_id
        if order is not None:
            variables["order"] = order
        return await self.execute_query(GET_PIPE_REPORTS_QUERY, variables)

    async def get_pipe_report_columns(self, pipe_uuid: str) -> dict[str, Any]:
        """Get available columns for a pipe report.

        Args:
            pipe_uuid: Pipe UUID.
        """
        return await self.execute_query(
            GET_PIPE_REPORT_COLUMNS_QUERY,
            {"pipeUuid": pipe_uuid},
        )

    async def get_pipe_report_filterable_fields(self, pipe_uuid: str) -> dict[str, Any]:
        """Get filterable fields for a pipe report (grouped by section/phase).

        Args:
            pipe_uuid: Pipe UUID.
        """
        return await self.execute_query(
            GET_PIPE_REPORT_FILTERABLE_FIELDS_QUERY,
            {"pipeUuid": pipe_uuid},
        )

    async def get_organization_report(self, report_id: str) -> dict[str, Any]:
        """Get a single organization report by ID.

        Args:
            report_id: Organization report ID.
        """
        return await self.execute_query(
            GET_ORGANIZATION_REPORT_QUERY,
            {"id": str(report_id)},
        )

    async def get_organization_reports(
        self,
        organization_id: str,
        *,
        first: int = 30,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List organization reports with pagination.

        Args:
            organization_id: Organization ID.
            first: Page size (default 30).
            after: Cursor for next page.
        """
        variables: dict[str, Any] = {
            "organizationId": str(organization_id),
            "first": first,
        }
        if after is not None:
            variables["after"] = after
        return await self.execute_query(GET_ORGANIZATION_REPORTS_QUERY, variables)

    async def get_pipe_report_export(self, export_id: str) -> dict[str, Any]:
        """Check the status of a pipe report export.

        Args:
            export_id: Pipe report export ID.
        """
        return await self.execute_query(
            GET_PIPE_REPORT_EXPORT_QUERY,
            {"id": export_id},
        )

    async def get_organization_report_export(self, export_id: str) -> dict[str, Any]:
        """Check the status of an organization report export.

        Args:
            export_id: Organization report export ID.
        """
        return await self.execute_query(
            GET_ORGANIZATION_REPORT_EXPORT_QUERY,
            {"id": export_id},
        )

    async def create_pipe_report(
        self,
        pipe_id: str,
        name: str,
        *,
        fields: list[str] | None = None,
        filter: dict[str, Any] | None = None,
        formulas: list[list[str]] | None = None,
    ) -> dict[str, Any]:
        """Create a pipe report.

        Args:
            pipe_id: Pipe ID (numeric string).
            name: Report name.
            fields: Internal field names (``name`` from ``get_pipe_report_columns``).
            filter: Report filter (``ReportCardsFilter`` shape).
            formulas: Formula definitions (list of [field, operator, ...] tuples).
        """
        input_obj: dict[str, Any] = {"pipeId": str(pipe_id), "name": name}
        if fields is not None:
            input_obj["fields"] = fields
        if filter is not None:
            input_obj["filter"] = filter
        if formulas is not None:
            input_obj["formulas"] = formulas
        return await self.execute_query(
            CREATE_PIPE_REPORT_MUTATION, {"input": input_obj}
        )

    async def update_pipe_report(
        self,
        report_id: str,
        *,
        name: str | None = None,
        color: str | None = None,
        fields: list[str] | None = None,
        filter: dict[str, Any] | None = None,
        formulas: list[list[str]] | None = None,
        featured_field: str | None = None,
    ) -> dict[str, Any]:
        """Update a pipe report. Only provided values are changed.

        Args:
            report_id: Pipe report ID.
            name: New report name.
            color: Report color.
            fields: Internal field names for columns.
            filter: Report filter (``ReportCardsFilter`` shape).
            formulas: Formula definitions.
            featured_field: Featured field name.
        """
        input_obj: dict[str, Any] = {"id": str(report_id)}
        optional_fields = {
            "name": name,
            "color": color,
            "fields": fields,
            "filter": filter,
            "formulas": formulas,
            "featuredField": featured_field,
        }
        for key, value in optional_fields.items():
            if value is not None:
                input_obj[key] = value
        return await self.execute_query(
            UPDATE_PIPE_REPORT_MUTATION, {"input": input_obj}
        )

    async def delete_pipe_report(self, report_id: str) -> dict[str, Any]:
        """Delete a pipe report by ID (permanent).

        Args:
            report_id: Pipe report ID.
        """
        return await self.execute_query(
            DELETE_PIPE_REPORT_MUTATION, {"input": {"id": str(report_id)}}
        )

    async def create_organization_report(
        self,
        organization_id: str,
        name: str,
        pipe_ids: list[str],
        *,
        fields: list[str] | None = None,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an organization report spanning multiple pipes.

        Args:
            organization_id: Organization ID.
            name: Report name.
            pipe_ids: List of pipe IDs to include.
            fields: Internal field names for columns.
            filter: Report filter (``ReportCardsFilter`` shape).
        """
        input_obj: dict[str, Any] = {
            "organizationId": str(organization_id),
            "name": name,
            "pipeIds": [str(pid) for pid in pipe_ids],
        }
        if fields is not None:
            input_obj["fields"] = fields
        if filter is not None:
            input_obj["filter"] = filter
        return await self.execute_query(
            CREATE_ORGANIZATION_REPORT_MUTATION, {"input": input_obj}
        )

    async def update_organization_report(
        self,
        report_id: str,
        *,
        name: str | None = None,
        color: str | None = None,
        fields: list[str] | None = None,
        filter: dict[str, Any] | None = None,
        pipe_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an organization report. Only provided values are changed.

        Args:
            report_id: Organization report ID.
            name: New report name.
            color: Report color.
            fields: Internal field names for columns.
            filter: Report filter (``ReportCardsFilter`` shape).
            pipe_ids: Pipe IDs to include.
        """
        input_obj: dict[str, Any] = {"id": str(report_id)}
        optional_fields = {
            "name": name,
            "color": color,
            "fields": fields,
            "filter": filter,
            "pipeIds": [str(pid) for pid in pipe_ids] if pipe_ids is not None else None,
        }
        for key, value in optional_fields.items():
            if value is not None:
                input_obj[key] = value
        return await self.execute_query(
            UPDATE_ORGANIZATION_REPORT_MUTATION, {"input": input_obj}
        )

    async def delete_organization_report(self, report_id: str) -> dict[str, Any]:
        """Delete an organization report by ID (permanent).

        Args:
            report_id: Organization report ID.
        """
        return await self.execute_query(
            DELETE_ORGANIZATION_REPORT_MUTATION, {"input": {"id": str(report_id)}}
        )

    async def export_pipe_report(
        self,
        pipe_id: str,
        pipe_report_id: str,
        *,
        sort_by: dict[str, Any] | None = None,
        filter: dict[str, Any] | None = None,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Trigger an async pipe report export (poll ``get_pipe_report_export`` for completion).

        Args:
            pipe_id: Pipe ID (GraphQL ``ID``).
            pipe_report_id: Pipe report ID to export.
            sort_by: ``ReportSortDirectionInput`` (``direction``, ``field``).
            filter: ``ReportCardsFilter`` shape.
            columns: Column field IDs to include in the export file.
        """
        input_obj: dict[str, Any] = {
            "pipeId": str(pipe_id),
            "pipeReportId": str(pipe_report_id),
        }
        if sort_by is not None:
            input_obj["sortBy"] = sort_by
        if filter is not None:
            input_obj["filter"] = filter
        if columns is not None:
            input_obj["columns"] = columns
        return await self.execute_query(
            EXPORT_PIPE_REPORT_MUTATION, {"input": input_obj}
        )

    async def export_organization_report(
        self,
        organization_id: str | int,
        *,
        organization_report_id: str | int | None = None,
        pipe_ids: list[str | int] | None = None,
        sort_by: dict[str, Any] | None = None,
        filter: dict[str, Any] | None = None,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Trigger an async organization report export (poll ``get_organization_report_export``).

        Args:
            organization_id: Organization ID.
            organization_report_id: Report to export; omit to export by pipes only.
            pipe_ids: Pipe IDs to scope the export.
            sort_by: ``ReportSortDirectionInput``.
            filter: ``ReportCardsFilter`` shape.
            columns: Column field IDs for the export file.
        """
        input_obj: dict[str, Any] = {"organizationId": int(organization_id)}
        optional_fields = {
            "organizationReportId": int(organization_report_id)
            if organization_report_id is not None
            else None,
            "pipeIds": [str(pid) for pid in pipe_ids] if pipe_ids is not None else None,
            "sortBy": sort_by,
            "filter": filter,
            "columns": columns,
        }
        for key, value in optional_fields.items():
            if value is not None:
                input_obj[key] = value
        return await self.execute_query(
            EXPORT_ORGANIZATION_REPORT_MUTATION, {"input": input_obj}
        )

    async def export_pipe_audit_logs(
        self,
        pipe_uuid: str,
        *,
        search_term: str | None = None,
    ) -> dict[str, Any]:
        """Trigger an async pipe audit logs export (returns ``success`` only; no export ID to poll).

        Args:
            pipe_uuid: Pipe UUID.
            search_term: Optional filter on audit log content.
        """
        input_obj: dict[str, Any] = {"pipeUuid": pipe_uuid}
        if search_term is not None:
            input_obj["searchTerm"] = search_term
        return await self.execute_query(
            EXPORT_PIPE_AUDIT_LOGS_MUTATION, {"input": input_obj}
        )
