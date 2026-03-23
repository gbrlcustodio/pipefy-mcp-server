"""MCP tools for Pipefy observability: AI agent logs, automation logs, usage, and exports."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.observability_tool_helpers import (
    build_observability_error_payload,
    build_observability_mutation_success_payload,
    build_observability_read_success_payload,
    handle_observability_tool_graphql_error,
)

_VALID_PERIODS = {"current_month", "last_month", "last_3_months"}
_MIN_PAGE_SIZE = 1
_MAX_PAGE_SIZE = 100


class ObservabilityTools:
    """MCP tools for monitoring AI agent and automation execution."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        # --- Log tools ---

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_ai_agent_logs(
            repo_uuid: str,
            first: int = 30,
            after: str | None = None,
            status: str | None = None,
            search_term: str | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """List AI agent execution logs for a pipe. Filter by status (processing, failed, success) and searchTerm. Returns paginated results with totalCount. Use `get_ai_agent_log_details` to inspect a specific log's execution trace.

            Args:
                repo_uuid: Pipe UUID (repo identifier).
                first: Page size (default 30).
                after: Cursor for next page.
                status: AiAgentLogStatus filter (processing, failed, success).
                search_term: Free-text search within logs.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not repo_uuid or not isinstance(repo_uuid, str):
                return build_observability_error_payload(
                    message="Invalid 'repo_uuid': provide a non-empty string.",
                )
            if not _MIN_PAGE_SIZE <= first <= _MAX_PAGE_SIZE:
                return build_observability_error_payload(
                    message=f"Invalid 'first': must be between {_MIN_PAGE_SIZE} and {_MAX_PAGE_SIZE}.",
                )
            try:
                raw = await client.get_ai_agent_logs(
                    repo_uuid,
                    first=first,
                    after=after,
                    status=status,
                    search_term=search_term,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_observability_tool_graphql_error(
                    exc, "Get AI agent logs failed.", debug=debug
                )
            return build_observability_read_success_payload(
                raw, message="AI agent logs retrieved."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_ai_agent_log_details(
            log_uuid: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Get detailed AI agent execution log by UUID. Includes executionTime, finishedAt, and tracingNodes — a step-by-step trace of each action the agent performed with per-node status (success, failed, skipped, conditions_not_met).

            Args:
                log_uuid: UUID of the AI agent log entry.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not log_uuid or not isinstance(log_uuid, str):
                return build_observability_error_payload(
                    message="Invalid 'log_uuid': provide a non-empty string.",
                )
            try:
                raw = await client.get_ai_agent_log_details(log_uuid)
            except Exception as exc:  # noqa: BLE001
                return handle_observability_tool_graphql_error(
                    exc, "Get AI agent log details failed.", debug=debug
                )
            return build_observability_read_success_payload(
                raw, message="AI agent log details retrieved."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_automation_logs(
            automation_id: str,
            first: int = 30,
            after: str | None = None,
            status: str | None = None,
            search_term: str | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """List execution logs for a specific automation by automation ID. Filter by status (processing, failed, success). Returns paginated results with card context.

            Args:
                automation_id: Automation ID.
                first: Page size (default 30).
                after: Cursor for next page.
                status: AutomationLogStatus filter (processing, failed, success).
                search_term: Free-text search within logs.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not automation_id or not isinstance(automation_id, str):
                return build_observability_error_payload(
                    message="Invalid 'automation_id': provide a non-empty string.",
                )
            if not _MIN_PAGE_SIZE <= first <= _MAX_PAGE_SIZE:
                return build_observability_error_payload(
                    message=f"Invalid 'first': must be between {_MIN_PAGE_SIZE} and {_MAX_PAGE_SIZE}.",
                )
            try:
                raw = await client.get_automation_logs(
                    automation_id,
                    first=first,
                    after=after,
                    status=status,
                    search_term=search_term,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_observability_tool_graphql_error(
                    exc, "Get automation logs failed.", debug=debug
                )
            return build_observability_read_success_payload(
                raw, message="Automation logs retrieved."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_automation_logs_by_repo(
            repo_id: str,
            first: int = 30,
            after: str | None = None,
            status: str | None = None,
            search_term: str | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """List automation execution logs for all automations in a pipe/repo. Filter by status and searchTerm. Use when troubleshooting all automations in a pipe, not just one.

            Args:
                repo_id: Pipe/repo ID.
                first: Page size (default 30).
                after: Cursor for next page.
                status: AutomationLogStatus filter (processing, failed, success).
                search_term: Free-text search within logs.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not repo_id or not isinstance(repo_id, str):
                return build_observability_error_payload(
                    message="Invalid 'repo_id': provide a non-empty string.",
                )
            if not _MIN_PAGE_SIZE <= first <= _MAX_PAGE_SIZE:
                return build_observability_error_payload(
                    message=f"Invalid 'first': must be between {_MIN_PAGE_SIZE} and {_MAX_PAGE_SIZE}.",
                )
            try:
                raw = await client.get_automation_logs_by_repo(
                    repo_id,
                    first=first,
                    after=after,
                    status=status,
                    search_term=search_term,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_observability_tool_graphql_error(
                    exc, "Get automation logs by repo failed.", debug=debug
                )
            return build_observability_read_success_payload(
                raw, message="Automation logs by repo retrieved."
            )

        # --- Usage & Credits tools ---

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_agents_usage(
            organization_uuid: str,
            filter_date_from: str,
            filter_date_to: str,
            filters: dict[str, Any] | None = None,
            search: str | None = None,
            sort: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Get AI agent usage stats for an org within a date range. Returns total AI credits consumed and per-agent breakdown. `filter_date_from` and `filter_date_to` are ISO8601 datetime strings. Optional `filters` for action/event/pipe/status filtering.

            Args:
                organization_uuid: Organization UUID.
                filter_date_from: Start of date range (ISO8601).
                filter_date_to: End of date range (ISO8601).
                filters: Optional FilterParams dict (action, event, pipe, status keys).
                search: Free-text search.
                sort: SortCriteria dict (field + direction).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not organization_uuid or not isinstance(organization_uuid, str):
                return build_observability_error_payload(
                    message="Invalid 'organization_uuid': provide a non-empty string.",
                )
            if not filter_date_from or not filter_date_to:
                return build_observability_error_payload(
                    message="Both 'filter_date_from' and 'filter_date_to' are required.",
                )
            try:
                raw = await client.get_agents_usage(
                    organization_uuid,
                    {"from": filter_date_from, "to": filter_date_to},
                    filters=filters,
                    search=search,
                    sort=sort,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_observability_tool_graphql_error(
                    exc, "Get agents usage failed.", debug=debug
                )
            return build_observability_read_success_payload(
                raw, message="Agents usage retrieved."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_automations_usage(
            organization_uuid: str,
            filter_date_from: str,
            filter_date_to: str,
            filters: dict[str, Any] | None = None,
            search: str | None = None,
            sort: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Get automation usage stats for an org within a date range. Returns total execution count and per-automation breakdown. Same input shape as `get_agents_usage`.

            Args:
                organization_uuid: Organization UUID.
                filter_date_from: Start of date range (ISO8601).
                filter_date_to: End of date range (ISO8601).
                filters: Optional FilterParams dict (action, event, pipe, status keys).
                search: Free-text search.
                sort: SortCriteria dict (field + direction).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not organization_uuid or not isinstance(organization_uuid, str):
                return build_observability_error_payload(
                    message="Invalid 'organization_uuid': provide a non-empty string.",
                )
            if not filter_date_from or not filter_date_to:
                return build_observability_error_payload(
                    message="Both 'filter_date_from' and 'filter_date_to' are required.",
                )
            try:
                raw = await client.get_automations_usage(
                    organization_uuid,
                    {"from": filter_date_from, "to": filter_date_to},
                    filters=filters,
                    search=search,
                    sort=sort,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_observability_tool_graphql_error(
                    exc, "Get automations usage failed.", debug=debug
                )
            return build_observability_read_success_payload(
                raw, message="Automations usage retrieved."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_ai_credit_usage(
            organization_uuid: str,
            period: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Get AI credit usage dashboard for an org. Shows credit limit, total consumption, per-resource breakdown (AI Agents vs Assistants), addon status, and free credit info. `period`: 'current_month', 'last_month', or 'last_3_months'.

            Args:
                organization_uuid: Organization UUID.
                period: PeriodFilter (current_month, last_month, last_3_months).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not organization_uuid or not isinstance(organization_uuid, str):
                return build_observability_error_payload(
                    message="Invalid 'organization_uuid': provide a non-empty string.",
                )
            if period not in _VALID_PERIODS:
                return build_observability_error_payload(
                    message=f"Invalid 'period': must be one of {sorted(_VALID_PERIODS)}.",
                )
            try:
                raw = await client.get_ai_credit_usage(organization_uuid, period)
            except Exception as exc:  # noqa: BLE001
                return handle_observability_tool_graphql_error(
                    exc, "Get AI credit usage failed.", debug=debug
                )
            return build_observability_read_success_payload(
                raw, message="AI credit usage retrieved."
            )

        # --- Export tool ---

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def export_automation_jobs(
            organization_id: str,
            period: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Trigger async export of automation job history for an org. `period`: 'current_month', 'last_month', or 'last_3_months'. The export file is delivered to the requesting user.

            Args:
                organization_id: Organization ID.
                period: PeriodFilter (current_month, last_month, last_3_months).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not organization_id or not isinstance(organization_id, str):
                return build_observability_error_payload(
                    message="Invalid 'organization_id': provide a non-empty string.",
                )
            if period not in _VALID_PERIODS:
                return build_observability_error_payload(
                    message=f"Invalid 'period': must be one of {sorted(_VALID_PERIODS)}.",
                )
            try:
                raw = await client.export_automation_jobs(organization_id, period)
            except Exception as exc:  # noqa: BLE001
                return handle_observability_tool_graphql_error(
                    exc, "Export automation jobs failed.", debug=debug
                )
            return build_observability_mutation_success_payload(
                message="Automation jobs export triggered.",
                data=raw,
            )
