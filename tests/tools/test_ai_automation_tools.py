"""Tests for AI Automation MCP tools."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.ai_automation_tools import AiAutomationTools
from pipefy_mcp.tools.tool_error_envelope import tool_error_message
from tests.tools.conftest import assert_invalid_arguments_envelope


@pytest.fixture
def mock_pipefy_client():
    client = MagicMock(spec=PipefyClient)
    client.create_ai_automation = AsyncMock()
    client.update_ai_automation = AsyncMock()
    client.get_automation = AsyncMock()
    client.get_automations = AsyncMock()
    client.delete_automation = AsyncMock()
    client.get_pipe_with_preferences = AsyncMock()
    client.get_automation_events = AsyncMock()
    client.get_ai_credit_usage = AsyncMock()
    client.ai_automation_available = True
    return client


@pytest.fixture
def mock_pipefy_client_no_ai():
    """Client where AI automation is not configured (no OAuth credentials)."""
    client = MagicMock(spec=PipefyClient)
    client.get_automation = AsyncMock()
    client.get_automations = AsyncMock()
    client.delete_automation = AsyncMock()
    client.ai_automation_available = False
    return client


@pytest.fixture
def mcp_server(mock_pipefy_client):
    mcp = FastMCP("AI Automation Tools Test")
    AiAutomationTools.register(mcp, mock_pipefy_client)
    return mcp


@pytest.fixture
def mcp_server_no_ai(mock_pipefy_client_no_ai):
    mcp = FastMCP("AI Automation Tools Test (no AI)")
    AiAutomationTools.register(mcp, mock_pipefy_client_no_ai)
    return mcp


@pytest.fixture
def client_session(mcp_server):
    return create_client_session(
        mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )


@pytest.fixture
def client_session_no_ai(mcp_server_no_ai):
    return create_client_session(
        mcp_server_no_ai,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )


@pytest.mark.anyio
class TestGetAiAutomation:
    async def test_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_automation.return_value = {
            "id": "501",
            "name": "AI rule",
            "action_id": "generate_with_ai",
            "action_params": {"aiParams": {"value": "Hello", "fieldIds": ["1"]}},
        }
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automation",
                {"automation_id": "501"},
            )
        assert result.isError is False
        mock_pipefy_client.get_automation.assert_awaited_once_with("501")
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["data"] == mock_pipefy_client.get_automation.return_value
        assert "AI automation retrieved" in payload["message"]

    async def test_graphql_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_automation.side_effect = TransportQueryError(
            "failed", errors=[{"message": "boom"}]
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automation",
                {"automation_id": "x"},
            )
        assert result.isError is False
        p = extract_payload(result)
        assert p["success"] is False
        assert "boom" in tool_error_message(p)

    async def test_not_found_empty_data(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_automation.return_value = {}
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automation",
                {"automation_id": "999"},
            )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["data"] == {}
        assert "No automation found" in payload["message"]

    async def test_rejects_empty_automation_id(
        self,
        client_session,
        mock_pipefy_client,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automation",
                {"automation_id": ""},
            )
        mock_pipefy_client.get_automation.assert_not_called()
        assert_invalid_arguments_envelope(result)

    async def test_rejects_non_positive_int_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automation",
                {"automation_id": -1},
            )
        mock_pipefy_client.get_automation.assert_not_called()
        assert extract_payload(result)["success"] is False

    async def test_debug_true_includes_codes_on_graphql_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        err = TransportQueryError(
            "failed",
            errors=[{"message": "nope", "extensions": {"code": "GONE"}}],
        )
        mock_pipefy_client.get_automation.side_effect = err
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automation",
                {"automation_id": "1", "debug": True},
            )
        p = extract_payload(result)
        assert p["success"] is False
        assert "nope" in tool_error_message(p)

    async def test_succeeds_when_oauth_not_configured_public_query(
        self,
        client_session_no_ai,
        mock_pipefy_client_no_ai,
        extract_payload,
    ):
        mock_pipefy_client_no_ai.get_automation.return_value = {
            "id": "1",
            "action_id": "generate_with_ai",
        }
        async with client_session_no_ai as session:
            result = await session.call_tool(
                "get_ai_automation",
                {"automation_id": "1"},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is True
        mock_pipefy_client_no_ai.get_automation.assert_awaited_once_with("1")


@pytest.mark.anyio
class TestGetAiAutomations:
    async def test_filters_to_generate_with_ai_only(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_automations.return_value = [
            {"id": "1", "name": "AI", "active": True, "action_id": "generate_with_ai"},
            {
                "id": "2",
                "name": "HTTP",
                "active": True,
                "action_id": "send_http_request",
            },
            {
                "id": "3",
                "name": "Legacy",
                "active": True,
                "actionParams": {"aiParams": {"value": "x"}},
            },
        ]
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automations",
                {"pipe_id": "303"},
            )
        assert result.isError is False
        mock_pipefy_client.get_automations.assert_awaited_once_with(
            organization_id=None,
            pipe_id="303",
        )
        payload = extract_payload(result)
        assert payload["success"] is True
        data = payload["data"]
        assert len(data) == 2
        ids = {row["id"] for row in data}
        assert ids == {"1", "3"}

    async def test_filter_accepts_camel_case_action_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_automations.return_value = [
            {"id": "9", "name": "AI", "active": True, "actionId": "generate_with_ai"},
        ]
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automations",
                {"pipe_id": "1"},
            )
        data = extract_payload(result)["data"]
        assert len(data) == 1 and data[0]["id"] == "9"

    async def test_empty_when_none_match(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_automations.return_value = [
            {
                "id": "2",
                "name": "HTTP",
                "active": True,
                "action_id": "send_http_request",
            },
        ]
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automations",
                {"pipe_id": "303"},
            )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["data"] == []

    async def test_passes_organization_id_when_provided(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_automations.return_value = []
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automations",
                {"pipe_id": "303", "organization_id": "9001"},
            )
        assert result.isError is False
        mock_pipefy_client.get_automations.assert_awaited_once_with(
            organization_id="9001",
            pipe_id="303",
        )
        assert extract_payload(result)["success"] is True

    async def test_graphql_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_automations.side_effect = TransportQueryError(
            "failed", errors=[{"message": "no access"}]
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automations",
                {"pipe_id": "303"},
            )
        p = extract_payload(result)
        assert p["success"] is False
        assert "no access" in tool_error_message(p)

    async def test_rejects_invalid_pipe_id(
        self,
        client_session,
        mock_pipefy_client,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automations",
                {"pipe_id": ""},
            )
        mock_pipefy_client.get_automations.assert_not_called()
        assert_invalid_arguments_envelope(result)

    async def test_rejects_invalid_organization_id(
        self,
        client_session,
        mock_pipefy_client,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automations",
                {"pipe_id": "1", "organization_id": ""},
            )
        mock_pipefy_client.get_automations.assert_not_called()
        assert_invalid_arguments_envelope(result)

    async def test_works_without_oauth_config(
        self,
        client_session_no_ai,
        mock_pipefy_client_no_ai,
        extract_payload,
    ):
        mock_pipefy_client_no_ai.get_automations.return_value = [
            {"id": "a", "name": "x", "active": True, "action_id": "generate_with_ai"},
        ]
        async with client_session_no_ai as session:
            result = await session.call_tool(
                "get_ai_automations",
                {"pipe_id": "10"},
            )
        assert extract_payload(result)["success"] is True

    async def test_org_auto_resolution_omits_organization_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """When ``organization_id`` is omitted, the client lists with ``None`` (org resolved inside the service)."""
        mock_pipefy_client.get_automations.return_value = [
            {"id": "1", "name": "AI", "active": True, "action_id": "generate_with_ai"},
        ]
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automations",
                {"pipe_id": "42"},
            )
        assert extract_payload(result)["success"] is True
        mock_pipefy_client.get_automations.assert_awaited_once_with(
            organization_id=None,
            pipe_id="42",
        )


@pytest.mark.anyio
class TestDeleteAiAutomation:
    async def test_confirm_false_returns_preview(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "delete_ai_automation",
                {"automation_id": "rm-1", "confirm": False},
            )
        assert result.isError is False
        mock_pipefy_client.delete_automation.assert_not_called()
        p = extract_payload(result)
        assert p["success"] is False
        assert p.get("requires_confirmation") is True
        assert "AI automation (ID: rm-1)" in p["resource"]

    async def test_confirm_true_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.delete_automation.return_value = {"success": True}
        async with client_session as session:
            result = await session.call_tool(
                "delete_ai_automation",
                {"automation_id": "rm-1", "confirm": True},
            )
        assert result.isError is False
        mock_pipefy_client.delete_automation.assert_awaited_once_with("rm-1")
        p = extract_payload(result)
        assert p["success"] is True

    async def test_graphql_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.delete_automation.side_effect = TransportQueryError(
            "failed", errors=[{"message": "forbidden"}]
        )
        async with client_session as session:
            result = await session.call_tool(
                "delete_ai_automation",
                {"automation_id": "z", "confirm": True},
            )
        p = extract_payload(result)
        assert p["success"] is False
        assert "forbidden" in tool_error_message(p)

    async def test_works_without_oauth_config(
        self,
        client_session_no_ai,
        mock_pipefy_client_no_ai,
        extract_payload,
    ):
        """Delete uses public GraphQL, not internal_api — OAuth is not required."""
        mock_pipefy_client_no_ai.delete_automation.return_value = {"success": True}
        async with client_session_no_ai as session:
            result = await session.call_tool(
                "delete_ai_automation",
                {"automation_id": "1", "confirm": True},
            )
        assert result.isError is False
        mock_pipefy_client_no_ai.delete_automation.assert_awaited_once_with("1")
        p = extract_payload(result)
        assert p["success"] is True

    async def test_api_success_false_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.delete_automation.return_value = {"success": False}
        async with client_session as session:
            result = await session.call_tool(
                "delete_ai_automation",
                {"automation_id": "x", "confirm": True},
            )
        p = extract_payload(result)
        assert p["success"] is False
        assert "did not succeed" in tool_error_message(p).lower()

    async def test_rejects_invalid_automation_id(
        self,
        client_session,
        mock_pipefy_client,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "delete_ai_automation",
                {"automation_id": "", "confirm": True},
            )
        mock_pipefy_client.delete_automation.assert_not_called()
        assert_invalid_arguments_envelope(result)

    async def test_has_destructive_hint(self, client_session):
        async with client_session as session:
            listed = await session.list_tools()
        tool = next(t for t in listed.tools if t.name == "delete_ai_automation")
        assert tool.annotations is not None
        assert tool.annotations.destructiveHint is True
        assert tool.annotations.readOnlyHint is False


@pytest.mark.anyio
class TestCreateAiAutomation:
    async def test_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        legacy_envelope,
    ):
        mock_pipefy_client.create_ai_automation.return_value = {
            "automation_id": "123",
            "message": "AI Automation created successfully. ID: 123",
        }
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_automation",
                {
                    "name": "My Auto",
                    "event_id": "card_created",
                    "pipe_id": "303",
                    "prompt": "Summarize %{133}",
                    "field_ids": ["133"],
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload == {
            "success": True,
            "automation_id": "123",
            "message": "AI Automation created successfully. ID: 123",
        }
        assert isinstance(payload["message"], str)
        assert isinstance(payload["automation_id"], str)

    async def test_success_unified_envelope(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        unified_envelope,
    ):
        """Default flag=True — automation_id sits under ``data``."""
        mock_pipefy_client.create_ai_automation.return_value = {
            "automation_id": "123",
            "message": "AI Automation created successfully. ID: 123",
        }
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_automation",
                {
                    "name": "My Auto",
                    "event_id": "card_created",
                    "pipe_id": "303",
                    "prompt": "Summarize %{133}",
                    "field_ids": ["133"],
                },
            )
        payload = extract_payload(result)
        assert payload == {
            "success": True,
            "data": {"automation_id": "123"},
            "message": "AI Automation created successfully. ID: 123",
        }

    async def test_service_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.create_ai_automation.side_effect = RuntimeError(
            "GraphQL error"
        )
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_automation",
                {
                    "name": "My Auto",
                    "event_id": "card_created",
                    "pipe_id": "303",
                    "prompt": "Summarize %{133}",
                    "field_ids": ["133"],
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert isinstance(tool_error_message(payload), str)

    async def test_internal_api_style_error_strips_code_and_correlation_from_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.create_ai_automation.side_effect = ValueError(
            "Invalid prompt [code=INVALID_PROMPT] [correlation_id=abc-123-def]"
        )
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_automation",
                {
                    "name": "My Auto",
                    "event_id": "card_created",
                    "pipe_id": "303",
                    "prompt": "Summarize %{133}",
                    "field_ids": ["133"],
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        err = tool_error_message(payload)
        assert "[code=" not in err
        assert "[correlation_id=" not in err
        assert "Invalid prompt" in err
        assert "abc-123-def" not in err

    async def test_create_debug_true_includes_correlation_and_codes_in_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.create_ai_automation.side_effect = ValueError(
            "Invalid prompt [code=INVALID_PROMPT] [correlation_id=abc-123-def]"
        )
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_automation",
                {
                    "name": "My Auto",
                    "event_id": "card_created",
                    "pipe_id": "303",
                    "prompt": "Summarize %{133}",
                    "field_ids": ["133"],
                    "debug": True,
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        err = tool_error_message(payload)
        assert "[code=" not in err
        assert "[correlation_id=" not in err
        assert "Invalid prompt" in err
        assert "(debug:" in err
        assert "INVALID_PROMPT" in err
        assert "abc-123-def" in err

    async def test_only_diagnostic_suffixes_use_stable_fallback(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.create_ai_automation.side_effect = ValueError(
            " [code=X] [correlation_id=Y]"
        )
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_automation",
                {
                    "name": "My Auto",
                    "event_id": "card_created",
                    "pipe_id": "303",
                    "prompt": "Summarize %{133}",
                    "field_ids": ["133"],
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        err = tool_error_message(payload)
        assert "[code=" not in err
        assert "[correlation_id=" not in err
        assert "Could not create the AI automation" in err

    async def test_omitted_condition_sends_default_condition_to_client(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        from pipefy_mcp.models.ai_automation import DEFAULT_CONDITION

        mock_pipefy_client.create_ai_automation.return_value = {
            "automation_id": "999",
            "message": "AI Automation created successfully. ID: 999",
        }
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_automation",
                {
                    "name": "No Condition",
                    "event_id": "card_created",
                    "pipe_id": "303",
                    "prompt": "Summarize %{133}",
                    "field_ids": ["133"],
                },
            )
        assert result.isError is False
        validated_input = mock_pipefy_client.create_ai_automation.call_args[0][0]
        assert validated_input.condition.model_dump(mode="python") == DEFAULT_CONDITION

    async def test_explicit_condition_overrides_default(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        custom_condition = {
            "expressions": [
                {
                    "structure_id": 1,
                    "field_address": "status",
                    "operation": "eq",
                    "value": "open",
                }
            ],
            "expressions_structure": [[1]],
        }
        mock_pipefy_client.create_ai_automation.return_value = {
            "automation_id": "888",
            "message": "AI Automation created successfully. ID: 888",
        }
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_automation",
                {
                    "name": "Custom Condition",
                    "event_id": "card_created",
                    "pipe_id": "303",
                    "prompt": "Summarize %{133}",
                    "field_ids": ["133"],
                    "condition": custom_condition,
                },
            )
        assert result.isError is False
        validated_input = mock_pipefy_client.create_ai_automation.call_args[0][0]
        dumped = validated_input.condition.model_dump(mode="python")
        assert dumped["expressions"][0]["field_address"] == "status"
        assert dumped["expressions"][0]["operation"] == "eq"

    async def test_validation_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_automation",
                {
                    "name": "",
                    "event_id": "card_created",
                    "pipe_id": "303",
                    "prompt": "Summarize %{133}",
                    "field_ids": ["133"],
                },
            )
        assert result.isError is False
        mock_pipefy_client.create_ai_automation.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload


@pytest.mark.anyio
class TestUpdateAiAutomation:
    async def test_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        legacy_envelope,
    ):
        mock_pipefy_client.update_ai_automation.return_value = {
            "automation_id": "789",
            "message": "AI Automation updated successfully. ID: 789",
        }
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_automation",
                {"automation_id": "789", "name": "Updated", "active": False},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload == {
            "success": True,
            "automation_id": "789",
            "message": "AI Automation updated successfully. ID: 789",
        }
        assert isinstance(payload["message"], str)
        assert isinstance(payload["automation_id"], str)

    async def test_service_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.update_ai_automation.side_effect = ValueError(
            "Network error"
        )
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_automation",
                {"automation_id": "789", "name": "Updated", "active": False},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    async def test_internal_api_style_error_strips_code_and_correlation_on_update(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.update_ai_automation.side_effect = ValueError(
            "Not found [code=NOT_FOUND] [correlation_id=corr-9]"
        )
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_automation",
                {"automation_id": "789", "name": "Updated", "active": False},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        err = tool_error_message(payload)
        assert "[code=" not in err
        assert "[correlation_id=" not in err
        assert "Ai automation not found (ID: 789)" in err
        assert "get_ai_automations" in err
        assert "corr-9" not in err

    async def test_update_debug_true_includes_correlation_and_codes(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.update_ai_automation.side_effect = ValueError(
            "Not found [code=NOT_FOUND] [correlation_id=corr-9]"
        )
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_automation",
                {
                    "automation_id": "789",
                    "name": "Updated",
                    "active": False,
                    "debug": True,
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        err = tool_error_message(payload)
        assert "[code=" not in err
        assert "Ai automation not found (ID: 789)" in err
        assert "(debug:" in err
        assert "NOT_FOUND" in err
        assert "corr-9" in err

    async def test_update_plain_api_automation_not_found_gets_discovery_hint(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.update_ai_automation.side_effect = ValueError(
            "API error: Automation not found with id: 99999999999"
        )
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_automation",
                {"automation_id": "99999999999", "name": "x"},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        err = tool_error_message(payload)
        assert "Ai automation not found (ID: 99999999999)" in err
        assert "get_ai_automations" in err
        assert payload["error"]["code"] == "NOT_FOUND"

    async def test_update_permission_denied_gets_gap_a_ambiguity_hint(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.update_ai_automation.side_effect = ValueError(
            "Permission denied [code=PERMISSION_DENIED] [correlation_id=c1]"
        )
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_automation",
                {"automation_id": "42", "name": "x"},
            )
        assert result.isError is False
        payload = extract_payload(result)
        err = tool_error_message(payload)
        assert "may not exist OR" in err
        assert "get_ai_automations" in err
        assert "get_pipe_members" not in err
        assert payload["error"]["code"] == "PERMISSION_DENIED"


## ---------------------------------------------------------------------------
## AI Automation not configured (no OAuth credentials)
## ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestAiAutomationNotConfigured:
    async def test_create_returns_error_payload_when_not_configured(
        self,
        client_session_no_ai,
        extract_payload,
    ):
        async with client_session_no_ai as session:
            result = await session.call_tool(
                "create_ai_automation",
                {
                    "name": "My Auto",
                    "event_id": "card_created",
                    "pipe_id": "303",
                    "prompt": "Summarize %{133}",
                    "field_ids": ["133"],
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "OAuth" in tool_error_message(payload)

    async def test_update_returns_error_payload_when_not_configured(
        self,
        client_session_no_ai,
        extract_payload,
    ):
        async with client_session_no_ai as session:
            result = await session.call_tool(
                "update_ai_automation",
                {"automation_id": "789", "name": "Updated"},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "OAuth" in tool_error_message(payload)

    async def test_delete_works_without_oauth_config(
        self,
        client_session_no_ai,
        mock_pipefy_client_no_ai,
        extract_payload,
    ):
        """Delete uses public GraphQL — no OAuth needed (unlike create/update)."""
        mock_pipefy_client_no_ai.delete_automation.return_value = {"success": True}
        async with client_session_no_ai as session:
            result = await session.call_tool(
                "delete_ai_automation",
                {"automation_id": "789", "confirm": True},
            )
        assert result.isError is False
        mock_pipefy_client_no_ai.delete_automation.assert_awaited_once_with("789")
        payload = extract_payload(result)
        assert payload["success"] is True


## ---------------------------------------------------------------------------
## PipefyId coercion: int → str through MCP transport (mcporter mitigation)
## ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestPipefyIdCoercion:
    async def test_create_ai_automation_coerces_int_pipe_id_and_event_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.create_ai_automation.return_value = {
            "automation_id": "456",
            "message": "AI Automation created successfully. ID: 456",
        }
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_automation",
                {
                    "name": "Coerce Test",
                    "event_id": 101,
                    "pipe_id": 303,
                    "prompt": "Summarize %{133}",
                    "field_ids": ["f1"],
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is True

        validated_input = mock_pipefy_client.create_ai_automation.call_args[0][0]
        assert validated_input.pipe_id == "303"
        assert validated_input.event_id == "101"

    async def test_update_ai_automation_coerces_int_automation_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.update_ai_automation.return_value = {
            "automation_id": "789",
            "message": "AI Automation updated successfully. ID: 789",
        }
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_automation",
                {"automation_id": 789, "name": "Updated"},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is True

        validated_input = mock_pipefy_client.update_ai_automation.call_args[0][0]
        assert validated_input.automation_id == "789"

    async def test_get_ai_automation_coerces_int_automation_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_automation.return_value = {"id": "900", "name": "x"}
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automation",
                {"automation_id": 900},
            )
        assert result.isError is False
        assert extract_payload(result)["success"] is True
        mock_pipefy_client.get_automation.assert_awaited_once_with("900")

    async def test_get_ai_automations_coerces_int_pipe_and_org_ids(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_automations.return_value = []
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automations",
                {"pipe_id": 303, "organization_id": 9001},
            )
        assert extract_payload(result)["success"] is True
        mock_pipefy_client.get_automations.assert_awaited_once_with(
            organization_id="9001",
            pipe_id="303",
        )

    async def test_delete_ai_automation_coerces_int_automation_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.delete_automation.return_value = {"success": True}
        async with client_session as session:
            result = await session.call_tool(
                "delete_ai_automation",
                {"automation_id": 501, "confirm": True},
            )
        assert extract_payload(result)["success"] is True
        mock_pipefy_client.delete_automation.assert_awaited_once_with("501")


## ---------------------------------------------------------------------------
## validate_ai_automation_prompt
## ---------------------------------------------------------------------------

MOCK_PIPE_WITH_PREFS = {
    "pipe": {
        "id": "303",
        "uuid": "pipe-uuid-303",
        "name": "Test Pipe",
        "preferences": {"aiAgentsEnabled": True},
        "phases": [
            {
                "id": "1",
                "name": "Start",
                "fields": [
                    {
                        "id": "slug_a",
                        "internal_id": "100",
                        "label": "Summary",
                        "type": "short_text",
                        "editable": True,
                    },
                    {
                        "id": "slug_b",
                        "internal_id": "200",
                        "label": "Status",
                        "type": "short_text",
                        "editable": False,
                    },
                ],
            },
        ],
        "start_form_fields": [
            {
                "id": "slug_c",
                "internal_id": "300",
                "label": "Title",
                "type": "short_text",
                "editable": True,
            },
        ],
    },
}

MOCK_EVENTS = [
    {"id": "card_created"},
    {"id": "card_moved"},
    {"id": "field_updated"},
]


@pytest.mark.anyio
class TestValidateAiAutomationPrompt:
    async def test_valid_prompt(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_PREFS
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["100"],
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["valid"] is True
        assert payload["problems"] == []
        assert payload["field_map"]["100"] == "Summary"

    async def test_missing_field_ref_in_prompt(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_PREFS
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Just a plain prompt with no references",
                    "field_ids": ["100"],
                },
            )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["valid"] is False
        assert any("%{internal_id}" in p for p in payload["problems"])

    async def test_invalid_field_id_in_prompt_token(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_PREFS
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{999999}",
                    "field_ids": ["100"],
                },
            )
        payload = extract_payload(result)
        assert payload["valid"] is False
        assert any("999999" in p for p in payload["problems"])

    async def test_invalid_output_field_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_PREFS
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["888888"],
                },
            )
        payload = extract_payload(result)
        assert payload["valid"] is False
        assert any("888888" in p for p in payload["problems"])

    async def test_ai_disabled_on_pipe(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        disabled_pipe = {
            "pipe": {
                **MOCK_PIPE_WITH_PREFS["pipe"],
                "preferences": {"aiAgentsEnabled": False},
            }
        }
        mock_pipefy_client.get_pipe_with_preferences.return_value = disabled_pipe
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["100"],
                },
            )
        payload = extract_payload(result)
        assert payload["valid"] is False
        assert any("AI is not enabled" in p for p in payload["problems"])

    async def test_valid_event_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_PREFS
        mock_pipefy_client.get_automation_events.return_value = MOCK_EVENTS
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["100"],
                    "event_id": "card_created",
                },
            )
        payload = extract_payload(result)
        assert payload["valid"] is True
        assert payload["problems"] == []

    async def test_invalid_event_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_PREFS
        mock_pipefy_client.get_automation_events.return_value = MOCK_EVENTS
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["100"],
                    "event_id": "nonexistent_event",
                },
            )
        payload = extract_payload(result)
        assert payload["valid"] is False
        assert any("nonexistent_event" in p for p in payload["problems"])

    async def test_read_only_field_warning(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_PREFS
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Check: %{200}",
                    "field_ids": ["200"],
                },
            )
        payload = extract_payload(result)
        # read-only field appears in warnings, not problems
        assert any("read-only" in w for w in payload["warnings"])

    async def test_pipe_fetch_failure(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe_with_preferences.side_effect = RuntimeError(
            "network error"
        )
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["100"],
                },
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "network error" in tool_error_message(payload)

    async def test_rejects_invalid_pipe_id(
        self,
        client_session,
        mock_pipefy_client,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["100"],
                },
            )
        mock_pipefy_client.get_pipe_with_preferences.assert_not_called()
        assert_invalid_arguments_envelope(result)

    async def test_event_fetch_failure_adds_warning(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_PREFS
        mock_pipefy_client.get_automation_events.side_effect = RuntimeError("fail")
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["100"],
                    "event_id": "card_created",
                },
            )
        payload = extract_payload(result)
        # Event fetch failure is a warning, not a problem
        assert payload["valid"] is True
        assert any("Could not verify event_id" in w for w in payload["warnings"])

    async def test_has_read_only_annotation(self, client_session):
        async with client_session as session:
            listed = await session.list_tools()
        tool = next(
            t for t in listed.tools if t.name == "validate_ai_automation_prompt"
        )
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True

    async def test_field_map_contains_only_referenced_fields(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_PREFS
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["300"],
                },
            )
        payload = extract_payload(result)
        # field_map only includes referenced fields (100 from prompt, 300 from field_ids)
        assert "100" in payload["field_map"]
        assert "300" in payload["field_map"]
        assert "200" not in payload["field_map"]


# AI credit check — three-case matrix exercised below. Uses a variant of
# MOCK_PIPE_WITH_PREFS that carries ``organizationId`` so the credit branch
# runs; tests explicitly set ``get_ai_credit_usage`` to shape ``aiCreditUsageStats``.
MOCK_PIPE_WITH_ORG = {
    "pipe": {
        **MOCK_PIPE_WITH_PREFS["pipe"],
        "organizationId": "org-42",
    }
}


@pytest.mark.anyio
class TestValidateAiAutomationPromptCreditCheck:
    async def test_ai_automations_disabled_blocks_with_problem(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_ORG
        mock_pipefy_client.get_ai_credit_usage.return_value = {
            "aiCreditUsageStats": {
                "active": False,
                "usage": 0,
                "limit": 0,
                "hasAddon": False,
                "aiAutomation": {"enabled": False},
            }
        }
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["100"],
                },
            )
        payload = extract_payload(result)
        assert payload["valid"] is False
        assert any(
            "AI Automations are disabled on this organization" in p
            for p in payload["problems"]
        )

    async def test_exhausted_budget_emits_warning_not_problem(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_ORG
        mock_pipefy_client.get_ai_credit_usage.return_value = {
            "aiCreditUsageStats": {
                "active": True,
                "usage": 1500,
                "limit": 1000,
                "hasAddon": False,
                "aiAutomation": {"enabled": True},
            }
        }
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["100"],
                },
            )
        payload = extract_payload(result)
        assert payload["valid"] is True
        assert any("AI credit budget exhausted" in w for w in payload["warnings"])

    async def test_limit_zero_is_silent(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Sandbox / custom plans with uncapped billing report limit=0;
        emitting a warning there is noise, so the check stays silent."""
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_ORG
        mock_pipefy_client.get_ai_credit_usage.return_value = {
            "aiCreditUsageStats": {
                "active": True,
                "usage": 1392,
                "limit": 0,
                "hasAddon": False,
                "aiAutomation": {"enabled": True},
            }
        }
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["100"],
                },
            )
        payload = extract_payload(result)
        assert payload["valid"] is True
        assert not any("credit" in w.lower() for w in payload["warnings"])
        assert not any("AI Automations are disabled" in p for p in payload["problems"])

    async def test_addon_skips_exhausted_warning(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """``hasAddon`` means billing will absorb overage; don't warn."""
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_ORG
        mock_pipefy_client.get_ai_credit_usage.return_value = {
            "aiCreditUsageStats": {
                "active": True,
                "usage": 1500,
                "limit": 1000,
                "hasAddon": True,
                "aiAutomation": {"enabled": True},
            }
        }
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["100"],
                },
            )
        payload = extract_payload(result)
        assert not any("credit" in w.lower() for w in payload["warnings"])

    async def test_credit_lookup_failure_is_silent(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Credit check is informational; a lookup error must not block the preflight."""
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_ORG
        mock_pipefy_client.get_ai_credit_usage.side_effect = RuntimeError("upstream")
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["100"],
                },
            )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["valid"] is True

    async def test_skipped_when_organization_id_missing(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Old mocks without ``organizationId`` must not trigger the credit lookup."""
        mock_pipefy_client.get_pipe_with_preferences.return_value = MOCK_PIPE_WITH_PREFS
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_automation_prompt",
                {
                    "pipe_id": "303",
                    "prompt": "Summarize: %{100}",
                    "field_ids": ["100"],
                },
            )
        payload = extract_payload(result)
        assert payload["success"] is True
        mock_pipefy_client.get_ai_credit_usage.assert_not_called()
