"""Tests for AI Agent MCP tools."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.tools.ai_agent_tools import AiAgentTools


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_ai_agent_service():
    service = MagicMock()
    service.create_agent = AsyncMock()
    service.update_agent = AsyncMock()
    service.toggle_agent_status = AsyncMock()
    return service


@pytest.fixture
def mcp_server(mock_ai_agent_service):
    mcp = FastMCP("AI Agent Tools Test")
    AiAgentTools.register(mcp, mock_ai_agent_service)
    return mcp


@pytest.fixture
def client_session(mcp_server):
    return create_client_session(
        mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )


@pytest.mark.anyio
class TestCreateAiAgent:
    async def test_success(
        self,
        client_session,
        mock_ai_agent_service,
        extract_payload,
    ):
        mock_ai_agent_service.create_agent.return_value = {
            "agent_uuid": "abc-123",
            "message": "AI Agent created successfully. UUID: abc-123",
        }
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {"name": "My Agent", "repo_uuid": "repo-456"},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload == {
            "success": True,
            "agent_uuid": "abc-123",
            "message": "AI Agent created successfully. UUID: abc-123",
        }
        assert isinstance(payload["message"], str)
        assert isinstance(payload["agent_uuid"], str)

    async def test_service_error_returns_error_payload(
        self,
        client_session,
        mock_ai_agent_service,
        extract_payload,
    ):
        mock_ai_agent_service.create_agent.side_effect = RuntimeError("GraphQL error")
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {"name": "My Agent", "repo_uuid": "repo-456"},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert isinstance(payload["error"], str)

    async def test_validation_error_returns_error_payload(
        self,
        client_session,
        mock_ai_agent_service,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {"name": "", "repo_uuid": "repo-456"},
            )
        assert result.isError is False
        mock_ai_agent_service.create_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload


@pytest.mark.anyio
class TestUpdateAiAgent:
    async def test_success(
        self,
        client_session,
        mock_ai_agent_service,
        extract_payload,
    ):
        mock_ai_agent_service.update_agent.return_value = {
            "agent_uuid": "agent-uuid",
            "message": "AI Agent updated successfully. UUID: agent-uuid",
        }
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_agent",
                {
                    "uuid": "agent-uuid",
                    "name": "Updated Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Do things",
                    "behaviors": [{"name": "B1", "event_id": "card_created"}],
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload == {
            "success": True,
            "agent_uuid": "agent-uuid",
            "message": "AI Agent updated successfully. UUID: agent-uuid",
        }
        assert isinstance(payload["message"], str)
        assert isinstance(payload["agent_uuid"], str)

    async def test_zero_behaviors_returns_error_payload(
        self,
        client_session,
        mock_ai_agent_service,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_agent",
                {
                    "uuid": "agent-uuid",
                    "name": "Updated Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Do things",
                    "behaviors": [],
                },
            )
        assert result.isError is False
        mock_ai_agent_service.update_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    async def test_six_behaviors_returns_error_payload(
        self,
        client_session,
        mock_ai_agent_service,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_agent",
                {
                    "uuid": "agent-uuid",
                    "name": "Updated Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Do things",
                    "behaviors": [
                        {"name": f"B{i}", "event_id": "card_created"} for i in range(6)
                    ],
                },
            )
        assert result.isError is False
        mock_ai_agent_service.update_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    async def test_service_error_returns_error_payload(
        self,
        client_session,
        mock_ai_agent_service,
        extract_payload,
    ):
        mock_ai_agent_service.update_agent.side_effect = ValueError("Network error")
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_agent",
                {
                    "uuid": "agent-uuid",
                    "name": "Updated Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Do things",
                    "behaviors": [{"name": "B1", "event_id": "card_created"}],
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload


@pytest.mark.anyio
class TestToggleAiAgentStatus:
    async def test_activate_success(
        self,
        client_session,
        mock_ai_agent_service,
        extract_payload,
    ):
        mock_ai_agent_service.toggle_agent_status.return_value = {
            "success": True,
            "message": "AI Agent activated successfully.",
        }
        async with client_session as session:
            result = await session.call_tool(
                "toggle_ai_agent_status",
                {"uuid": "agent-uuid", "active": True},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload == {
            "success": True,
            "message": "AI Agent activated successfully.",
        }
        assert isinstance(payload["message"], str)

    async def test_deactivate_success(
        self,
        client_session,
        mock_ai_agent_service,
        extract_payload,
    ):
        mock_ai_agent_service.toggle_agent_status.return_value = {
            "success": True,
            "message": "AI Agent deactivated successfully.",
        }
        async with client_session as session:
            result = await session.call_tool(
                "toggle_ai_agent_status",
                {"uuid": "agent-uuid", "active": False},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is True
        assert "deactivated" in payload["message"]

    async def test_service_error_returns_error_payload(
        self,
        client_session,
        mock_ai_agent_service,
        extract_payload,
    ):
        mock_ai_agent_service.toggle_agent_status.side_effect = RuntimeError(
            "API error"
        )
        async with client_session as session:
            result = await session.call_tool(
                "toggle_ai_agent_status",
                {"uuid": "agent-uuid", "active": True},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert isinstance(payload["error"], str)
