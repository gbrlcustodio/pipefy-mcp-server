"""Tests for observability MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from _mcp_compat import (
    create_connected_server_and_client_session as create_client_session,
)
from _shared.fixture_ids import EXAMPLE_NUMERIC_ORG_ID
from pipefy_sdk import PipefyClient, PipefyGraphQLError

from pipefy_mcp.core.tool_error_envelope import tool_error_message
from pipefy_mcp.tools.observability_tools import _MAX_PAGE_SIZE, ObservabilityTools
from tools.conftest import (
    assert_invalid_arguments_envelope,
    build_tool_test_server,
)


@pytest.fixture
def mock_observability_client():
    client = MagicMock(PipefyClient)
    client.get_ai_agent_logs = AsyncMock()
    client.get_ai_agent_log_details = AsyncMock()
    client.get_automation_logs = AsyncMock()
    client.get_automation_logs_by_repo = AsyncMock()
    client.get_agents_usage = AsyncMock()
    client.get_automations_usage = AsyncMock()
    client.get_automation_execution_metrics = AsyncMock()
    client.get_ai_credit_usage = AsyncMock()
    client.export_automation_jobs = AsyncMock()
    client.get_automation_jobs_export = AsyncMock()
    client.get_automation_jobs_export_csv = AsyncMock()
    return client


@pytest.fixture
def observability_mcp_server(mock_observability_client):
    return build_tool_test_server(
        "Observability Tools Test",
        ObservabilityTools.register,
        mock_observability_client,
    )


@pytest.fixture
def observability_session(observability_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        observability_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


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
        result = await session.call_tool("get_ai_agent_logs", {"repo_uuid": "repo-1"})

    assert result.is_error is False
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
    mock_observability_client.get_ai_agent_logs.side_effect = PipefyGraphQLError(
        [{"message": "not authorized"}]
    )

    async with observability_session as session:
        result = await session.call_tool("get_ai_agent_logs", {"repo_uuid": "repo-bad"})

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not authorized" in tool_error_message(payload)


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

    assert result.is_error is False
    mock_observability_client.get_ai_agent_log_details.assert_awaited_once_with("log-1")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["aiAgentLogDetails"]["executionTime"] == 5.2


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

    assert result.is_error is False
    mock_observability_client.get_automation_logs.assert_awaited_once_with(
        "auto-1", first=30, after=None, status=None, search_term=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["automationLogs"]["totalCount"] == 1


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

    assert result.is_error is False
    mock_observability_client.get_automation_logs_by_repo.assert_awaited_once_with(
        "repo-5", first=30, after=None, status=None, search_term=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["automationLogsByRepo"]["totalCount"] == 15


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
            assert tool.annotations.read_only_hint is True, f"{tool.name} not read-only"


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

    assert result.is_error is False
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

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["automationsUsageDetails"]["usage"] == 500


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_execution_metrics_partial_success(
    observability_session, mock_observability_client, extract_payload
):
    """Permitted automations + denied ids both surface; defaults applied."""
    mock_observability_client.get_automation_execution_metrics.return_value = {
        "automations": [
            {
                "id": "25",
                "name": "Loop 51",
                "executionMetrics": {
                    "lastRun": None,
                    "failureRate": 0.0,
                    "successRate": 0.0,
                    "averageDuration": None,
                    "totalRuns": 0,
                },
            }
        ],
        "partial_errors": [
            {
                "automation_id": "124",
                "code": "PERMISSION_DENIED",
                "message": "Permission denied",
                "correlation_id": "c86ccfa6",
            }
        ],
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_execution_metrics",
            {"organization_id": "3", "automation_ids": ["25", "124"], "repo_id": "16"},
        )

    assert result.is_error is False
    mock_observability_client.get_automation_execution_metrics.assert_awaited_once_with(
        "3",
        ["25", "124"],
        repo_id="16",
        action_ids=None,
        event_id=None,
        active=None,
        search=None,
        sort_by=None,
        sort_order=None,
        period="SIXTY_MINUTES",
        first=50,
        after=None,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert [a["id"] for a in payload["data"]["automations"]] == ["25"]
    assert payload["data"]["partial_errors"][0]["automation_id"] == "124"


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_execution_metrics_without_ids_fetches_all(
    observability_session, mock_observability_client, extract_payload
):
    """Omitting automation_ids fetches every automation in the org (ids passed as None)."""
    mock_observability_client.get_automation_execution_metrics.return_value = {
        "automations": [],
        "partial_errors": [],
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_execution_metrics",
            {"organization_id": "3"},
        )

    assert result.is_error is False
    mock_observability_client.get_automation_execution_metrics.assert_awaited_once_with(
        "3",
        None,
        repo_id=None,
        action_ids=None,
        event_id=None,
        active=None,
        search=None,
        sort_by=None,
        sort_order=None,
        period="SIXTY_MINUTES",
        first=50,
        after=None,
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_execution_metrics_rejects_invalid_period(
    observability_session, mock_observability_client, extract_payload
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_execution_metrics",
            {
                "organization_id": "3",
                "automation_ids": ["25"],
                "period": "current_month",
            },
        )

    assert result.is_error is False
    p = extract_payload(result)
    assert p["success"] is False
    assert "period" in tool_error_message(p)
    mock_observability_client.get_automation_execution_metrics.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_execution_metrics_rejects_empty_ids(
    observability_session, mock_observability_client, extract_payload
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_execution_metrics",
            {"organization_id": "3", "automation_ids": []},
        )

    assert result.is_error is False
    p = extract_payload(result)
    assert p["success"] is False
    assert "automation_ids" in tool_error_message(p)
    mock_observability_client.get_automation_execution_metrics.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_execution_metrics_rejects_first_over_cap(
    observability_session, mock_observability_client, extract_payload
):
    """first above the server's 50-per-page cap is rejected before any API call."""
    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_execution_metrics",
            {"organization_id": "3", "first": 51},
        )

    assert result.is_error is False
    p = extract_payload(result)
    assert p["success"] is False
    assert "first" in tool_error_message(p)
    mock_observability_client.get_automation_execution_metrics.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_execution_metrics_forwards_pagination(
    observability_session, mock_observability_client, extract_payload
):
    """first and after reach the client; page_info rides back in the payload."""
    mock_observability_client.get_automation_execution_metrics.return_value = {
        "automations": [],
        "partial_errors": [],
        "page_info": {"hasNextPage": True, "endCursor": "cur-1"},
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_execution_metrics",
            {"organization_id": "3", "first": 50, "after": "cur-0"},
        )

    assert result.is_error is False
    mock_observability_client.get_automation_execution_metrics.assert_awaited_once_with(
        "3",
        None,
        repo_id=None,
        action_ids=None,
        event_id=None,
        active=None,
        search=None,
        sort_by=None,
        sort_order=None,
        period="SIXTY_MINUTES",
        first=50,
        after="cur-0",
    )
    payload = extract_payload(result)
    assert payload["data"]["page_info"] == {"hasNextPage": True, "endCursor": "cur-1"}


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_execution_metrics_forwards_filters(
    observability_session, mock_observability_client, extract_payload
):
    """All filter params reach the client; search is stripped."""
    mock_observability_client.get_automation_execution_metrics.return_value = {
        "automations": [],
        "partial_errors": [],
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_execution_metrics",
            {
                "organization_id": "3",
                "action_ids": ["9", "10"],
                "event_id": "card_moved",
                "active": True,
                "search": "  welcome  ",
                "sort_by": "name",
                "sort_order": "asc",
            },
        )

    assert result.is_error is False
    mock_observability_client.get_automation_execution_metrics.assert_awaited_once_with(
        "3",
        None,
        repo_id=None,
        action_ids=["9", "10"],
        event_id="card_moved",
        active=True,
        search="welcome",
        sort_by="name",
        sort_order="asc",
        period="SIXTY_MINUTES",
        first=50,
        after=None,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
@pytest.mark.parametrize(
    ("arg", "value"),
    [
        ("event_id", "bogus_event"),
        ("sort_by", "priority"),
        ("sort_order", "descending"),
    ],
)
async def test_get_automation_execution_metrics_rejects_invalid_enum(
    observability_session, mock_observability_client, extract_payload, arg, value
):
    """Invalid enum-valued filters are rejected before any API call."""
    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_execution_metrics",
            {"organization_id": "3", arg: value},
        )

    assert result.is_error is False
    p = extract_payload(result)
    assert p["success"] is False
    assert arg in tool_error_message(p)
    mock_observability_client.get_automation_execution_metrics.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_execution_metrics_rejects_empty_action_ids(
    observability_session, mock_observability_client, extract_payload
):
    """A present-but-empty action_ids list is rejected like automation_ids."""
    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_execution_metrics",
            {"organization_id": "3", "action_ids": []},
        )

    assert result.is_error is False
    p = extract_payload(result)
    assert p["success"] is False
    assert "action_ids" in tool_error_message(p)
    mock_observability_client.get_automation_execution_metrics.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_execution_metrics_value_error_from_client(
    observability_session, mock_observability_client, extract_payload
):
    """A total failure (SDK raises ValueError) comes back as a plain error envelope."""
    mock_observability_client.get_automation_execution_metrics.side_effect = ValueError(
        "Couldn't find Organization with 'id'=999"
    )

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_execution_metrics",
            {"organization_id": "999"},
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Couldn't find Organization" in tool_error_message(payload)


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

    assert result.is_error is False
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
    mock_observability_client.get_ai_credit_usage.side_effect = PipefyGraphQLError(
        [{"message": "forbidden"}]
    )

    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_credit_usage",
            {"organization_uuid": "org-bad", "period": "current_month"},
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "forbidden" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_credit_usage_value_error_from_client(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_ai_credit_usage.side_effect = ValueError(
        "Organization not found or has no uuid for id: 999"
    )

    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_credit_usage",
            {"organization_uuid": "999", "period": "current_month"},
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Organization not found" in tool_error_message(payload)


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

    assert result.is_error is False
    mock_observability_client.export_automation_jobs.assert_awaited_once_with(
        "org-123", "last_month"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert (
        payload["result"]["createAutomationJobsExport"]["automationJobsExport"]["id"]
        == "exp-1"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_jobs_export_success(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_automation_jobs_export.return_value = {
        "automationJobsExport": {
            "id": "25820",
            "status": "finished",
            "fileUrl": "https://app.pipefy.com/storage/signed/example.xlsx",
        }
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_jobs_export",
            {"export_id": "25820"},
        )

    assert result.is_error is False
    mock_observability_client.get_automation_jobs_export.assert_awaited_once_with(
        "25820"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["automationJobsExport"]["status"] == "finished"
    assert payload["data"]["automationJobsExport"]["fileUrl"].endswith(".xlsx")


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_jobs_export_graphql_error(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_automation_jobs_export.side_effect = (
        PipefyGraphQLError([{"message": "not found"}])
    )

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_jobs_export",
            {"export_id": "999"},
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_jobs_export_rejects_empty_export_id(
    observability_session, mock_observability_client
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_jobs_export",
            {"export_id": ""},
        )

    mock_observability_client.get_automation_jobs_export.assert_not_called()
    assert_invalid_arguments_envelope(result)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_jobs_export_coerces_int_export_id(
    observability_session, mock_observability_client, extract_payload
):
    """mcporter CLI sends numeric IDs as int; PipefyId must coerce to str."""
    mock_observability_client.get_automation_jobs_export.return_value = {
        "automationJobsExport": {
            "id": "25901",
            "status": "finished",
            "fileUrl": "https://app.pipefy.com/storage/signed/export.xlsx",
        }
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_jobs_export",
            {"export_id": 25901},
        )

    assert result.is_error is False
    mock_observability_client.get_automation_jobs_export.assert_awaited_once_with(
        "25901"
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_jobs_export_csv_coerces_int_export_id(
    observability_session, mock_observability_client, extract_payload
):
    """mcporter CLI sends numeric IDs as int; PipefyId must coerce to str."""
    mock_observability_client.get_automation_jobs_export_csv.return_value = {
        "export_id": "25901",
        "status": "finished",
        "csv_text": "col1,col2\na,b\n",
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_jobs_export_csv",
            {"export_id": 25901},
        )

    assert result.is_error is False
    mock_observability_client.get_automation_jobs_export_csv.assert_awaited_once_with(
        "25901",
        max_output_chars=400_000,
        max_download_bytes=50 * 1024 * 1024,
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_logs_coerces_int_automation_id(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_automation_logs.return_value = {
        "automationExecutions": {
            "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_logs",
            {"automation_id": 42},
        )

    assert result.is_error is False
    mock_observability_client.get_automation_logs.assert_awaited_once_with(
        "42", first=30, after=None, status=None, search_term=None
    )


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
            assert tool.annotations.read_only_hint is True, f"{tool.name} not read-only"


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_export_tool_not_read_only(observability_session):
    async with observability_session as session:
        listed = await session.list_tools()

    export_tool = next(t for t in listed.tools if t.name == "export_automation_jobs")
    assert export_tool.annotations is not None
    assert export_tool.annotations.read_only_hint is False


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_jobs_export_read_only_hint(observability_session):
    async with observability_session as session:
        listed = await session.list_tools()

    tool = next(t for t in listed.tools if t.name == "get_automation_jobs_export")
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_jobs_export_csv_success(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_automation_jobs_export_csv.return_value = {
        "export_id": "1",
        "status": "finished",
        "sheet_name": "Sheet",
        "row_count": 2,
        "csv_truncated": False,
        "max_output_chars": 400_000,
        "csv": "a,b\n1,2\n",
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_jobs_export_csv",
            {"export_id": "1"},
        )

    assert result.is_error is False
    mock_observability_client.get_automation_jobs_export_csv.assert_awaited_once_with(
        "1", max_output_chars=400_000, max_download_bytes=50 * 1024 * 1024
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "1,2" in payload["data"]["csv"]


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_jobs_export_csv_value_error(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_automation_jobs_export_csv.side_effect = ValueError(
        "Export status is 'processing'"
    )

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_jobs_export_csv",
            {"export_id": "1"},
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "processing" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_jobs_export_csv_rejects_bad_max_chars(
    observability_session, mock_observability_client, extract_payload
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_jobs_export_csv",
            {"export_id": "1", "max_output_chars": 10},
        )

    mock_observability_client.get_automation_jobs_export_csv.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "max_output_chars" in tool_error_message(p)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_jobs_export_csv_read_only_hint(observability_session):
    async with observability_session as session:
        listed = await session.list_tools()

    tool = next(t for t in listed.tools if t.name == "get_automation_jobs_export_csv")
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_agent_logs_rejects_invalid_repo_uuid(
    observability_session, mock_observability_client, extract_payload
):
    async with observability_session as session:
        result = await session.call_tool("get_ai_agent_logs", {"repo_uuid": ""})

    mock_observability_client.get_ai_agent_logs.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "repo_uuid" in tool_error_message(p)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_agent_log_details_rejects_invalid_log_uuid(
    observability_session, mock_observability_client, extract_payload
):
    async with observability_session as session:
        result = await session.call_tool("get_ai_agent_log_details", {"log_uuid": ""})

    mock_observability_client.get_ai_agent_log_details.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "log_uuid" in tool_error_message(p)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_credit_usage_rejects_invalid_period(
    observability_session, mock_observability_client, extract_payload
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_credit_usage",
            {"organization_uuid": "org-1", "period": "invalid_period"},
        )

    mock_observability_client.get_ai_credit_usage.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "period" in tool_error_message(p)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_agents_usage_rejects_empty_org_uuid(
    observability_session, mock_observability_client
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_agents_usage",
            {
                "organization_uuid": "",
                "filter_date_from": "2026-03-01T00:00:00Z",
                "filter_date_to": "2026-03-31T23:59:59Z",
            },
        )

    mock_observability_client.get_agents_usage.assert_not_called()
    assert_invalid_arguments_envelope(result)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_agents_usage_rejects_missing_dates(
    observability_session, mock_observability_client, extract_payload
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_agents_usage",
            {
                "organization_uuid": "org-1",
                "filter_date_from": "",
                "filter_date_to": "2026-03-31T23:59:59Z",
            },
        )

    mock_observability_client.get_agents_usage.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "filter_date" in tool_error_message(p).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
@pytest.mark.parametrize("bad_first", [0, -1, _MAX_PAGE_SIZE + 1])
async def test_get_ai_agent_logs_rejects_out_of_bounds_first(
    observability_session, mock_observability_client, extract_payload, bad_first
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_agent_logs", {"repo_uuid": "repo-1", "first": bad_first}
        )

    mock_observability_client.get_ai_agent_logs.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "first" in tool_error_message(p).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_agent_logs_debug_true_appends_codes(
    observability_session, mock_observability_client, extract_payload
):
    error = PipefyGraphQLError(
        [
            {
                "message": "not authorized",
                "extensions": {"code": "PERMISSION_DENIED"},
            }
        ]
    )
    mock_observability_client.get_ai_agent_logs.side_effect = error

    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_agent_logs", {"repo_uuid": "repo-1", "debug": True}
        )

    assert result.is_error is False
    p = extract_payload(result)
    assert p["success"] is False
    # The ambiguity enricher rewrote the raw "not authorized" into a
    # dual-meaning message; the debug suffix still carries the code + correlation.
    msg = tool_error_message(p)
    assert "may lack access" in msg
    assert "codes=" in msg or "correlation_id=" in msg
    assert "PERMISSION_DENIED" in msg


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_credit_usage_debug_true_appends_codes(
    observability_session, mock_observability_client, extract_payload
):
    error = PipefyGraphQLError(
        [
            {
                "message": "forbidden",
                "extensions": {"code": "FORBIDDEN"},
            }
        ]
    )
    mock_observability_client.get_ai_credit_usage.side_effect = error

    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_credit_usage",
            {"organization_uuid": "org-1", "period": "current_month", "debug": True},
        )

    assert result.is_error is False
    p = extract_payload(result)
    assert p["success"] is False
    assert "forbidden" in tool_error_message(p)
    assert "FORBIDDEN" in tool_error_message(p)


# --- Int-to-str coercion tests ---


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_export_automation_jobs_coerces_int_organization_id(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.export_automation_jobs.return_value = {
        "createAutomationJobsExport": {
            "automationJobsExport": {"id": "exp-1", "status": "processing"}
        }
    }

    async with observability_session as session:
        result = await session.call_tool(
            "export_automation_jobs",
            {"organization_id": int(EXAMPLE_NUMERIC_ORG_ID), "period": "last_month"},
        )

    assert result.is_error is False
    mock_observability_client.export_automation_jobs.assert_awaited_once_with(
        EXAMPLE_NUMERIC_ORG_ID, "last_month"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_agents_usage_coerces_int_organization_uuid(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_agents_usage.return_value = {
        "agentsUsageDetails": {"usage": 0, "agents": {"nodes": [], "totalCount": 0}}
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_agents_usage",
            {
                "organization_uuid": int(EXAMPLE_NUMERIC_ORG_ID),
                "filter_date_from": "2026-03-01T00:00:00Z",
                "filter_date_to": "2026-03-31T23:59:59Z",
            },
        )

    assert result.is_error is False
    mock_observability_client.get_agents_usage.assert_awaited_once_with(
        EXAMPLE_NUMERIC_ORG_ID,
        {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"},
        filters=None,
        search=None,
        sort=None,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automations_usage_coerces_int_organization_uuid(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_automations_usage.return_value = {
        "automationsUsageDetails": {
            "usage": 0,
            "automations": {"nodes": [], "totalCount": 0},
        }
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_automations_usage",
            {
                "organization_uuid": int(EXAMPLE_NUMERIC_ORG_ID),
                "filter_date_from": "2026-03-01T00:00:00Z",
                "filter_date_to": "2026-03-31T23:59:59Z",
            },
        )

    assert result.is_error is False
    mock_observability_client.get_automations_usage.assert_awaited_once_with(
        EXAMPLE_NUMERIC_ORG_ID,
        {"from": "2026-03-01T00:00:00Z", "to": "2026-03-31T23:59:59Z"},
        filters=None,
        search=None,
        sort=None,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_credit_usage_coerces_int_organization_uuid(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_ai_credit_usage.return_value = {
        "aiCreditUsage": {"creditLimit": 100, "totalConsumption": 50}
    }

    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_credit_usage",
            {
                "organization_uuid": int(EXAMPLE_NUMERIC_ORG_ID),
                "period": "current_month",
            },
        )

    assert result.is_error is False
    mock_observability_client.get_ai_credit_usage.assert_awaited_once_with(
        EXAMPLE_NUMERIC_ORG_ID, "current_month"
    )


# ---------------------------------------------------------------------------
# get_automation_logs — input validation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_logs_rejects_blank_automation_id(
    observability_session, mock_observability_client
):
    async with observability_session as session:
        result = await session.call_tool("get_automation_logs", {"automation_id": ""})

    mock_observability_client.get_automation_logs.assert_not_called()
    assert_invalid_arguments_envelope(result)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
@pytest.mark.parametrize("bad_first", [0, _MAX_PAGE_SIZE + 1])
async def test_get_automation_logs_rejects_out_of_bounds_first(
    observability_session, mock_observability_client, extract_payload, bad_first
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_logs", {"automation_id": "auto-1", "first": bad_first}
        )

    mock_observability_client.get_automation_logs.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "first" in tool_error_message(p).lower()


# ---------------------------------------------------------------------------
# get_automation_logs_by_repo — input validation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_logs_by_repo_rejects_blank_repo_id(
    observability_session, mock_observability_client
):
    async with observability_session as session:
        result = await session.call_tool("get_automation_logs_by_repo", {"repo_id": ""})

    mock_observability_client.get_automation_logs_by_repo.assert_not_called()
    assert_invalid_arguments_envelope(result)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
@pytest.mark.parametrize("bad_first", [0, _MAX_PAGE_SIZE + 1])
async def test_get_automation_logs_by_repo_rejects_out_of_bounds_first(
    observability_session, mock_observability_client, extract_payload, bad_first
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_logs_by_repo", {"repo_id": "repo-5", "first": bad_first}
        )

    mock_observability_client.get_automation_logs_by_repo.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "first" in tool_error_message(p).lower()


# ---------------------------------------------------------------------------
# get_agents_usage — invalid organization_uuid
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_agents_usage_graphql_error(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_agents_usage.side_effect = PipefyGraphQLError(
        [{"message": "unauthorized"}]
    )

    async with observability_session as session:
        result = await session.call_tool(
            "get_agents_usage",
            {
                "organization_uuid": "org-1",
                "filter_date_from": "2026-03-01T00:00:00Z",
                "filter_date_to": "2026-03-31T23:59:59Z",
            },
        )

    p = extract_payload(result)
    assert p["success"] is False
    assert "unauthorized" in tool_error_message(p)


# ---------------------------------------------------------------------------
# get_automations_usage — invalid organization_uuid + GraphQL error
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automations_usage_rejects_empty_org_uuid(
    observability_session, mock_observability_client
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_automations_usage",
            {
                "organization_uuid": "",
                "filter_date_from": "2026-03-01T00:00:00Z",
                "filter_date_to": "2026-03-31T23:59:59Z",
            },
        )

    mock_observability_client.get_automations_usage.assert_not_called()
    assert_invalid_arguments_envelope(result)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automations_usage_graphql_error(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_automations_usage.side_effect = PipefyGraphQLError(
        [{"message": "service unavailable"}]
    )

    async with observability_session as session:
        result = await session.call_tool(
            "get_automations_usage",
            {
                "organization_uuid": "org-1",
                "filter_date_from": "2026-03-01T00:00:00Z",
                "filter_date_to": "2026-03-31T23:59:59Z",
            },
        )

    p = extract_payload(result)
    assert p["success"] is False
    assert "service unavailable" in tool_error_message(p)


# ---------------------------------------------------------------------------
# get_ai_credit_usage — invalid organization_uuid
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_credit_usage_rejects_empty_org_uuid(
    observability_session, mock_observability_client
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_credit_usage",
            {"organization_uuid": "", "period": "current_month"},
        )

    mock_observability_client.get_ai_credit_usage.assert_not_called()
    assert_invalid_arguments_envelope(result)


# ---------------------------------------------------------------------------
# export_automation_jobs — invalid organization_id + GraphQL error
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_export_automation_jobs_rejects_empty_org_id(
    observability_session, mock_observability_client
):
    async with observability_session as session:
        result = await session.call_tool(
            "export_automation_jobs",
            {"organization_id": "", "period": "last_month"},
        )

    mock_observability_client.export_automation_jobs.assert_not_called()
    assert_invalid_arguments_envelope(result)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_export_automation_jobs_rejects_invalid_period(
    observability_session, mock_observability_client, extract_payload
):
    async with observability_session as session:
        result = await session.call_tool(
            "export_automation_jobs",
            {"organization_id": "org-1", "period": "all_time"},
        )

    mock_observability_client.export_automation_jobs.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "period" in tool_error_message(p)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_export_automation_jobs_graphql_error(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.export_automation_jobs.side_effect = PipefyGraphQLError(
        [{"message": "rate limited"}]
    )

    async with observability_session as session:
        result = await session.call_tool(
            "export_automation_jobs",
            {"organization_id": "org-1", "period": "last_month"},
        )

    p = extract_payload(result)
    assert p["success"] is False
    assert "rate limited" in tool_error_message(p)


# ---------------------------------------------------------------------------
# get_ai_agent_log_details — GraphQL error
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_agent_log_details_graphql_error(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_ai_agent_log_details.side_effect = PipefyGraphQLError(
        [{"message": "log not found"}]
    )

    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_agent_log_details", {"log_uuid": "bad-uuid"}
        )

    p = extract_payload(result)
    assert p["success"] is False
    assert "Ai agent log not found" in tool_error_message(p)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_ai_agent_log_details_rewrites_automationaction_not_found(
    observability_session, mock_observability_client, extract_payload
):
    """The upstream resolver leaks its internal type (``AutomationAction``) when
    the UUID isn't found; the tool rewrites to tool-level semantics."""
    mock_observability_client.get_ai_agent_log_details.side_effect = PipefyGraphQLError(
        [
            {
                "message": (
                    "Couldn't find AutomationAction with 'id'="
                    "00000000-0000-0000-0000-000000000000"
                )
            }
        ]
    )
    async with observability_session as session:
        result = await session.call_tool(
            "get_ai_agent_log_details",
            {"log_uuid": "00000000-0000-0000-0000-000000000000"},
        )
    p = extract_payload(result)
    assert p["success"] is False
    msg = tool_error_message(p)
    assert "AutomationAction" not in msg
    assert "AI agent log not found" in msg
    assert "00000000-0000-0000-0000-000000000000" in msg


# ---------------------------------------------------------------------------
# get_automation_logs — GraphQL error
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_logs_graphql_error(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_automation_logs.side_effect = PipefyGraphQLError(
        [{"message": "internal error"}]
    )

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_logs", {"automation_id": "auto-1"}
        )

    p = extract_payload(result)
    assert p["success"] is False
    assert "internal error" in tool_error_message(p)


# ---------------------------------------------------------------------------
# get_automation_logs_by_repo — GraphQL error
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_logs_by_repo_graphql_error(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_automation_logs_by_repo.side_effect = (
        PipefyGraphQLError([{"message": "timeout"}])
    )

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_logs_by_repo", {"repo_id": "repo-5"}
        )

    p = extract_payload(result)
    assert p["success"] is False
    assert "timeout" in tool_error_message(p)


# ---------------------------------------------------------------------------
# get_automation_jobs_export_csv — invalid limits + GraphQL error
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_jobs_export_csv_rejects_bad_max_download_bytes(
    observability_session, mock_observability_client, extract_payload
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_jobs_export_csv",
            {"export_id": "1", "max_download_bytes": 10},
        )

    mock_observability_client.get_automation_jobs_export_csv.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "max_download_bytes" in tool_error_message(p)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_jobs_export_csv_graphql_error(
    observability_session, mock_observability_client, extract_payload
):
    mock_observability_client.get_automation_jobs_export_csv.side_effect = Exception(
        "network failure"
    )

    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_jobs_export_csv",
            {"export_id": "1"},
        )

    p = extract_payload(result)
    assert p["success"] is False
    assert "CSV failed" in tool_error_message(
        p
    ) or "network failure" in tool_error_message(p)


@pytest.mark.anyio
@pytest.mark.parametrize("observability_session", [None], indirect=True)
async def test_get_automation_jobs_export_csv_rejects_empty_export_id(
    observability_session, mock_observability_client
):
    async with observability_session as session:
        result = await session.call_tool(
            "get_automation_jobs_export_csv",
            {"export_id": ""},
        )

    mock_observability_client.get_automation_jobs_export_csv.assert_not_called()
    assert_invalid_arguments_envelope(result)
