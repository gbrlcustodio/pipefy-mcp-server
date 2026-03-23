"""Service for Pipefy observability: AI agent logs, automation logs, usage stats, and exports."""

from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.observability_queries import (
    CREATE_AUTOMATION_JOBS_EXPORT_MUTATION,
    GET_AGENTS_USAGE_QUERY,
    GET_AI_AGENT_LOG_DETAILS_QUERY,
    GET_AI_AGENT_LOGS_QUERY,
    GET_AI_CREDIT_USAGE_QUERY,
    GET_AUTOMATION_LOGS_BY_REPO_QUERY,
    GET_AUTOMATION_LOGS_QUERY,
    GET_AUTOMATIONS_USAGE_QUERY,
)

_DEFAULT_PAGE_SIZE = 30


class DateRange(TypedDict):
    """ISO8601 date range for usage queries (``from`` and ``to``)."""

    from_: str  # serialised as "from" in GraphQL variables
    to: str


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

    # --- Usage & Credits ---

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
            organization_uuid: Organization UUID.
            filter_date: DateRange dict with ``from`` and ``to`` ISO8601 strings.
            filters: Optional FilterParams (action, event, pipe, status).
            search: Free-text search.
            sort: SortCriteria (field + direction).
        """
        variables = _build_usage_variables(
            organization_uuid,
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
            organization_uuid: Organization UUID.
            filter_date: DateRange dict with ``from`` and ``to`` ISO8601 strings.
            filters: Optional FilterParams (action, event, pipe, status).
            search: Free-text search.
            sort: SortCriteria (field + direction).
        """
        variables = _build_usage_variables(
            organization_uuid,
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
            organization_uuid: Organization UUID.
            period: PeriodFilter enum value (current_month, last_month, last_3_months).
        """
        return await self.execute_query(
            GET_AI_CREDIT_USAGE_QUERY,
            {"organizationUuid": organization_uuid, "period": period},
        )

    # --- Export ---

    async def export_automation_jobs(
        self,
        organization_id: str,
        period: str,
    ) -> dict[str, Any]:
        """Trigger async export of automation job history.

        Args:
            organization_id: Organization ID.
            period: PeriodFilter enum value (current_month, last_month, last_3_months).
        """
        return await self.execute_query(
            CREATE_AUTOMATION_JOBS_EXPORT_MUTATION,
            {"input": {"organizationId": organization_id, "period": period}},
        )
