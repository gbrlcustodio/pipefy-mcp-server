"""Unit tests for ObservabilityService (logs, usage, and export)."""

import io
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from gql.transport.exceptions import TransportQueryError
from openpyxl import Workbook

from pipefy_mcp.services.pipefy.observability_service import ObservabilityService
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
from pipefy_mcp.settings import PipefySettings

_ORG_UUID_FOR_TESTS = "341c1327-261c-4766-bb96-7953e4c3970d"


@pytest.fixture
def mock_settings():
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings, return_value):
    service = ObservabilityService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_agent_logs_success(mock_settings):
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
    service = _make_service(mock_settings, payload)
    result = await service.get_ai_agent_logs("repo-uuid-1")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is GET_AI_AGENT_LOGS_QUERY
    assert variables == {"repoUuid": "repo-uuid-1", "first": 30}
    assert len(result["aiAgentLogsByRepo"]["nodes"]) == 2
    assert result["aiAgentLogsByRepo"]["totalCount"] == 50


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_agent_logs_with_status_filter(mock_settings):
    payload = {
        "aiAgentLogsByRepo": {
            "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "totalCount": 0,
        }
    }
    service = _make_service(mock_settings, payload)
    await service.get_ai_agent_logs("repo-uuid-1", status="failed", search_term="error")

    _, variables = service.execute_query.call_args[0]
    assert variables["status"] == "failed"
    assert variables["searchTerm"] == "error"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_agent_log_details_success(mock_settings):
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
    service = _make_service(mock_settings, payload)
    result = await service.get_ai_agent_log_details("log-1")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AI_AGENT_LOG_DETAILS_QUERY
    assert variables == {"uuid": "log-1"}
    assert len(result["aiAgentLogDetails"]["tracingNodes"]) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_logs_success(mock_settings):
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
    service = _make_service(mock_settings, payload)
    result = await service.get_automation_logs("auto-1")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AUTOMATION_LOGS_QUERY
    assert variables == {"automationId": "auto-1", "first": 30}
    assert result["automationLogs"]["totalCount"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_logs_by_repo_success(mock_settings):
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
    service = _make_service(mock_settings, payload)
    result = await service.get_automation_logs_by_repo(
        "repo-5", first=10, after="cur-0"
    )

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AUTOMATION_LOGS_BY_REPO_QUERY
    assert variables == {"repoId": "repo-5", "first": 10, "after": "cur-0"}
    assert result["automationLogsByRepo"]["totalCount"] == 15


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_agent_logs_transport_error(mock_settings):
    service = ObservabilityService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_ai_agent_logs("repo-uuid-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agents_usage_success(mock_settings):
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
    service = _make_service(mock_settings, payload)
    filter_date = {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"}
    result = await service.get_agents_usage(_ORG_UUID_FOR_TESTS, filter_date)

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AGENTS_USAGE_QUERY
    assert variables == {
        "organizationUuid": _ORG_UUID_FOR_TESTS,
        "filterDate": filter_date,
    }
    assert result["agentsUsageDetails"]["usage"] == 42.5
    assert result["agentsUsageDetails"]["agents"]["totalCount"] == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_usage_success(mock_settings):
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
    service = _make_service(mock_settings, payload)
    filter_date = {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"}
    result = await service.get_automations_usage(
        _ORG_UUID_FOR_TESTS, filter_date, search="Rule"
    )

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AUTOMATIONS_USAGE_QUERY
    assert variables["organizationUuid"] == _ORG_UUID_FOR_TESTS
    assert variables["filterDate"] == filter_date
    assert variables["search"] == "Rule"
    assert result["automationsUsageDetails"]["usage"] == 500


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_credit_usage_success(mock_settings):
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
    service = _make_service(mock_settings, payload)
    result = await service.get_ai_credit_usage(_ORG_UUID_FOR_TESTS, "current_month")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AI_CREDIT_USAGE_QUERY
    assert variables == {
        "organizationUuid": _ORG_UUID_FOR_TESTS,
        "period": "current_month",
    }
    assert result["aiCreditUsageStats"]["usage"] == 150.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_credit_usage_resolves_numeric_organization_id(mock_settings):
    resolve_payload = {"organization": {"uuid": "341c1327-261c-4766-bb96-7953e4c3970d"}}
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
    service = ObservabilityService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=[resolve_payload, credit_payload])
    result = await service.get_ai_credit_usage("300514213", "current_month")

    assert service.execute_query.call_count == 2
    calls = service.execute_query.call_args_list
    assert calls[0][0][0] is RESOLVE_ORGANIZATION_UUID_QUERY
    assert calls[0][0][1] == {"id": "300514213"}
    assert calls[1][0][0] is GET_AI_CREDIT_USAGE_QUERY
    assert calls[1][0][1] == {
        "organizationUuid": "341c1327-261c-4766-bb96-7953e4c3970d",
        "period": "current_month",
    }
    assert result["aiCreditUsageStats"]["usage"] == 10.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_credit_usage_resolve_fails_when_organization_missing(
    mock_settings,
):
    service = ObservabilityService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value={"organization": None})
    with pytest.raises(ValueError, match="Organization not found"):
        await service.get_ai_credit_usage("999999999", "current_month")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_automation_jobs_success(mock_settings):
    payload = {
        "createAutomationJobsExport": {
            "automationJobsExport": {
                "id": "exp-1",
                "status": "processing",
                "fileUrl": None,
            }
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.export_automation_jobs("123", "last_month")

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_AUTOMATION_JOBS_EXPORT_MUTATION
    assert variables == {"input": {"organizationId": "123", "filter": "last_month"}}
    assert result["createAutomationJobsExport"]["automationJobsExport"]["id"] == "exp-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_jobs_export_success(mock_settings):
    payload = {
        "automationJobsExport": {
            "id": "25820",
            "status": "processing",
            "fileUrl": None,
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_automation_jobs_export("25820")

    query, variables = service.execute_query.call_args[0]
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
async def test_get_automation_jobs_export_csv_success(mock_settings):
    xlsx = _tiny_xlsx_bytes()
    service = ObservabilityService(settings=mock_settings)
    service.execute_query = AsyncMock(
        return_value={
            "automationJobsExport": {
                "id": "9",
                "status": "finished",
                "fileUrl": "https://app.pipefy.com/storage/x.xlsx",
            }
        }
    )
    with patch(
        "pipefy_mcp.services.pipefy.observability_service.download_bytes",
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
async def test_get_automation_jobs_export_csv_not_finished(mock_settings):
    service = ObservabilityService(settings=mock_settings)
    service.execute_query = AsyncMock(
        return_value={
            "automationJobsExport": {
                "id": "9",
                "status": "processing",
                "fileUrl": None,
            }
        }
    )
    with pytest.raises(ValueError, match="finished"):
        await service.get_automation_jobs_export_csv("9")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_jobs_export_csv_download_error(mock_settings):
    service = ObservabilityService(settings=mock_settings)
    service.execute_query = AsyncMock(
        return_value={
            "automationJobsExport": {
                "id": "9",
                "status": "finished",
                "fileUrl": "https://app.pipefy.com/storage/x.xlsx",
            }
        }
    )
    req = httpx.Request("GET", "https://app.pipefy.com/storage/x.xlsx")
    with patch(
        "pipefy_mcp.services.pipefy.observability_service.download_bytes",
        new_callable=AsyncMock,
        side_effect=httpx.RequestError("boom", request=req),
    ):
        with pytest.raises(ValueError, match="Failed to download"):
            await service.get_automation_jobs_export_csv("9")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agents_usage_transport_error(mock_settings):
    service = ObservabilityService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "forbidden"}])
    )
    filter_date = {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"}
    with pytest.raises(TransportQueryError):
        await service.get_agents_usage(_ORG_UUID_FOR_TESTS, filter_date)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_organization_uuid_rejects_non_uuid_non_numeric(mock_settings):
    service = ObservabilityService(settings=mock_settings)
    with pytest.raises(ValueError, match="must be a UUID or numeric id"):
        await service._resolve_organization_uuid("not-a-uuid-or-digits")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_logs_transport_error(mock_settings):
    service = ObservabilityService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_automation_logs("auto-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agents_usage_resolves_numeric_organization_id(mock_settings):
    resolve_payload = {"organization": {"uuid": "341c1327-261c-4766-bb96-7953e4c3970d"}}
    usage_payload = {
        "agentsUsage": {
            "data": [{"agentName": "Bot", "totalCredits": 5.0}],
            "totalCredits": 5.0,
        }
    }
    service = ObservabilityService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=[resolve_payload, usage_payload])
    filter_date = {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"}
    result = await service.get_agents_usage("300514213", filter_date)

    assert service.execute_query.call_count == 2
    calls = service.execute_query.call_args_list
    assert calls[0][0][0] is RESOLVE_ORGANIZATION_UUID_QUERY
    assert calls[0][0][1] == {"id": "300514213"}
    assert calls[1][0][0] is GET_AGENTS_USAGE_QUERY
    assert calls[1][0][1]["organizationUuid"] == "341c1327-261c-4766-bb96-7953e4c3970d"
    assert result["agentsUsage"]["totalCredits"] == 5.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_usage_resolves_numeric_organization_id(mock_settings):
    resolve_payload = {"organization": {"uuid": "341c1327-261c-4766-bb96-7953e4c3970d"}}
    usage_payload = {
        "automationsUsage": {
            "data": [{"automationName": "Rule 1", "totalExecutions": 42}],
            "totalExecutions": 42,
        }
    }
    service = ObservabilityService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=[resolve_payload, usage_payload])
    filter_date = {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"}
    result = await service.get_automations_usage("300514213", filter_date)

    assert service.execute_query.call_count == 2
    calls = service.execute_query.call_args_list
    assert calls[0][0][0] is RESOLVE_ORGANIZATION_UUID_QUERY
    assert calls[0][0][1] == {"id": "300514213"}
    assert calls[1][0][0] is GET_AUTOMATIONS_USAGE_QUERY
    assert calls[1][0][1]["organizationUuid"] == "341c1327-261c-4766-bb96-7953e4c3970d"
    assert result["automationsUsage"]["totalExecutions"] == 42
