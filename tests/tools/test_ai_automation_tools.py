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
