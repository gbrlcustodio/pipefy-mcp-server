"""Service for Pipefy observability: AI agent logs, automation logs, usage stats, and exports."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict
from zipfile import BadZipFile

import httpx
from openpyxl.utils.exceptions import InvalidFileException

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.observability_export_csv import (
    download_bytes,
    xlsx_first_sheet_to_csv_limited,
)
from pipefy_mcp.services.pipefy.queries.observability_queries import (
    CREATE_AUTOMATION_JOBS_EXPORT_MUTATION,
    GET_AGENTS_USAGE_QUERY,
    GET_AI_AGENT_LOG_DETAILS_QUERY,
    GET_AI_AGENT_LOGS_QUERY,
    GET_AI_CREDIT_USAGE_QUERY,
    GET_AUTOMATION_JOBS_EXPORT_QUERY,
    GET_AUTOMATION_LOGS_BY_REPO_QUERY,
    GET_AUTOMATION_LOGS_QUERY,
    GET_AUTOMATIONS_USAGE_QUERY,
    RESOLVE_ORGANIZATION_UUID_QUERY,
)

_DEFAULT_PAGE_SIZE = 30


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(value.strip())
    except ValueError:
        return False
    return True


DateRange = TypedDict("DateRange", {"from": str, "to": str})


def _build_log_variables(
    primary_key: str,
    primary_value: str,
    *,
    first: int,
    after: str | None,
    status: str | None,
    search_term: str | None,
) -> dict[str, Any]:
    """Build the GraphQL variables dict shared by all paginated log queries.

    Args:
        primary_key: GraphQL variable name for the main identifier (e.g. ``repoUuid``).
        primary_value: Value for that identifier.
        first: Page size.
        after: Cursor for next page.
        status: Optional status filter.
        search_term: Optional free-text search.
    """
    variables: dict[str, Any] = {primary_key: primary_value, "first": first}
    if after is not None:
        variables["after"] = after
    if status is not None:
        variables["status"] = status
    if search_term is not None:
        variables["searchTerm"] = search_term
    return variables


def _build_usage_variables(
    organization_uuid: str,
    filter_date: dict[str, str],
    *,
    filters: dict[str, Any] | None,
    search: str | None,
    sort: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the GraphQL variables dict shared by usage-stats queries.

    Args:
        organization_uuid: Organization UUID.
        filter_date: DateRange dict with ``from`` and ``to`` ISO8601 strings.
        filters: Optional FilterParams (action, event, pipe, status).
        search: Free-text search.
        sort: SortCriteria (field + direction).
    """
    variables: dict[str, Any] = {
        "organizationUuid": organization_uuid,
        "filterDate": filter_date,
    }
    if filters is not None:
        variables["filters"] = filters
    if search is not None:
        variables["search"] = search
    if sort is not None:
        variables["sort"] = sort
    return variables


class ObservabilityService(BasePipefyClient):
    """Reads for AI agent logs, automation logs, usage stats, and credit dashboard."""

    async def _resolve_organization_uuid(self, organization_identifier: str) -> str:
        """Return the organization UUID, resolving numeric IDs via GraphQL.

        Pipefy accepts a numeric organization id in URLs, but several GraphQL queries expect
        ``organizationUuid``. When the caller passes digits only, resolve via ``organization``.

        Args:
            organization_identifier: Organization UUID, or numeric organization id as a string.

        Returns:
            Organization UUID string for GraphQL variables.

        Raises:
            ValueError: When the identifier is empty, or resolution yields no uuid.
        """
        trimmed = organization_identifier.strip()
        if not trimmed:
            raise ValueError("organization identifier must be non-empty")
        if _looks_like_uuid(trimmed):
            return trimmed
        if trimmed.isdigit():
            result = await self.execute_query(
                RESOLVE_ORGANIZATION_UUID_QUERY,
                {"id": trimmed},
            )
            org = result.get("organization")
            uuid_value = org.get("uuid") if isinstance(org, dict) else None
            if not uuid_value:
                raise ValueError(
                    f"Organization not found or has no uuid for id: {trimmed}"
                )
            return str(uuid_value)
        raise ValueError(
            f"organization identifier must be a UUID or numeric id, got: {trimmed!r}"
        )

    async def get_ai_agent_logs(
        self,
        repo_uuid: str,
        *,
        first: int = _DEFAULT_PAGE_SIZE,
        after: str | None = None,
        status: str | None = None,
        search_term: str | None = None,
    ) -> dict[str, Any]:
        """List AI agent execution logs for a pipe (paginated connection).

        Args:
            repo_uuid: Pipe UUID (repo identifier).
            first: Page size (default 30).
            after: Cursor for next page.
            status: Filter by AiAgentLogStatus (processing, failed, success).
            search_term: Free-text search within logs.
        """
        variables = _build_log_variables(
            "repoUuid",
            repo_uuid,
            first=first,
            after=after,
            status=status,
            search_term=search_term,
        )
        return await self.execute_query(GET_AI_AGENT_LOGS_QUERY, variables)

    async def get_ai_agent_log_details(self, log_uuid: str) -> dict[str, Any]:
        """Get detailed AI agent execution log with tracing nodes.

        Args:
            log_uuid: UUID of the AI agent log entry.
        """
        return await self.execute_query(
            GET_AI_AGENT_LOG_DETAILS_QUERY, {"uuid": log_uuid}
        )

    async def get_automation_logs(
        self,
        automation_id: str,
        *,
        first: int = _DEFAULT_PAGE_SIZE,
        after: str | None = None,
        status: str | None = None,
        search_term: str | None = None,
    ) -> dict[str, Any]:
        """List execution logs for a specific automation (paginated connection).

        Args:
            automation_id: Automation ID.
            first: Page size (default 30).
            after: Cursor for next page.
            status: Filter by AutomationLogStatus (processing, failed, success).
            search_term: Free-text search within logs.
        """
        variables = _build_log_variables(
            "automationId",
            automation_id,
            first=first,
            after=after,
            status=status,
            search_term=search_term,
        )
        return await self.execute_query(GET_AUTOMATION_LOGS_QUERY, variables)

    async def get_automation_logs_by_repo(
        self,
        repo_id: str,
        *,
        first: int = _DEFAULT_PAGE_SIZE,
        after: str | None = None,
        status: str | None = None,
        search_term: str | None = None,
    ) -> dict[str, Any]:
        """List automation logs for all automations in a pipe/repo (paginated connection).

        Args:
            repo_id: Pipe/repo ID.
            first: Page size (default 30).
            after: Cursor for next page.
            status: Filter by AutomationLogStatus (processing, failed, success).
            search_term: Free-text search within logs.
        """
        variables = _build_log_variables(
            "repoId",
            repo_id,
            first=first,
            after=after,
            status=status,
            search_term=search_term,
        )
        return await self.execute_query(GET_AUTOMATION_LOGS_BY_REPO_QUERY, variables)

    async def get_agents_usage(
        self,
        organization_uuid: str,
        filter_date: dict[str, str],
        *,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        sort: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get AI agent usage stats for an org within a date range.

        Args:
            organization_uuid: Organization UUID, or numeric organization id (string).
                Numeric ids are resolved to UUID via a short GraphQL query.
            filter_date: DateRange dict with ``from`` and ``to`` ISO8601 strings.
            filters: Optional FilterParams (action, event, pipe, status).
            search: Free-text search.
            sort: SortCriteria (field + direction).
        """
        resolved = await self._resolve_organization_uuid(organization_uuid)
        variables = _build_usage_variables(
            resolved,
            filter_date,
            filters=filters,
            search=search,
            sort=sort,
        )
        return await self.execute_query(GET_AGENTS_USAGE_QUERY, variables)

    async def get_automations_usage(
        self,
        organization_uuid: str,
        filter_date: dict[str, str],
        *,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        sort: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get automation usage stats for an org within a date range.

        Args:
            organization_uuid: Organization UUID, or numeric organization id (string).
                Numeric ids are resolved to UUID via a short GraphQL query.
            filter_date: DateRange dict with ``from`` and ``to`` ISO8601 strings.
            filters: Optional FilterParams (action, event, pipe, status).
            search: Free-text search.
            sort: SortCriteria (field + direction).
        """
        resolved = await self._resolve_organization_uuid(organization_uuid)
        variables = _build_usage_variables(
            resolved,
            filter_date,
            filters=filters,
            search=search,
            sort=sort,
        )
        return await self.execute_query(GET_AUTOMATIONS_USAGE_QUERY, variables)

    async def get_ai_credit_usage(
        self,
        organization_uuid: str,
        period: str,
    ) -> dict[str, Any]:
        """Get AI credit usage dashboard for an org.

        Args:
            organization_uuid: Organization UUID, or numeric organization id (string). Numeric ids
                are resolved to UUID via a short GraphQL query before calling ``aiCreditUsageStats``.
            period: PeriodFilter enum value (current_month, last_month, last_3_months).
        """
        resolved = await self._resolve_organization_uuid(organization_uuid)
        return await self.execute_query(
            GET_AI_CREDIT_USAGE_QUERY,
            {"organizationUuid": resolved, "period": period},
        )

    async def export_automation_jobs(
        self,
        organization_id: str,
        period: str,
    ) -> dict[str, Any]:
        """Trigger async export of automation job history.

        Args:
            organization_id: Organization ID.
            period: PeriodFilter enum value (current_month, last_month, last_3_months). Sent as
                GraphQL input field ``filter`` (Pipefy schema no longer exposes ``period`` on this input).
        """
        return await self.execute_query(
            CREATE_AUTOMATION_JOBS_EXPORT_MUTATION,
            {"input": {"organizationId": organization_id, "filter": period}},
        )

    async def get_automation_jobs_export(self, export_id: str) -> dict[str, Any]:
        """Load automation jobs export status and download URL by id.

        Args:
            export_id: Export id returned by ``createAutomationJobsExport`` (same as ``automationJobsExport.id``).
        """
        return await self.execute_query(
            GET_AUTOMATION_JOBS_EXPORT_QUERY,
            {"id": export_id},
        )

    async def get_automation_jobs_export_csv(
        self,
        export_id: str,
        *,
        max_output_chars: int = 400_000,
        max_download_bytes: int = 50 * 1024 * 1024,
    ) -> dict[str, Any]:
        """Resolve a finished export, download the xlsx, and return the first sheet as CSV text.

        Args:
            export_id: Export id from ``export_automation_jobs`` / ``get_automation_jobs_export``.
            max_output_chars: Cap on returned CSV size (UTF-8 characters); adds a truncation line if exceeded.
            max_download_bytes: Refuse downloads larger than this many bytes.
        """
        raw = await self.get_automation_jobs_export(export_id)
        node = raw.get("automationJobsExport")
        if not isinstance(node, dict):
            raise ValueError(
                "Export not found or not visible for this token (automationJobsExport is null)."
            )
        status = node.get("status")
        if status != "finished":
            raise ValueError(
                f"Export status is {status!r}; wait until it is 'finished' "
                "(poll get_automation_jobs_export)."
            )
        file_url = node.get("fileUrl")
        if not file_url or not isinstance(file_url, str):
            raise ValueError("Export has no fileUrl.")

        try:
            body = await download_bytes(file_url, max_bytes=max_download_bytes)
        except httpx.HTTPError as exc:
            raise ValueError(f"Failed to download export file: {exc}") from exc

        try:
            csv_text, rows, sheet_name, truncated = xlsx_first_sheet_to_csv_limited(
                body, max_output_chars=max_output_chars
            )
        except (BadZipFile, InvalidFileException, OSError, ValueError) as exc:
            raise ValueError(
                "Could not parse export as XLSX (first sheet to CSV)."
            ) from exc

        return {
            "export_id": export_id,
            "status": status,
            "sheet_name": sheet_name,
            "row_count": rows,
            "csv_truncated": truncated,
            "max_output_chars": max_output_chars,
            "csv": csv_text,
        }
