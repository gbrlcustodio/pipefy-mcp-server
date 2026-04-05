"""Tests for AI Agent MCP tools."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.models.ai_agent import UpdateAiAgentInput
from pipefy_mcp.tools.ai_agent_tools import AiAgentTools
from tests.ai_agent_test_payloads import minimal_behavior_dict


@pytest.fixture
def anyio_backend():
    return "asyncio"


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
    return client


@pytest.fixture
def mcp_server(mock_pipefy_client):
    mcp = FastMCP("AI Agent Tools Test")
    AiAgentTools.register(mcp, mock_pipefy_client)
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
    async def test_data_source_ids_defaults_to_empty_list(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.create_ai_agent.return_value = {
            "agent_uuid": "abc-123",
            "message": "created",
        }
        mock_pipefy_client.update_ai_agent.return_value = {
            "agent_uuid": "abc-123",
            "message": "updated",
        }
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "My Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Do the thing",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is True
        update_arg = mock_pipefy_client.update_ai_agent.call_args[0][0]
        assert isinstance(update_arg, UpdateAiAgentInput)
        assert update_arg.data_source_ids == []

    async def test_service_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.create_ai_agent.side_effect = RuntimeError("GraphQL error")
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "My Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Purpose",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert isinstance(payload["error"], str)
        assert "GraphQL error" in payload["error"]
        mock_pipefy_client.update_ai_agent.assert_not_called()

    async def test_validation_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "",
                    "repo_uuid": "repo-456",
                    "instruction": "Purpose",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                },
            )
        assert result.isError is False
        mock_pipefy_client.create_ai_agent.assert_not_called()
        mock_pipefy_client.update_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    async def test_create_and_configure_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.create_ai_agent.return_value = {
            "agent_uuid": "new-uuid",
            "message": "created",
        }
        mock_pipefy_client.update_ai_agent.return_value = {
            "agent_uuid": "new-uuid",
            "message": "updated",
        }
        behaviors = [minimal_behavior_dict(name="B1")]
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "Configured Agent",
                    "repo_uuid": "repo-789",
                    "instruction": "Tell users about the pipe",
                    "behaviors": behaviors,
                    "data_source_ids": ["ds-1", "ds-2"],
                },
            )
        assert result.isError is False
        mock_pipefy_client.create_ai_agent.assert_awaited_once()
        mock_pipefy_client.update_ai_agent.assert_awaited_once()
        update_arg = mock_pipefy_client.update_ai_agent.call_args[0][0]
        assert isinstance(update_arg, UpdateAiAgentInput)
        assert update_arg.uuid == "new-uuid"
        assert update_arg.name == "Configured Agent"
        assert update_arg.repo_uuid == "repo-789"
        assert update_arg.instruction == "Tell users about the pipe"
        assert len(update_arg.behaviors) == 1
        assert update_arg.behaviors[0].name == "B1"
        assert update_arg.behaviors[0].event_id == "card_created"
        assert update_arg.data_source_ids == ["ds-1", "ds-2"]
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["agent_uuid"] == "new-uuid"

    async def test_partial_failure_returns_uuid_and_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.create_ai_agent.return_value = {
            "agent_uuid": "created-uuid",
            "message": "AI Agent created successfully. UUID: created-uuid",
        }
        mock_pipefy_client.update_ai_agent.side_effect = ValueError("update failed")
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "My Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Purpose",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert payload["agent_uuid"] == "created-uuid"
        assert "error" in payload
        assert "update failed" in payload["error"]

    async def test_graphql_error_extracts_messages(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.create_ai_agent.side_effect = TransportQueryError(
            "failed", errors=[{"message": "permission denied"}]
        )
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "My Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Purpose",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "permission denied" in payload["error"]
        mock_pipefy_client.update_ai_agent.assert_not_called()

    async def test_empty_behaviors_returns_validation_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "My Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Purpose",
                    "behaviors": [],
                },
            )
        assert result.isError is False
        mock_pipefy_client.create_ai_agent.assert_not_called()
        mock_pipefy_client.update_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    async def test_six_behaviors_returns_validation_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        six = [minimal_behavior_dict(name=f"B{i}") for i in range(6)]
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "My Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Purpose",
                    "behaviors": six,
                },
            )
        assert result.isError is False
        mock_pipefy_client.create_ai_agent.assert_not_called()
        mock_pipefy_client.update_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload


@pytest.mark.anyio
class TestUpdateAiAgent:
    async def test_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.update_ai_agent.return_value = {
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
                    "behaviors": [minimal_behavior_dict(name="B1")],
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
        mock_pipefy_client,
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
        mock_pipefy_client.update_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    async def test_six_behaviors_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
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
                        minimal_behavior_dict(name=f"B{i}") for i in range(6)
                    ],
                },
            )
        assert result.isError is False
        mock_pipefy_client.update_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    async def test_service_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.update_ai_agent.side_effect = ValueError("Network error")
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
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload


@pytest.mark.anyio
class TestToggleAiAgentStatus:
    async def test_activate_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.toggle_ai_agent_status.return_value = {
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
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.toggle_ai_agent_status.return_value = {
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
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.toggle_ai_agent_status.side_effect = RuntimeError(
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

    async def test_graphql_error_extracts_message(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.toggle_ai_agent_status.side_effect = TransportQueryError(
            "failed", errors=[{"message": "Agent is locked"}]
        )
        async with client_session as session:
            result = await session.call_tool(
                "toggle_ai_agent_status",
                {"uuid": "agent-uuid", "active": True},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "locked" in payload["error"]


def _behavior_update_card_on_pipe(pipe_id="1", field_id="100"):
    return {
        "name": "Fill",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "go",
                "actionsAttributes": [
                    {
                        "name": "u",
                        "actionType": "update_card",
                        "metadata": {
                            "pipeId": pipe_id,
                            "fieldsAttributes": [
                                {
                                    "fieldId": field_id,
                                    "inputMode": "fill_with_ai",
                                    "value": "",
                                },
                            ],
                        },
                    },
                ],
            }
        },
    }


def _pipe_graph_with_field(field_id="100", phase_id="ph-1"):
    return {
        "pipe": {
            "phases": [
                {
                    "id": phase_id,
                    "fields": [{"id": field_id}],
                }
            ],
            "start_form_fields": [],
        }
    }


@pytest.mark.anyio
class TestValidateAiAgentBehaviors:
    async def test_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field()
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {
                    "pipe_id": "1",
                    "behaviors": [_behavior_update_card_on_pipe()],
                    "strict_unknown_action_types": True,
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["valid"] is True
        assert payload["problems"] == []
        assert payload["warnings"] == []
        mock_pipefy_client.get_pipe.assert_awaited_once_with(1)
        mock_pipefy_client.get_pipe_relations.assert_awaited_once_with("1")

    async def test_relations_fetch_failure_adds_warning_skips_relation_check(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field()
        mock_pipefy_client.get_pipe_relations.side_effect = TransportQueryError(
            "failed", errors=[{"message": "denied"}]
        )
        behavior = {
            "name": "Child",
            "event_id": "card_created",
            "actionParams": {
                "aiBehaviorParams": {
                    "instruction": "go",
                    "actionsAttributes": [
                        {
                            "name": "c",
                            "actionType": "create_connected_card",
                            "metadata": {
                                "pipeId": "99999",
                                "fieldsAttributes": [
                                    {
                                        "fieldId": "200",
                                        "inputMode": "fill_with_ai",
                                        "value": "",
                                    },
                                ],
                            },
                        },
                    ],
                }
            },
        }
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {"pipe_id": "1", "behaviors": [behavior]},
            )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["valid"] is True
        assert payload["problems"] == []
        assert len(payload["warnings"]) == 1
        assert "relations" in payload["warnings"][0].lower()

    async def test_invalid_field_id_blocking(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field()
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {
                    "pipe_id": "1",
                    "behaviors": [_behavior_update_card_on_pipe(field_id="999")],
                },
            )
        payload = extract_payload(result)
        assert payload["valid"] is False
        assert any("999" in p for p in payload["problems"])

    async def test_strict_unknown_action_types_false_warns_only(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        from tests.ai_agent_test_payloads import behavior_with_action

        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field()
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        b = behavior_with_action("custom_future_type", {"x": 1})
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {
                    "pipe_id": "1",
                    "behaviors": [b],
                    "strict_unknown_action_types": False,
                },
            )
        payload = extract_payload(result)
        assert payload["valid"] is True
        assert payload["problems"] == []
        assert any("custom_future_type" in w for w in payload["warnings"])


@pytest.mark.anyio
class TestGetAiAgent:
    async def test_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        agent = {
            "uuid": "agent-1",
            "name": "Assistant",
            "instruction": "Help",
            "disabledAt": None,
            "needReview": False,
        }
        mock_pipefy_client.get_ai_agent.return_value = agent
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_agent",
                {"uuid": "agent-1"},
            )
        assert result.isError is False
        mock_pipefy_client.get_ai_agent.assert_awaited_once_with("agent-1")
        payload = extract_payload(result)
        assert payload == {"success": True, "agent": agent}

    async def test_not_found_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_ai_agent.return_value = {}
        async with client_session as session:
            result = await session.call_tool("get_ai_agent", {"uuid": "missing-uuid"})
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "not found" in payload["error"].lower()

    async def test_blank_uuid_returns_error_payload(
        self, client_session, mock_pipefy_client, extract_payload
    ):
        async with client_session as session:
            result = await session.call_tool("get_ai_agent", {"uuid": "  "})
        mock_pipefy_client.get_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "blank" in payload["error"].lower()

    async def test_graphql_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_ai_agent.side_effect = TransportQueryError(
            "failed", errors=[{"message": "not found"}]
        )
        async with client_session as session:
            result = await session.call_tool("get_ai_agent", {"uuid": "missing"})
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "not found" in payload["error"]


@pytest.mark.anyio
class TestGetAiAgents:
    async def test_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        agents = [{"uuid": "a1", "name": "One"}]
        mock_pipefy_client.get_ai_agents.return_value = agents
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_agents",
                {"repo_uuid": "pipe-uuid-9"},
            )
        assert result.isError is False
        mock_pipefy_client.get_ai_agents.assert_awaited_once_with("pipe-uuid-9")
        payload = extract_payload(result)
        assert payload == {"success": True, "agents": agents}

    async def test_blank_repo_uuid_returns_error_payload(
        self, client_session, mock_pipefy_client, extract_payload
    ):
        async with client_session as session:
            result = await session.call_tool("get_ai_agents", {"repo_uuid": ""})
        mock_pipefy_client.get_ai_agents.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "blank" in payload["error"].lower()

    async def test_graphql_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_ai_agents.side_effect = TransportQueryError(
            "failed", errors=[{"message": "denied"}]
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_agents",
                {"repo_uuid": "repo-x"},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "denied" in payload["error"]


@pytest.mark.anyio
class TestDeleteAiAgent:
    async def test_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.delete_ai_agent.return_value = {"success": True}
        async with client_session as session:
            result = await session.call_tool(
                "delete_ai_agent",
                {"uuid": "to-delete", "confirm": True},
            )
        assert result.isError is False
        mock_pipefy_client.delete_ai_agent.assert_awaited_once_with("to-delete")
        payload = extract_payload(result)
        assert payload["success"] is True
        assert isinstance(payload["message"], str)
        assert len(payload["message"]) > 0

    async def test_api_returns_false(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.delete_ai_agent.return_value = {"success": False}
        async with client_session as session:
            result = await session.call_tool(
                "delete_ai_agent", {"uuid": "fail", "confirm": True}
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "success=false" in payload["error"].lower()

    async def test_blank_uuid_returns_error_payload(
        self, client_session, mock_pipefy_client, extract_payload
    ):
        async with client_session as session:
            result = await session.call_tool("delete_ai_agent", {"uuid": "\t"})
        mock_pipefy_client.delete_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "blank" in payload["error"].lower()

    async def test_graphql_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.delete_ai_agent.side_effect = TransportQueryError(
            "failed", errors=[{"message": "gone"}]
        )
        async with client_session as session:
            result = await session.call_tool(
                "delete_ai_agent",
                {"uuid": "bad", "confirm": True},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "gone" in payload["error"]

    async def test_has_destructive_hint(self, client_session):
        async with client_session as session:
            listed = await session.list_tools()
        delete_tool = next(t for t in listed.tools if t.name == "delete_ai_agent")
        assert delete_tool.annotations is not None
        assert delete_tool.annotations.destructiveHint is True
        assert delete_tool.annotations.readOnlyHint is False


@pytest.mark.anyio
async def test_get_ai_agent_tools_have_read_only_hint(client_session):
    async with client_session as session:
        listed = await session.list_tools()
    by_name = {t.name: t for t in listed.tools}
    for name in ("get_ai_agent", "get_ai_agents", "validate_ai_agent_behaviors"):
        tool = by_name[name]
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
