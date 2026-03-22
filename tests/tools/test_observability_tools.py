"""Tests for observability MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.observability_tools import ObservabilityTools


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_observability_client():
    client = MagicMock(PipefyClient)
    client.get_ai_agent_logs = AsyncMock()
    client.get_ai_agent_log_details = AsyncMock()
    client.get_automation_logs = AsyncMock()
    client.get_automation_logs_by_repo = AsyncMock()
    client.get_agents_usage = AsyncMock()
    client.get_automations_usage = AsyncMock()
    client.get_ai_credit_usage = AsyncMock()
    client.export_automation_jobs = AsyncMock()
    return client


@pytest.fixture
def observability_mcp_server(mock_observability_client):
    mcp = FastMCP("Observability Tools Test")
    ObservabilityTools.register(mcp, mock_observability_client)
    return mcp


@pytest.fixture
def observability_session(observability_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        observability_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


# --- get_ai_agent_logs ---


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_agent_logs_success(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_ai_agent_logs.return_value = {
        "aiAgentLogsByRepo": {
            "nodes": [
                {
                    "uuid": "log-1",
                    "agentUuid": "agent-1",
                    "agentName": "Agent",
                    "automationId": "a1",
                    "automationName": "Rule",
                    "cardId": "100",
                    "cardTitle": "Card",
                    "status": "success",
                    "createdAt": "2026-03-01T00:00:00Z",
                    "updatedAt": "2026-03-01T00:01:00Z",
                },
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "totalCount": 1,
        }
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_agent_logs", {"repo_uuid": "repo-1"}
        )

    assert result.isError is False
    mock_observability_client.get_ai_agent_logs.assert_awaited_once_with(
        "repo-1", first=30, after=None, status=None, search_term=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["aiAgentLogsByRepo"]["totalCount"] == 1


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_agent_logs_graphql_error(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_ai_agent_logs.side_effect = TransportQueryError(
        "failed", errors=[{"message": "not authorized"}]
    )

    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_agent_logs", {"repo_uuid": "repo-bad"}
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not authorized" in payload["error"]


# --- get_ai_agent_log_details ---


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_agent_log_details_success(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_ai_agent_log_details.return_value = {
        "aiAgentLogDetails": {
            "uuid": "log-1",
            "agentUuid": "agent-1",
            "agentName": "Agent",
            "automation": {"id": "a1", "name": "Rule"},
            "cardId": "100",
            "cardTitle": "Card",
            "status": "success",
            "executionTime": 5.2,
            "createdAt": "2026-03-01T00:00:00Z",
            "finishedAt": "2026-03-01T00:00:05Z",
            "tracingNodes": [
                {"nodeName": "Step1", "status": "success", "message": "OK"},
            ],
        }
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_agent_log_details", {"log_uuid": "log-1"}
        )

    assert result.isError is False
    mock_observability_client.get_ai_agent_log_details.assert_awaited_once_with("log-1")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["aiAgentLogDetails"]["executionTime"] == 5.2


# --- get_automation_logs ---


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_logs_success(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_automation_logs.return_value = {
        "automationLogs": {
            "nodes": [
                {
                    "uuid": "alog-1",
                    "automationId": "auto-1",
                    "automationName": "Auto",
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

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_logs", {"automation_id": "auto-1"}
        )

    assert result.isError is False
    mock_observability_client.get_automation_logs.assert_awaited_once_with(
        "auto-1", first=30, after=None, status=None, search_term=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["automationLogs"]["totalCount"] == 1


# --- get_automation_logs_by_repo ---


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_logs_by_repo_success(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_automation_logs_by_repo.return_value = {
        "automationLogsByRepo": {
            "nodes": [
                {
                    "uuid": "alog-2",
                    "automationId": "auto-2",
                    "automationName": "Auto 2",
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

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_logs_by_repo", {"repo_id": "repo-5"}
        )

    assert result.isError is False
    mock_observability_client.get_automation_logs_by_repo.assert_awaited_once_with(
        "repo-5", first=30, after=None, status=None, search_term=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["automationLogsByRepo"]["totalCount"] == 15


# --- readOnlyHint on all 4 log tools ---


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_log_tools_have_read_only_hint(observability_session):
    async with observability_session as session:
        listed = await session.list_tools()

    log_tool_names = {
        "get_ai_agent_logs",
        "get_ai_agent_log_details",
        "get_automation_logs",
        "get_automation_logs_by_repo",
    }
    for tool in listed.tools:
        if tool.name in log_tool_names:
            assert tool.annotations is not None, f"{tool.name} missing annotations"
            assert tool.annotations.readOnlyHint is True, f"{tool.name} not read-only"


# --- get_agents_usage ---


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_agents_usage_success(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_agents_usage.return_value = {
        "agentsUsageDetails": {
            "usage": 42.5,
            "agents": {
                "nodes": [{"id": "a1", "name": "Agent", "usage": 20.0}],
                "totalCount": 3,
                "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
            },
        }
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_agents_usage",
            {
                "organization_uuid": "org-1",
                "filter_date_from": "2026-03-01T00:00:00Z",
                "filter_date_to": "2026-03-31T23:59:59Z",
            },
        )

    assert result.isError is False
    mock_observability_client.get_agents_usage.assert_awaited_once_with(
        "org-1",
        {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"},
        filters=None,
        search=None,
        sort=None,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["agentsUsageDetails"]["usage"] == 42.5


# --- get_automations_usage ---


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automations_usage_success(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_automations_usage.return_value = {
        "automationsUsageDetails": {
            "usage": 500,
            "automations": {
                "nodes": [{"id": "r1", "name": "Rule", "usage": 100}],
                "totalCount": 5,
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            },
        }
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_automations_usage",
            {
                "organization_uuid": "org-1",
                "filter_date_from": "2026-03-01T00:00:00Z",
                "filter_date_to": "2026-03-31T23:59:59Z",
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["automationsUsageDetails"]["usage"] == 500


# --- get_ai_credit_usage ---


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_credit_usage_success(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_ai_credit_usage.return_value = {
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

    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_credit_usage",
            {"organization_uuid": "org-1", "period": "current_month"},
        )

    assert result.isError is False
    mock_observability_client.get_ai_credit_usage.assert_awaited_once_with(
        "org-1", "current_month"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["aiCreditUsageStats"]["usage"] == 150.0


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_credit_usage_graphql_error(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_ai_credit_usage.side_effect = TransportQueryError(
        "failed", errors=[{"message": "forbidden"}]
    )

    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_credit_usage",
            {"organization_uuid": "org-bad", "period": "current_month"},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "forbidden" in payload["error"]


# --- export_automation_jobs ---


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_export_automation_jobs_success(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.export_automation_jobs.return_value = {
        "createAutomationJobsExport": {
            "automationJobsExport": {
                "id": "exp-1",
                "status": "processing",
                "fileUrl": None,
            }
        }
    }

    async with observability_session as session:
        result = await session.call_tool(
            "export_automation_jobs",
            {"organization_id": "org-123", "period": "last_month"},
        )

    assert result.isError is False
    mock_observability_client.export_automation_jobs.assert_awaited_once_with(
        "org-123", "last_month"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["createAutomationJobsExport"]["automationJobsExport"]["id"] == "exp-1"


# --- readOnlyHint on usage tools, not on export ---


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_usage_tools_have_read_only_hint(observability_session):
    async with observability_session as session:
        listed = await session.list_tools()

    read_only_names = {
        "get_agents_usage",
        "get_automations_usage",
        "get_ai_credit_usage",
    }
    for tool in listed.tools:
        if tool.name in read_only_names:
            assert tool.annotations is not None, f"{tool.name} missing annotations"
            assert tool.annotations.readOnlyHint is True, f"{tool.name} not read-only"


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_export_tool_not_read_only(observability_session):
    async with observability_session as session:
        listed = await session.list_tools()

    export_tool = next(t for t in listed.tools if t.name == "export_automation_jobs")
    assert export_tool.annotations is not None
    assert export_tool.annotations.readOnlyHint is False
