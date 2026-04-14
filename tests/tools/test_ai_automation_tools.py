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


@pytest.fixture
def mock_pipefy_client():
    client = MagicMock(spec=PipefyClient)
    client.create_ai_automation = AsyncMock()
    client.update_ai_automation = AsyncMock()
    client.get_automation = AsyncMock()
    client.get_automations = AsyncMock()
    client.delete_automation = AsyncMock()
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
        assert "boom" in p["error"]

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
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automation",
                {"automation_id": ""},
            )
        mock_pipefy_client.get_automation.assert_not_called()
        p = extract_payload(result)
        assert p["success"] is False
        assert "automation_id" in p["error"].lower()

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
        assert "nope" in p["error"]

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
        assert "no access" in p["error"]

    async def test_rejects_invalid_pipe_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automations",
                {"pipe_id": ""},
            )
        mock_pipefy_client.get_automations.assert_not_called()
        assert extract_payload(result)["success"] is False

    async def test_rejects_invalid_organization_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_automations",
                {"pipe_id": "1", "organization_id": ""},
            )
        mock_pipefy_client.get_automations.assert_not_called()
        assert extract_payload(result)["success"] is False

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
        assert "forbidden" in p["error"]

    async def test_not_configured_returns_oauth_message(
        self,
        client_session_no_ai,
        mock_pipefy_client_no_ai,
        extract_payload,
    ):
        async with client_session_no_ai as session:
            result = await session.call_tool(
                "delete_ai_automation",
                {"automation_id": "1", "confirm": True},
            )
        assert result.isError is False
        mock_pipefy_client_no_ai.delete_automation.assert_not_called()
        p = extract_payload(result)
        assert p["success"] is False
        assert "OAuth" in p["error"]

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
        assert "did not succeed" in p["error"].lower()

    async def test_rejects_invalid_automation_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "delete_ai_automation",
                {"automation_id": "", "confirm": True},
            )
        mock_pipefy_client.delete_automation.assert_not_called()
        assert extract_payload(result)["success"] is False

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
        assert isinstance(payload["error"], str)

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
        err = payload["error"]
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
        err = payload["error"]
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
        err = payload["error"]
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
        err = payload["error"]
        assert "[code=" not in err
        assert "[correlation_id=" not in err
        assert "Not found" in err
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
        err = payload["error"]
        assert "[code=" not in err
        assert "Not found" in err
        assert "(debug:" in err
        assert "NOT_FOUND" in err
        assert "corr-9" in err


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
        assert "OAuth" in payload["error"]

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
        assert "OAuth" in payload["error"]

    async def test_delete_returns_error_payload_when_not_configured(
        self,
        client_session_no_ai,
        mock_pipefy_client_no_ai,
        extract_payload,
    ):
        async with client_session_no_ai as session:
            result = await session.call_tool(
                "delete_ai_automation",
                {"automation_id": "789", "confirm": True},
            )
        assert result.isError is False
        mock_pipefy_client_no_ai.delete_automation.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "OAuth" in payload["error"]


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
