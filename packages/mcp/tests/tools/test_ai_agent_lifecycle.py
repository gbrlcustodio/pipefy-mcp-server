"""Lifecycle tests for AI agent active/disabled create and update."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from _mcp_compat import (
    create_connected_server_and_client_session as create_client_session,
)
from _shared.ai_agent_test_payloads import minimal_behavior_dict
from pipefy_sdk.models.ai_agent import CreateAiAgentInput, UpdateAiAgentInput

from pipefy_mcp.tools.ai_agent_tools import AiAgentTools
from tools.conftest import build_tool_test_server


@pytest.fixture
def mock_pipefy_client():
    client = MagicMock()
    client.create_ai_agent = AsyncMock()
    client.update_ai_agent = AsyncMock()
    client.toggle_ai_agent_status = AsyncMock()
    client.get_ai_agent = AsyncMock()
    client.get_ai_agents = AsyncMock()
    client.delete_ai_agent = AsyncMock()
    client.get_pipe = AsyncMock()
    client.get_pipe_relations = AsyncMock()
    client.get_pipe_members = AsyncMock(return_value={"pipe": {"members": []}})
    client.get_phase_allowed_move_targets = AsyncMock()
    client.get_phase_fields = AsyncMock(return_value={"fields": []})
    return client


@pytest.fixture
def mcp_server(mock_pipefy_client):
    return build_tool_test_server(
        "AI Agent Lifecycle Tools Test", AiAgentTools.register, mock_pipefy_client
    )


@pytest.fixture
def client_session(mcp_server):
    return create_client_session(
        mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )


@pytest.mark.anyio
class TestCreateAiAgentLifecycle:
    async def test_create_active_sets_preserve_disabled_at_false_on_update_chain(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        envelope_flag,
    ):
        """Default/active create omits preserve so configure update can clear API default."""
        mock_pipefy_client.create_ai_agent.return_value = {
            "agent_uuid": "active-uuid",
            "message": "created",
            "disabled_at": "2026-08-04T12:00:00+00:00",
            "active": False,
        }
        mock_pipefy_client.update_ai_agent.return_value = {
            "agent_uuid": "active-uuid",
            "message": "updated",
            "disabled_at": None,
            "active": True,
        }
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "Active Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Purpose",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                },
            )
        assert result.is_error is False
        create_arg = mock_pipefy_client.create_ai_agent.call_args[0][0]
        assert isinstance(create_arg, CreateAiAgentInput)
        assert create_arg.disabled_at is None
        update_arg = mock_pipefy_client.update_ai_agent.call_args[0][0]
        assert isinstance(update_arg, UpdateAiAgentInput)
        assert update_arg.disabled_at is None
        assert update_arg.preserve_disabled_at is False
        payload = extract_payload(result)
        assert payload["success"] is True
        if envelope_flag:
            assert payload["data"]["agent_uuid"] == "active-uuid"
            assert payload["data"]["disabled_at"] is None
            assert payload["data"]["active"] is True
        else:
            assert payload["agent_uuid"] == "active-uuid"
            assert payload["disabled_at"] is None
            assert payload["active"] is True

    async def test_create_inactive_sets_disabled_at_on_create_and_update_chain(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        envelope_flag,
    ):
        stub_disabled_at = "2026-08-04T13:00:00+00:00"
        mock_pipefy_client.create_ai_agent.return_value = {
            "agent_uuid": "inactive-uuid",
            "message": "created",
            "disabled_at": stub_disabled_at,
            "active": False,
        }
        mock_pipefy_client.update_ai_agent.return_value = {
            "agent_uuid": "inactive-uuid",
            "message": "updated",
            "disabled_at": stub_disabled_at,
            "active": False,
        }
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "Inactive Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Purpose",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                    "active": False,
                },
            )
        assert result.is_error is False
        create_arg = mock_pipefy_client.create_ai_agent.call_args[0][0]
        assert isinstance(create_arg, CreateAiAgentInput)
        assert create_arg.disabled_at is not None
        datetime.fromisoformat(create_arg.disabled_at)
        update_arg = mock_pipefy_client.update_ai_agent.call_args[0][0]
        assert isinstance(update_arg, UpdateAiAgentInput)
        assert update_arg.disabled_at == create_arg.disabled_at
        assert update_arg.disabled_at is not None
        assert update_arg.preserve_disabled_at is False
        payload = extract_payload(result)
        assert payload["success"] is True
        if envelope_flag:
            assert payload["data"]["agent_uuid"] == "inactive-uuid"
            assert payload["data"]["disabled_at"] == stub_disabled_at
            assert payload["data"]["active"] is False
        else:
            assert payload["agent_uuid"] == "inactive-uuid"
            assert payload["disabled_at"] == stub_disabled_at
            assert payload["active"] is False


@pytest.mark.anyio
class TestUpdateAiAgentLifecycle:
    async def test_update_preserves_inactive_status_in_success_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        envelope_flag,
    ):
        """Routine update does not inject reactivation; returns disabled_at from SDK."""
        stub_disabled_at = "2026-01-15T12:00:00+00:00"
        mock_pipefy_client.update_ai_agent.return_value = {
            "agent_uuid": "agent-uuid",
            "message": "AI Agent updated successfully. UUID: agent-uuid",
            "disabled_at": stub_disabled_at,
            "active": False,
        }
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_agent",
                {
                    "uuid": "agent-uuid",
                    "name": "Updated Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Do things",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                },
            )
        assert result.is_error is False
        update_arg = mock_pipefy_client.update_ai_agent.call_args[0][0]
        assert isinstance(update_arg, UpdateAiAgentInput)
        assert update_arg.disabled_at is None
        assert update_arg.preserve_disabled_at is True
        payload = extract_payload(result)
        assert payload["success"] is True
        if envelope_flag:
            assert payload["data"]["disabled_at"] == stub_disabled_at
            assert payload["data"]["active"] is False
        else:
            assert payload["disabled_at"] == stub_disabled_at
            assert payload["active"] is False
