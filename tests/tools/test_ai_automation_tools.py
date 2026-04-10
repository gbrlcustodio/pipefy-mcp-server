"""Tests for AI Automation MCP tools."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
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
    client.ai_automation_available = True
    return client


@pytest.fixture
def mock_pipefy_client_no_ai():
    """Client where AI automation is not configured (no OAuth credentials)."""
    client = MagicMock(spec=PipefyClient)
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
