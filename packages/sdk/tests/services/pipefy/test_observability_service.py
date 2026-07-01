"""Unit tests for ObservabilityService (logs, usage, and export)."""

import io
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from _shared.fixture_ids import EXAMPLE_NUMERIC_ORG_ID, EXAMPLE_ORG_UUID
from _shared.mock_clients import mock_executor
from gql.transport.exceptions import TransportQueryError
from graphql import ExecutionResult, GraphQLError
from openpyxl import Workbook

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
    RESOLVE_ORGANIZATION_UUID_QUERY,
)
from pipefy_sdk.services.observability_service import ObservabilityService


def _make_service(return_value):
    executor = mock_executor(return_value)
    service = ObservabilityService(executor=executor)
    return service, executor


def _make_partial_service(execution_result):
    executor = mock_executor()
    executor.execute_query_allow_partial = AsyncMock(return_value=execution_result)
    service = ObservabilityService(executor=executor)
    return service, executor


def _metrics_node(automation_id: str, *, total_runs: int) -> dict:
    return {
        "id": automation_id,
        "name": f"Automation {automation_id}",
        "event_id": "card_moved",
        "action_id": "update_card_field",
        "event_repo": {"id": "16", "name": "Execution Metrics 16"},
        "executionMetrics": {
            "lastRun": None,
            "failureRate": 0.0,
            "successRate": 0.0,
            "averageDuration": None,
            "totalRuns": total_runs,
        },
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_agent_logs_success():
    payload = {
        "aiAgentLogsByRepo": {
            "nodes": [
                {
                    "uuid": "log-1",
                    "agentUuid": "agent-1",
                    "agentName": "My Agent",
                    "automationId": "auto-1",
                    "automationName": "Auto Rule",
                    "cardId": "100",
                    "cardTitle": "Card A",
                    "status": "success",
                    "createdAt": "2026-03-01T00:00:00Z",
                    "updatedAt": "2026-03-01T00:01:00Z",
                },
                {
                    "uuid": "log-2",
                    "agentUuid": "agent-1",
                    "agentName": "My Agent",
                    "automationId": "auto-1",
                    "automationName": "Auto Rule",
                    "cardId": "101",
                    "cardTitle": "Card B",
                    "status": "failed",
                    "createdAt": "2026-03-02T00:00:00Z",
                    "updatedAt": "2026-03-02T00:01:00Z",
                },
            ],
            "pageInfo": {"hasNextPage": True, "endCursor": "cursor-abc"},
            "totalCount": 50,
        }
    }
    service, executor = _make_service(payload)
    result = await service.get_ai_agent_logs("repo-uuid-1")

    executor.execute_query.assert_awaited_once()
    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AI_AGENT_LOGS_QUERY
    assert variables == {"repoUuid": "repo-uuid-1", "first": 30}
    assert len(result["aiAgentLogsByRepo"]["nodes"]) == 2
    assert result["aiAgentLogsByRepo"]["totalCount"] == 50


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_agent_logs_with_status_filter():
    payload = {
        "aiAgentLogsByRepo": {
            "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "totalCount": 0,
        }
    }
    service, executor = _make_service(payload)
    await service.get_ai_agent_logs("repo-uuid-1", status="failed", search_term="error")

    _, variables = executor.execute_query.call_args[0]
    assert variables["status"] == "failed"
    assert variables["searchTerm"] == "error"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_agent_log_details_success():
    payload = {
        "aiAgentLogDetails": {
            "uuid": "log-1",
            "agentUuid": "agent-1",
            "agentName": "My Agent",
            "automation": {"id": "auto-1", "name": "Auto Rule"},
            "cardId": "100",
            "cardTitle": "Card A",
            "status": "success",
            "executionTime": 12.5,
            "createdAt": "2026-03-01T00:00:00Z",
            "finishedAt": "2026-03-01T00:00:12Z",
            "tracingNodes": [
                {"nodeName": "Step 1", "status": "success", "message": "Done"},
                {"nodeName": "Step 2", "status": "failed", "message": "Timeout"},
            ],
        }
    }
    service, executor = _make_service(payload)
    result = await service.get_ai_agent_log_details("log-1")

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AI_AGENT_LOG_DETAILS_QUERY
    assert variables == {"uuid": "log-1"}
    assert len(result["aiAgentLogDetails"]["tracingNodes"]) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_logs_success():
    payload = {
        "automationLogs": {
            "nodes": [
                {
                    "uuid": "alog-1",
                    "automationId": "auto-1",
                    "automationName": "My Auto",
                    "cardId": "200",
                    "cardTitle": "Card X",
                    "datetime": "2026-03-01T10:00:00Z",
                    "status": "success",
                },
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "totalCount": 1,
        }
    }
    service, executor = _make_service(payload)
    result = await service.get_automation_logs("auto-1")

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AUTOMATION_LOGS_QUERY
    assert variables == {"automationId": "auto-1", "first": 30}
    assert result["automationLogs"]["totalCount"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_logs_by_repo_success():
    payload = {
        "automationLogsByRepo": {
            "nodes": [
                {
                    "uuid": "alog-2",
                    "automationId": "auto-2",
                    "automationName": "Other Auto",
                    "cardId": "300",
                    "cardTitle": "Card Y",
                    "datetime": "2026-03-02T12:00:00Z",
                    "status": "processing",
                },
            ],
            "pageInfo": {"hasNextPage": True, "endCursor": "cur-xyz"},
            "totalCount": 15,
        }
    }
    service, executor = _make_service(payload)
    result = await service.get_automation_logs_by_repo(
        "repo-5", first=10, after="cur-0"
    )

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AUTOMATION_LOGS_BY_REPO_QUERY
    assert variables == {"repoId": "repo-5", "first": 10, "after": "cur-0"}
    assert result["automationLogsByRepo"]["totalCount"] == 15


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_agent_logs_transport_error():
    executor = mock_executor(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    service = ObservabilityService(executor=executor)
    with pytest.raises(TransportQueryError):
        await service.get_ai_agent_logs("repo-uuid-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agents_usage_success():
    payload = {
        "agentsUsageDetails": {
            "usage": 42.5,
            "agents": {
                "nodes": [
                    {"id": "a1", "name": "Agent 1", "usage": 20.0, "status": "active"},
                ],
                "totalCount": 3,
                "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
            },
        }
    }
    service, executor = _make_service(payload)
    filter_date = {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"}
    result = await service.get_agents_usage(EXAMPLE_ORG_UUID, filter_date)

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AGENTS_USAGE_QUERY
    assert variables == {
        "organizationUuid": EXAMPLE_ORG_UUID,
        "filterDate": filter_date,
    }
    assert result["agentsUsageDetails"]["usage"] == 42.5
    assert result["agentsUsageDetails"]["agents"]["totalCount"] == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_usage_success():
    payload = {
        "automationsUsageDetails": {
            "usage": 500,
            "automations": {
                "nodes": [
                    {"id": "r1", "name": "Rule 1", "usage": 100, "status": "active"},
                ],
                "totalCount": 5,
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            },
        }
    }
    service, executor = _make_service(payload)
    filter_date = {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"}
    result = await service.get_automations_usage(
        EXAMPLE_ORG_UUID, filter_date, search="Rule"
    )

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AUTOMATIONS_USAGE_QUERY
    assert variables["organizationUuid"] == EXAMPLE_ORG_UUID
    assert variables["filterDate"] == filter_date
    assert variables["search"] == "Rule"
    assert result["automationsUsageDetails"]["usage"] == 500


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_credit_usage_success():
    payload = {
        "aiCreditUsageStats": {
            "active": True,
            "usage": 150.0,
            "limit": 1000,
            "hasAddon": False,
            "updatedAt": "2026-03-20T00:00:00Z",
            "aiAutomation": {"enabled": True, "usage": 100.0},
            "assistants": {"enabled": True, "usage": 50.0},
            "freeAiCredit": {"limit": 200, "usage": 150.0},
            "filterDate": {
                "from": "2026-03-01T00:00:00Z",
                "to": "2026-03-31T23:59:59Z",
            },
        }
    }
    service, executor = _make_service(payload)
    result = await service.get_ai_credit_usage(EXAMPLE_ORG_UUID, "current_month")

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AI_CREDIT_USAGE_QUERY
    assert variables == {
        "organizationUuid": EXAMPLE_ORG_UUID,
        "period": "current_month",
    }
    assert result["aiCreditUsageStats"]["usage"] == 150.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_credit_usage_resolves_numeric_organization_id():
    resolve_payload = {"organization": {"uuid": EXAMPLE_ORG_UUID}}
    credit_payload = {
        "aiCreditUsageStats": {
            "active": True,
            "usage": 10.0,
            "limit": 0,
            "hasAddon": False,
            "updatedAt": "2026-03-20T00:00:00Z",
            "aiAutomation": {"enabled": True, "usage": 10.0},
            "assistants": {"enabled": True, "usage": 0.0},
            "freeAiCredit": None,
            "filterDate": {
                "from": "2026-03-01T00:00:00Z",
                "to": "2026-03-20T00:00:00Z",
            },
        }
    }
    executor = mock_executor(side_effect=[resolve_payload, credit_payload])
    service = ObservabilityService(executor=executor)
    result = await service.get_ai_credit_usage(EXAMPLE_NUMERIC_ORG_ID, "current_month")

    assert executor.execute_query.call_count == 2
    calls = executor.execute_query.call_args_list
    assert calls[0][0][0] is RESOLVE_ORGANIZATION_UUID_QUERY
    assert calls[0][0][1] == {"id": EXAMPLE_NUMERIC_ORG_ID}
    assert calls[1][0][0] is GET_AI_CREDIT_USAGE_QUERY
    assert calls[1][0][1] == {
        "organizationUuid": EXAMPLE_ORG_UUID,
        "period": "current_month",
    }
    assert result["aiCreditUsageStats"]["usage"] == 10.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_credit_usage_resolve_fails_when_organization_missing():
    executor = mock_executor({"organization": None})
    service = ObservabilityService(executor=executor)
    with pytest.raises(ValueError, match="Organization not found"):
        await service.get_ai_credit_usage("999999999", "current_month")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_automation_jobs_success():
    payload = {
        "createAutomationJobsExport": {
            "automationJobsExport": {
                "id": "exp-1",
                "status": "processing",
                "fileUrl": None,
            }
        }
    }
    service, executor = _make_service(payload)
    result = await service.export_automation_jobs("123", "last_month")

    query, variables = executor.execute_query.call_args[0]
    assert query is CREATE_AUTOMATION_JOBS_EXPORT_MUTATION
    assert variables == {"input": {"organizationId": "123", "filter": "last_month"}}
    assert result["createAutomationJobsExport"]["automationJobsExport"]["id"] == "exp-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_jobs_export_success():
    payload = {
        "automationJobsExport": {
            "id": "25820",
            "status": "processing",
            "fileUrl": None,
        }
    }
    service, executor = _make_service(payload)
    result = await service.get_automation_jobs_export("25820")

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AUTOMATION_JOBS_EXPORT_QUERY
    assert variables == {"id": "25820"}
    assert result["automationJobsExport"]["status"] == "processing"


def _tiny_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["h"])
    ws.append(["v"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_jobs_export_csv_success():
    xlsx = _tiny_xlsx_bytes()
    executor = mock_executor(
        {
            "automationJobsExport": {
                "id": "9",
                "status": "finished",
                "fileUrl": "https://app.pipefy.com/storage/x.xlsx",
            }
        }
    )
    service = ObservabilityService(executor=executor)
    with patch(
        "pipefy_sdk.services.observability_service.download_bytes",
        new_callable=AsyncMock,
        return_value=xlsx,
    ):
        out = await service.get_automation_jobs_export_csv("9")

    assert out["export_id"] == "9"
    assert out["status"] == "finished"
    assert out["row_count"] == 2
    assert "h" in out["csv"]
    assert out["csv_truncated"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_jobs_export_csv_not_finished():
    executor = mock_executor(
        {
            "automationJobsExport": {
                "id": "9",
                "status": "processing",
                "fileUrl": None,
            }
        }
    )
    service = ObservabilityService(executor=executor)
    with pytest.raises(ValueError, match="finished"):
        await service.get_automation_jobs_export_csv("9")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_jobs_export_csv_download_error():
    executor = mock_executor(
        {
            "automationJobsExport": {
                "id": "9",
                "status": "finished",
                "fileUrl": "https://app.pipefy.com/storage/x.xlsx",
            }
        }
    )
    service = ObservabilityService(executor=executor)
    req = httpx.Request("GET", "https://app.pipefy.com/storage/x.xlsx")
    with patch(
        "pipefy_sdk.services.observability_service.download_bytes",
        new_callable=AsyncMock,
        side_effect=httpx.RequestError("boom", request=req),
    ):
        with pytest.raises(ValueError, match="Failed to download"):
            await service.get_automation_jobs_export_csv("9")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agents_usage_transport_error():
    executor = mock_executor(
        side_effect=TransportQueryError("failed", errors=[{"message": "forbidden"}])
    )
    service = ObservabilityService(executor=executor)
    filter_date = {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"}
    with pytest.raises(TransportQueryError):
        await service.get_agents_usage(EXAMPLE_ORG_UUID, filter_date)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_logs_transport_error():
    executor = mock_executor(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    service = ObservabilityService(executor=executor)
    with pytest.raises(TransportQueryError):
        await service.get_automation_logs("auto-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agents_usage_resolves_numeric_organization_id():
    resolve_payload = {"organization": {"uuid": EXAMPLE_ORG_UUID}}
    usage_payload = {
        "agentsUsage": {
            "data": [{"agentName": "Bot", "totalCredits": 5.0}],
            "totalCredits": 5.0,
        }
    }
    executor = mock_executor(side_effect=[resolve_payload, usage_payload])
    service = ObservabilityService(executor=executor)
    filter_date = {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"}
    result = await service.get_agents_usage(EXAMPLE_NUMERIC_ORG_ID, filter_date)

    assert executor.execute_query.call_count == 2
    calls = executor.execute_query.call_args_list
    assert calls[0][0][0] is RESOLVE_ORGANIZATION_UUID_QUERY
    assert calls[0][0][1] == {"id": EXAMPLE_NUMERIC_ORG_ID}
    assert calls[1][0][0] is GET_AGENTS_USAGE_QUERY
    assert calls[1][0][1]["organizationUuid"] == EXAMPLE_ORG_UUID
    assert result["agentsUsage"]["totalCredits"] == 5.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_usage_resolves_numeric_organization_id():
    resolve_payload = {"organization": {"uuid": EXAMPLE_ORG_UUID}}
    usage_payload = {
        "automationsUsage": {
            "data": [{"automationName": "Rule 1", "totalExecutions": 42}],
            "totalExecutions": 42,
        }
    }
    executor = mock_executor(side_effect=[resolve_payload, usage_payload])
    service = ObservabilityService(executor=executor)
    filter_date = {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"}
    result = await service.get_automations_usage(EXAMPLE_NUMERIC_ORG_ID, filter_date)

    assert executor.execute_query.call_count == 2
    calls = executor.execute_query.call_args_list
    assert calls[0][0][0] is RESOLVE_ORGANIZATION_UUID_QUERY
    assert calls[0][0][1] == {"id": EXAMPLE_NUMERIC_ORG_ID}
    assert calls[1][0][0] is GET_AUTOMATIONS_USAGE_QUERY
    assert calls[1][0][1]["organizationUuid"] == EXAMPLE_ORG_UUID
    assert result["automationsUsage"]["totalExecutions"] == 42


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_execution_metrics_all_permitted():
    """Full success: all requested automations return metrics, no partial errors."""
    execution_result = ExecutionResult(
        data={
            "automations": {
                "edges": [
                    {"node": _metrics_node("25", total_runs=3)},
                    {"node": _metrics_node("107", total_runs=0)},
                ]
            }
        },
        errors=None,
    )
    service, executor = _make_partial_service(execution_result)

    result = await service.get_automation_execution_metrics(
        "3", ["25", "107"], repo_id="16", period="TWENTY_FOUR_HOURS"
    )

    executor.execute_query_allow_partial.assert_awaited_once()
    query, variables = executor.execute_query_allow_partial.call_args[0]
    assert query is GET_AUTOMATION_EXECUTION_METRICS_QUERY
    assert variables == {
        "organizationId": "3",
        "automationIds": ["25", "107"],
        "period": "TWENTY_FOUR_HOURS",
        "repoId": "16",
    }
    assert [a["id"] for a in result["automations"]] == ["25", "107"]
    assert result["automations"][0]["executionMetrics"]["totalRuns"] == 3
    assert result["partial_errors"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_execution_metrics_partial_permission_denied():
    """Partial success: permitted nodes returned, denied ids surfaced in partial_errors."""
    execution_result = ExecutionResult(
        data={"automations": {"edges": [{"node": _metrics_node("25", total_runs=3)}]}},
        errors=[
            GraphQLError(
                "Permission denied",
                extensions={
                    "code": "PERMISSION_DENIED",
                    "automation_id": "124",
                    "correlation_id": "c86ccfa6",
                },
            ),
            GraphQLError(
                "Permission denied",
                extensions={
                    "code": "PERMISSION_DENIED",
                    "automation_id": "65",
                    "correlation_id": "c86ccfa6",
                },
            ),
        ],
    )
    service, executor = _make_partial_service(execution_result)

    result = await service.get_automation_execution_metrics("3", ["25", "124", "65"])

    assert [a["id"] for a in result["automations"]] == ["25"]
    assert result["partial_errors"] == [
        {
            "automation_id": "124",
            "code": "PERMISSION_DENIED",
            "message": "Permission denied",
            "correlation_id": "c86ccfa6",
        },
        {
            "automation_id": "65",
            "code": "PERMISSION_DENIED",
            "message": "Permission denied",
            "correlation_id": "c86ccfa6",
        },
    ]
    # repo_id omitted → not sent as a variable
    _, variables = executor.execute_query_allow_partial.call_args[0]
    assert "repoId" not in variables


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_execution_metrics_null_data():
    """Defensive: null data (total failure shape) yields empty automations list."""
    execution_result = ExecutionResult(
        data=None,
        errors=[GraphQLError("boom", extensions={"code": "INTERNAL"})],
    )
    service, _ = _make_partial_service(execution_result)

    result = await service.get_automation_execution_metrics("3", ["25"])

    assert result["automations"] == []
    assert result["partial_errors"][0]["code"] == "INTERNAL"
    assert result["partial_errors"][0]["automation_id"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_execution_metrics_without_ids_omits_filter():
    """Omitting automation_ids drops the automationIds variable so the query returns all."""
    execution_result = ExecutionResult(
        data={
            "automations": {
                "edges": [
                    {"node": _metrics_node("25", total_runs=3)},
                    {"node": _metrics_node("107", total_runs=0)},
                ]
            }
        },
        errors=None,
    )
    service, executor = _make_partial_service(execution_result)

    result = await service.get_automation_execution_metrics("3")

    _, variables = executor.execute_query_allow_partial.call_args[0]
    assert "automationIds" not in variables
    assert variables == {"organizationId": "3", "period": "SIXTY_MINUTES"}
    assert [a["id"] for a in result["automations"]] == ["25", "107"]
