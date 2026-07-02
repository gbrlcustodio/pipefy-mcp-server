"""Service for Pipefy observability: AI agent logs, automation logs, usage stats, and exports."""

from __future__ import annotations

from typing import Any, TypedDict
from zipfile import BadZipFile

import httpx
from openpyxl.utils.exceptions import InvalidFileException

from pipefy_sdk.graphql_executor import GraphQLExecutor, PartialQueryResult
from pipefy_sdk.queries.observability_queries import (
    CREATE_AUTOMATION_JOBS_EXPORT_MUTATION,
    GET_AGENTS_USAGE_QUERY,
    GET_AI_AGENT_LOG_DETAILS_QUERY,
    GET_AI_AGENT_LOGS_QUERY,
    GET_AI_CREDIT_USAGE_QUERY,
    GET_AUTOMATION_EXECUTION_METRICS_QUERY,
    GET_AUTOMATION_JOBS_EXPORT_QUERY,
    GET_AUTOMATION_LOGS_BY_REPO_QUERY,
    GET_AUTOMATION_LOGS_QUERY,
    GET_AUTOMATIONS_USAGE_QUERY,
)
from pipefy_sdk.services.observability_export_csv import (
    download_bytes,
    xlsx_first_sheet_to_csv_limited,
)
from pipefy_sdk.utils.organization_identifiers import resolve_organization_uuid
from pipefy_sdk.utils.relay import unwrap_relay_connection_nodes

_DEFAULT_PAGE_SIZE = 30


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
    filter_date: DateRange,
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


def _partial_error(err: dict[str, Any]) -> dict[str, Any]:
    """Project one raw GraphQL error dict onto the per-automation failure shape."""
    extensions = err.get("extensions") or {}
    return {
        "automation_id": extensions.get("automation_id"),
        "code": extensions.get("code"),
        "message": err.get("message"),
        "correlation_id": extensions.get("correlation_id"),
    }


def _normalize_execution_metrics_result(result: PartialQueryResult) -> dict[str, Any]:
    """Split a partial ``automations.executionMetrics`` response into nodes and errors.

    ``result.data`` carries the automations the token may read (each with its
    ``executionMetrics``); ``result.errors`` carries per-automation failures
    (e.g. ``PERMISSION_DENIED``) with ``automation_id`` in ``extensions``. Both are
    returned so the caller can report a partial success.

    A null ``automations`` connection means the lookup itself failed (bad org, no
    org access) rather than individual nodes being denied; that is a total failure,
    so this raises ``ValueError`` instead of reporting an empty partial success.
    An empty ``edges`` list (every requested automation denied) stays a partial
    success with a populated ``partial_errors``.

    Args:
        result: PartialQueryResult from ``execute_query_allow_partial``.
    """
    connection = result.data.get("automations")
    if connection is None and result.errors:
        raise ValueError(result.errors[0].get("message") or "Query failed.")
    automations = unwrap_relay_connection_nodes(connection)
    partial_errors = [_partial_error(err) for err in result.errors]
    return {"automations": automations, "partial_errors": partial_errors}


class ObservabilityService:
    """Reads for AI agent logs, automation logs, usage stats, and credit dashboard."""

    def __init__(self, *, executor: GraphQLExecutor) -> None:
        self._executor = executor

    async def get_automation_execution_metrics(
        self,
        organization_id: str,
        automation_ids: list[str] | None = None,
        *,
        repo_id: str | None = None,
        period: str = "SIXTY_MINUTES",
    ) -> dict[str, Any]:
        """Get execution metrics for one or more automations within a rolling period.

        Partial success: returns metrics for the automations this token may read,
        plus a ``partial_errors`` list naming any automations that failed
        (e.g. ``PERMISSION_DENIED``). The ``automations`` query reports per-node
        errors alongside data, so this uses the partial-tolerant execute path.

        Args:
            organization_id: Organization ID (required by the ``automations`` query;
                a numeric org id, not a UUID).
            automation_ids: Automation IDs to fetch metrics for. When ``None``,
                the ``automationIds`` filter is omitted and the query returns
                metrics for every automation in the organization (optionally
                scoped by ``repo_id``).
            repo_id: Optional pipe/repo ID to scope the query.
            period: AutomationExecutionMetricsPeriod enum value (FIFTEEN_MINUTES,
                SIXTY_MINUTES, TWELVE_HOURS, TWENTY_FOUR_HOURS). Defaults to
                SIXTY_MINUTES, matching the API default.
        """
        variables: dict[str, Any] = {
            "organizationId": organization_id,
            "period": period,
        }
        if automation_ids is not None:
            variables["automationIds"] = automation_ids
        if repo_id is not None:
            variables["repoId"] = repo_id
        result = await self._executor.execute_query_allow_partial(
            GET_AUTOMATION_EXECUTION_METRICS_QUERY, variables
        )
        return _normalize_execution_metrics_result(result)

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
        return await self._executor.execute_query(GET_AI_AGENT_LOGS_QUERY, variables)

    async def get_ai_agent_log_details(self, log_uuid: str) -> dict[str, Any]:
        """Get detailed AI agent execution log with tracing nodes.

        Args:
            log_uuid: UUID of the AI agent log entry.
        """
        return await self._executor.execute_query(
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
        return await self._executor.execute_query(GET_AUTOMATION_LOGS_QUERY, variables)

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
        return await self._executor.execute_query(
            GET_AUTOMATION_LOGS_BY_REPO_QUERY, variables
        )

    async def get_agents_usage(
        self,
        organization_uuid: str,
        filter_date: DateRange,
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
        resolved = await resolve_organization_uuid(
            self._executor.execute_query, organization_uuid
        )
        variables = _build_usage_variables(
            resolved,
            filter_date,
            filters=filters,
            search=search,
            sort=sort,
        )
        return await self._executor.execute_query(GET_AGENTS_USAGE_QUERY, variables)

    async def get_automations_usage(
        self,
        organization_uuid: str,
        filter_date: DateRange,
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
        resolved = await resolve_organization_uuid(
            self._executor.execute_query, organization_uuid
        )
        variables = _build_usage_variables(
            resolved,
            filter_date,
            filters=filters,
            search=search,
            sort=sort,
        )
        return await self._executor.execute_query(
            GET_AUTOMATIONS_USAGE_QUERY, variables
        )

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
        resolved = await resolve_organization_uuid(
            self._executor.execute_query, organization_uuid
        )
        return await self._executor.execute_query(
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
        return await self._executor.execute_query(
            CREATE_AUTOMATION_JOBS_EXPORT_MUTATION,
            {"input": {"organizationId": str(organization_id), "filter": period}},
        )

    async def get_automation_jobs_export(self, export_id: str) -> dict[str, Any]:
        """Load automation jobs export status and download URL by id.

        Args:
            export_id: Export id returned by ``createAutomationJobsExport`` (same as ``automationJobsExport.id``).
        """
        return await self._executor.execute_query(
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
