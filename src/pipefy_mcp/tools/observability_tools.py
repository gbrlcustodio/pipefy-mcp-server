"""MCP tools for Pipefy observability: AI agent logs, automation logs, usage, and exports."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from pipefy_mcp.models.validators import PipefyId
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.graphql_error_helpers import extract_error_strings
from pipefy_mcp.tools.observability_tool_helpers import (
    build_observability_error_payload,
    build_observability_mutation_success_payload,
    build_observability_read_success_payload,
    handle_observability_tool_graphql_error,
)
from pipefy_mcp.tools.validation_helpers import validate_tool_id

# --- Validation constants ---

_VALID_PERIODS = {"current_month", "last_month", "last_3_months"}

# Pagination
_MIN_PAGE_SIZE = 1
_MAX_PAGE_SIZE = 100

# CSV / export download limits
_MIN_CSV_CHARS = 256
_MAX_CSV_CHARS = 2_000_000
_DEFAULT_CSV_CHARS = 400_000
_MIN_EXPORT_DOWNLOAD_BYTES = 4096
_MAX_EXPORT_DOWNLOAD_BYTES = 80 * 1024 * 1024
_DEFAULT_EXPORT_DOWNLOAD_BYTES = 50 * 1024 * 1024


def _rewrite_ai_agent_log_not_found(exc: BaseException, log_uuid: str) -> str | None:
    """Translate the Pipefy resolver's internal type leak to tool semantics.

    The ``aiAgentLogDetails`` resolver looks up by ``AutomationAction`` under
    the hood; when the UUID isn't found, the upstream error string exposes
    that internal type (``"Couldn't find AutomationAction with 'id'=..."``).
    ``TransportQueryError`` hides per-error messages behind ``.errors``, so we
    check both ``str(exc)`` and the structured error list.
    """
    candidates = [str(exc), *extract_error_strings(exc)]
    for msg in candidates:
        lowered = msg.lower()
        if "automationaction" in lowered and (
            "couldn't find" in lowered or "not find" in lowered
        ):
            return f"AI agent log not found with uuid: {log_uuid}"
    return None


class ObservabilityTools:
    """MCP tools for monitoring AI agent and automation execution."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
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
                    exc,
                    "Get AI agent logs failed.",
                    debug=debug,
                    resource_kind="pipe",
                    resource_id=repo_uuid,
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
                rewritten = _rewrite_ai_agent_log_not_found(exc, log_uuid)
                if rewritten is not None:
                    return build_observability_error_payload(message=rewritten)
                return handle_observability_tool_graphql_error(
                    exc,
                    "Get AI agent log details failed.",
                    debug=debug,
                    resource_kind="ai_agent_log",
                    resource_id=log_uuid,
                )
            return build_observability_read_success_payload(
                raw, message="AI agent log details retrieved."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_automation_logs(
            automation_id: PipefyId,
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
            if not automation_id:
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
                    exc,
                    "Get automation logs failed.",
                    debug=debug,
                    resource_kind="automation",
                    resource_id=str(automation_id),
                )
            return build_observability_read_success_payload(
                raw, message="Automation logs retrieved."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_automation_logs_by_repo(
            repo_id: PipefyId,
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
            if not repo_id:
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
                    exc,
                    "Get automation logs by repo failed.",
                    debug=debug,
                    resource_kind="pipe",
                    resource_id=str(repo_id),
                )
            return build_observability_read_success_payload(
                raw, message="Automation logs by repo retrieved."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_agents_usage(
            organization_uuid: PipefyId,
            filter_date_from: str,
            filter_date_to: str,
            filters: dict[str, Any] | None = None,
            search: str | None = None,
            sort: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Get AI agent usage stats for an org within a date range. Returns total AI credits consumed and per-agent breakdown. `filter_date_from` and `filter_date_to` are ISO8601 datetime strings. Optional `filters` for action/event/pipe/status filtering.

            Args:
                organization_uuid: Organization UUID, or numeric organization id.
                filter_date_from: Start of date range (ISO8601).
                filter_date_to: End of date range (ISO8601).
                filters: Optional FilterParams dict (action, event, pipe, status keys).
                search: Free-text search.
                sort: SortCriteria dict (field + direction).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            organization_uuid, err = validate_tool_id(
                organization_uuid, "organization_uuid"
            )
            if err is not None:
                return err
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
                    exc,
                    "Get agents usage failed.",
                    debug=debug,
                    resource_kind="organization",
                    resource_id=str(organization_uuid),
                )
            return build_observability_read_success_payload(
                raw, message="Agents usage retrieved."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_automations_usage(
            organization_uuid: PipefyId,
            filter_date_from: str,
            filter_date_to: str,
            filters: dict[str, Any] | None = None,
            search: str | None = None,
            sort: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Get automation usage stats for an org within a date range. Returns total execution count and per-automation breakdown. Same input shape as `get_agents_usage`.

            Args:
                organization_uuid: Organization UUID, or numeric organization id.
                filter_date_from: Start of date range (ISO8601).
                filter_date_to: End of date range (ISO8601).
                filters: Optional FilterParams dict (action, event, pipe, status keys).
                search: Free-text search.
                sort: SortCriteria dict (field + direction).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            organization_uuid, err = validate_tool_id(
                organization_uuid, "organization_uuid"
            )
            if err is not None:
                return err
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
                    exc,
                    "Get automations usage failed.",
                    debug=debug,
                    resource_kind="organization",
                    resource_id=str(organization_uuid),
                )
            return build_observability_read_success_payload(
                raw, message="Automations usage retrieved."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_ai_credit_usage(
            organization_uuid: PipefyId,
            period: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Get AI credit usage dashboard for an org. Shows credit limit, total consumption, per-resource breakdown (AI Agents vs Assistants), addon status, and free credit info. `period`: 'current_month', 'last_month', or 'last_3_months'.

            Args:
                organization_uuid: Organization UUID, or numeric organization id (same as in the
                    Pipefy URL). Numeric ids are resolved to UUID automatically.
                period: PeriodFilter (current_month, last_month, last_3_months).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            organization_uuid, err = validate_tool_id(
                organization_uuid, "organization_uuid"
            )
            if err is not None:
                return err
            if period not in _VALID_PERIODS:
                return build_observability_error_payload(
                    message=f"Invalid 'period': must be one of {sorted(_VALID_PERIODS)}.",
                )
            try:
                raw = await client.get_ai_credit_usage(organization_uuid, period)
            except ValueError as exc:
                return build_observability_error_payload(message=str(exc))
            except Exception as exc:  # noqa: BLE001
                return handle_observability_tool_graphql_error(
                    exc,
                    "Get AI credit usage failed.",
                    debug=debug,
                    resource_kind="organization",
                    resource_id=str(organization_uuid),
                )
            return build_observability_read_success_payload(
                raw, message="AI credit usage retrieved."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def export_automation_jobs(
            organization_id: PipefyId,
            period: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Trigger async export of automation job history for an org. `period`: 'current_month', 'last_month', or 'last_3_months'. The export file is delivered to the requesting user.

            Args:
                organization_id: Organization ID (string or numeric).
                period: PeriodFilter (current_month, last_month, last_3_months).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            organization_id, err = validate_tool_id(organization_id, "organization_id")
            if err is not None:
                return err
            if period not in _VALID_PERIODS:
                return build_observability_error_payload(
                    message=f"Invalid 'period': must be one of {sorted(_VALID_PERIODS)}.",
                )
            try:
                raw = await client.export_automation_jobs(organization_id, period)
            except Exception as exc:  # noqa: BLE001
                return handle_observability_tool_graphql_error(
                    exc,
                    "Export automation jobs failed.",
                    debug=debug,
                    resource_kind="organization",
                    resource_id=str(organization_id),
                )
            return build_observability_mutation_success_payload(
                message="Automation jobs export triggered.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_automation_jobs_export(
            export_id: PipefyId,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Poll an automation jobs export by id. Returns `status` (`created`, `processing`, `finished`, `failed`) and `fileUrl` when the API provides a signed download link (often after `finished`). Use after `export_automation_jobs`; repeat until `finished` or `failed`. The tool does not download the file — use `fileUrl` over HTTP if needed.

            Args:
                export_id: Export id from `export_automation_jobs` result (`automationJobsExport.id`).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not export_id:
                return build_observability_error_payload(
                    message="Invalid 'export_id': provide a non-empty string.",
                )
            try:
                raw = await client.get_automation_jobs_export(export_id)
            except Exception as exc:  # noqa: BLE001
                return handle_observability_tool_graphql_error(
                    exc,
                    "Get automation jobs export failed.",
                    debug=debug,
                    resource_kind="automation",
                    resource_id=str(export_id),
                )
            return build_observability_read_success_payload(
                raw, message="Automation jobs export retrieved."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_automation_jobs_export_csv(
            export_id: PipefyId,
            max_output_chars: int = _DEFAULT_CSV_CHARS,
            max_download_bytes: int = _DEFAULT_EXPORT_DOWNLOAD_BYTES,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Download a finished automation-jobs export and return the first worksheet as CSV text for LLM consumption. The API provides an xlsx file which is converted to CSV automatically. Requires export ``status`` ``finished``. Only https URLs on ``*.pipefy.com`` from the API are fetched. Large exports are capped by ``max_output_chars`` and ``max_download_bytes``.

            Args:
                export_id: Export id from `export_automation_jobs` after the export is `finished`.
                max_output_chars: Max CSV characters returned (256–2_000_000); default 400_000.
                max_download_bytes: Max xlsx size to download (4 KiB–80 MiB); default 50 MiB.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not export_id:
                return build_observability_error_payload(
                    message="Invalid 'export_id': provide a non-empty string.",
                )
            if not isinstance(max_output_chars, int) or not (
                _MIN_CSV_CHARS <= max_output_chars <= _MAX_CSV_CHARS
            ):
                return build_observability_error_payload(
                    message=(
                        f"Invalid 'max_output_chars': must be an integer between "
                        f"{_MIN_CSV_CHARS} and {_MAX_CSV_CHARS}."
                    ),
                )
            if not isinstance(max_download_bytes, int) or not (
                _MIN_EXPORT_DOWNLOAD_BYTES
                <= max_download_bytes
                <= _MAX_EXPORT_DOWNLOAD_BYTES
            ):
                return build_observability_error_payload(
                    message=(
                        "Invalid 'max_download_bytes': must be an integer between "
                        f"{_MIN_EXPORT_DOWNLOAD_BYTES} and {_MAX_EXPORT_DOWNLOAD_BYTES}."
                    ),
                )
            try:
                raw = await client.get_automation_jobs_export_csv(
                    export_id,
                    max_output_chars=max_output_chars,
                    max_download_bytes=max_download_bytes,
                )
            except ValueError as exc:
                return build_observability_error_payload(message=str(exc))
            except Exception as exc:  # noqa: BLE001
                return handle_observability_tool_graphql_error(
                    exc,
                    "Get automation jobs export as CSV failed.",
                    debug=debug,
                    resource_kind="automation",
                    resource_id=str(export_id),
                )
            return build_observability_read_success_payload(
                raw, message="Automation jobs export converted to CSV (first sheet)."
            )
