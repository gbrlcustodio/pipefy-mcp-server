"""Unit tests for ObservabilityService (logs, usage, and export)."""

from unittest.mock import AsyncMock

import pytest
from gql.transport.exceptions import TransportQueryError

from pipefy_mcp.services.pipefy.observability_service import ObservabilityService
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
from pipefy_mcp.settings import PipefySettings


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


# --- AI Agent Logs ---


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
    await service.get_ai_agent_logs(
        "repo-uuid-1", status="failed", search_term="error"
    )

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


# --- Automation Logs ---


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
    result = await service.get_automation_logs_by_repo("repo-5", first=10, after="cur-0")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AUTOMATION_LOGS_BY_REPO_QUERY
    assert variables == {"repoId": "repo-5", "first": 10, "after": "cur-0"}
    assert result["automationLogsByRepo"]["totalCount"] == 15


# --- Sad path ---


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_ai_agent_logs_transport_error(mock_settings):
    service = ObservabilityService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_ai_agent_logs("repo-uuid-1")


# --- Usage Queries ---


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
    result = await service.get_agents_usage("org-uuid-1", filter_date)

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AGENTS_USAGE_QUERY
    assert variables == {"organizationUuid": "org-uuid-1", "filterDate": filter_date}
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
        "org-uuid-1", filter_date, search="Rule"
    )

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AUTOMATIONS_USAGE_QUERY
    assert variables["organizationUuid"] == "org-uuid-1"
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
    result = await service.get_ai_credit_usage("org-uuid-1", "current_month")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AI_CREDIT_USAGE_QUERY
    assert variables == {"organizationUuid": "org-uuid-1", "period": "current_month"}
    assert result["aiCreditUsageStats"]["usage"] == 150.0


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
    result = await service.export_automation_jobs("org-123", "last_month")

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_AUTOMATION_JOBS_EXPORT_MUTATION
    assert variables == {
        "input": {"organizationId": "org-123", "period": "last_month"}
    }
    assert result["createAutomationJobsExport"]["automationJobsExport"]["id"] == "exp-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agents_usage_transport_error(mock_settings):
    service = ObservabilityService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "forbidden"}])
    )
    filter_date = {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"}
    with pytest.raises(TransportQueryError):
        await service.get_agents_usage("org-uuid-1", filter_date)
