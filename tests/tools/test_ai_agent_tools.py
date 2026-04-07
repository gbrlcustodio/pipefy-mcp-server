"""Tests for AI Agent MCP tools."""

import asyncio
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
from tests.ai_agent_test_payloads import behavior_with_action, minimal_behavior_dict


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

    async def test_blank_repo_uuid_returns_error_payload(
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
                    "repo_uuid": "   ",
                    "instruction": "Purpose",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                },
            )
        assert result.isError is False
        mock_pipefy_client.create_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "repo_uuid" in payload["error"]

    async def test_blank_name_returns_error_before_api_call(
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
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "name" in payload["error"]


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

    async def test_blank_uuid_returns_error_before_api_call(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_agent",
                {
                    "uuid": "  ",
                    "name": "Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Do things",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                },
            )
        assert result.isError is False
        mock_pipefy_client.update_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "uuid" in payload["error"]

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

    async def test_record_not_saved_with_valid_payload_shows_pipe_restriction(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.update_ai_agent.side_effect = TransportQueryError(
            "RECORD_NOT_SAVED", errors=[{"message": "RECORD_NOT_SAVED"}]
        )
        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field(
            field_id="425829426", phase_id="ph-1"
        )
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        behavior = _behavior_update_card_on_pipe(
            pipe_id="306996636", field_id="425829426"
        )
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_agent",
                {
                    "uuid": "agent-uuid",
                    "name": "Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Do things",
                    "behaviors": [behavior],
                },
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "RECORD_NOT_SAVED" in payload["error"]
        assert "pipe-specific restriction" in payload["error"]
        assert "Do NOT retry" in payload["error"]

    async def test_record_not_saved_with_invalid_payload_shows_problems(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.update_ai_agent.side_effect = TransportQueryError(
            "RECORD_NOT_SAVED", errors=[{"message": "RECORD_NOT_SAVED"}]
        )
        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field(
            field_id="100", phase_id="ph-1"
        )
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        behavior = _behavior_update_card_on_pipe(pipe_id="306996636", field_id="999")
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_agent",
                {
                    "uuid": "agent-uuid",
                    "name": "Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Do things",
                    "behaviors": [behavior],
                },
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "RECORD_NOT_SAVED" in payload["error"]
        assert "Validation found problems" in payload["error"]
        assert '"999"' in payload["error"]

    async def test_non_record_not_saved_error_uses_standard_enrichment(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.update_ai_agent.side_effect = ValueError("timeout")
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_agent",
                {
                    "uuid": "agent-uuid",
                    "name": "Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Do things",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                },
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "timeout" in payload["error"]
        assert "pipe-specific restriction" not in payload["error"]
        mock_pipefy_client.get_pipe.assert_not_called()


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

    async def test_create_table_record_warns_without_treating_table_field_as_pipe_field(
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
        behavior = behavior_with_action(
            "create_table_record",
            {
                "tableId": "tbl-1",
                "fieldsAttributes": [
                    {
                        "fieldId": "not-on-pipe-999",
                        "inputMode": "fill_with_ai",
                        "value": "",
                    },
                ],
            },
        )
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
        assert "create_table_record" in payload["warnings"][0]

    async def test_send_email_template_validates_without_pipe_field_problems(
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
        behavior = behavior_with_action(
            "send_email_template",
            {"emailTemplateId": "tmpl-abc"},
        )
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {"pipe_id": "1", "behaviors": [behavior]},
            )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["valid"] is True
        assert payload["problems"] == []
        assert payload["warnings"] == []

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

    async def test_success_with_behaviors(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Behaviors from the API are included verbatim in the MCP tool response."""
        from tests.ai_agent_test_payloads import mock_agent_with_behaviors

        agent = mock_agent_with_behaviors()
        mock_pipefy_client.get_ai_agent.return_value = agent
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_agent",
                {"uuid": "agent-with-behaviors"},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is True
        behaviors = payload["agent"]["behaviors"]
        assert behaviors is not None
        assert len(behaviors) == 1
        assert behaviors[0]["eventId"] == "card_created"
        ai_params = behaviors[0]["actionParams"]["aiBehaviorParams"]
        assert ai_params["instruction"] == "Analyze the card and fill summary."

    async def test_null_behaviors_from_api(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """When API returns behaviors: null, the tool response exposes it.

        This documents the bug: callers see behaviors=null and cannot safely
        re-send the config via update_ai_agent without risking data loss.
        """
        agent = {
            "uuid": "agent-1",
            "name": "Assistant",
            "instruction": "Help",
            "disabledAt": None,
            "needReview": False,
            "behaviors": None,
        }
        mock_pipefy_client.get_ai_agent.return_value = agent
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_agent",
                {"uuid": "agent-1"},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["agent"]["behaviors"] is None

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
class TestGetAiAgentGraphqlError:
    """Cover get_ai_agent GraphQL error path (line 410)."""

    async def test_runtime_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_ai_agent.side_effect = RuntimeError("server down")
        async with client_session as session:
            result = await session.call_tool("get_ai_agent", {"uuid": "agent-1"})
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "server down" in payload["error"]


@pytest.mark.anyio
class TestGetAiAgentsErrorPaths:
    """Cover get_ai_agents empty-list and GraphQL error paths."""

    async def test_empty_list_returns_success_with_empty_agents(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_ai_agents.return_value = []
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_agents", {"repo_uuid": "pipe-uuid"}
            )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["agents"] == []

    async def test_runtime_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_ai_agents.side_effect = RuntimeError("boom")
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_agents", {"repo_uuid": "pipe-uuid"}
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "boom" in payload["error"]


@pytest.mark.anyio
class TestToggleAiAgentStatusErrorPaths:
    """Cover blank uuid path (line 373)."""

    async def test_blank_uuid_returns_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "toggle_ai_agent_status", {"uuid": "   ", "active": True}
            )
        mock_pipefy_client.toggle_ai_agent_status.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "blank" in payload["error"].lower()


@pytest.mark.anyio
class TestDeleteAiAgentConfirmationGuard:
    """Cover confirmation guard early return (line 461)."""

    async def test_no_confirm_returns_requires_confirmation(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "delete_ai_agent", {"uuid": "agent-uuid", "confirm": False}
            )
        mock_pipefy_client.delete_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert payload.get("requires_confirmation") is True

    async def test_runtime_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.delete_ai_agent.side_effect = RuntimeError("network")
        async with client_session as session:
            result = await session.call_tool(
                "delete_ai_agent", {"uuid": "agent-uuid", "confirm": True}
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "network" in payload["error"]


@pytest.mark.anyio
class TestCreateAiAgentBlankInstruction:
    """Cover blank instruction guard (line 246)."""

    async def test_blank_instruction_returns_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "Agent",
                    "repo_uuid": "repo-1",
                    "instruction": "   ",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                },
            )
        mock_pipefy_client.create_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "instruction" in payload["error"]


@pytest.mark.anyio
class TestUpdateAiAgentBlankFields:
    """Cover blank name (line 325) and blank repo_uuid (line 327) guards."""

    async def test_blank_name_returns_error(
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
                    "name": "  ",
                    "repo_uuid": "repo-1",
                    "instruction": "Do things",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                },
            )
        mock_pipefy_client.update_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "name" in payload["error"]

    async def test_blank_repo_uuid_returns_error(
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
                    "name": "Agent",
                    "repo_uuid": "  ",
                    "instruction": "Do things",
                    "behaviors": [minimal_behavior_dict(name="B1")],
                },
            )
        mock_pipefy_client.update_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "repo_uuid" in payload["error"]


@pytest.mark.anyio
class TestValidateAiAgentBehaviorsErrorPaths:
    """Cover pipe fetch timeout, pipe fetch error, blank pipe_id, pydantic validation,
    start_form_fields, relations child/parent, target pipe fetch, and cross-pipe fields."""

    async def test_blank_pipe_id_returns_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {"pipe_id": "  ", "behaviors": [minimal_behavior_dict()]},
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "blank" in payload["error"].lower()

    async def test_pydantic_validation_failure(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Invalid behavior dict fails BehaviorInput validation (lines 523-524)."""
        bad_behavior = {"name": "X"}  # missing required fields
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {"pipe_id": "1", "behaviors": [bad_behavior]},
            )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["valid"] is False
        assert len(payload["problems"]) > 0

    async def test_pipe_fetch_timeout(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Timeout during get_pipe raises error (lines 538-541)."""
        mock_pipefy_client.get_pipe.side_effect = asyncio.TimeoutError()
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {"pipe_id": "123", "behaviors": [minimal_behavior_dict()]},
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "timed out" in payload["error"].lower()

    async def test_pipe_fetch_generic_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Generic error during get_pipe (lines 542-543)."""
        mock_pipefy_client.get_pipe.side_effect = RuntimeError("db down")
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {"pipe_id": "123", "behaviors": [minimal_behavior_dict()]},
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "db down" in payload["error"]

    async def test_start_form_fields_collected(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Start form fields are included in validation (lines 559-561)."""
        mock_pipefy_client.get_pipe.return_value = {
            "pipe": {
                "phases": [{"id": "ph-1", "fields": []}],
                "start_form_fields": [{"id": "sf-1"}],
            }
        }
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        behavior = _behavior_update_card_on_pipe(pipe_id="1", field_id="sf-1")
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {"pipe_id": "1", "behaviors": [behavior]},
            )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["valid"] is True
        assert payload["problems"] == []

    async def test_relations_children_and_parents_collected(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Child and parent relations are collected (lines 572-578).

        When pipeId targets a related pipe, no 'not a related pipe' problem appears.
        We mock the target pipe fetch so cross-pipe field checks also pass.
        """
        mock_pipefy_client.get_pipe.side_effect = [
            _pipe_graph_with_field(),
            {
                "pipe": {
                    "phases": [{"id": "tp-1", "fields": [{"id": "f1"}]}],
                    "start_form_fields": [],
                }
            },
        ]
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [{"child": {"id": "200"}}],
            "parents": [{"parent": {"id": "300"}}],
        }
        behavior = {
            "name": "Connected",
            "event_id": "card_created",
            "actionParams": {
                "aiBehaviorParams": {
                    "instruction": "go",
                    "actionsAttributes": [
                        {
                            "name": "cc",
                            "actionType": "create_connected_card",
                            "metadata": {
                                "pipeId": "200",
                                "fieldsAttributes": [
                                    {
                                        "fieldId": "f1",
                                        "inputMode": "fill_with_ai",
                                        "value": "",
                                    }
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

    async def test_target_pipe_fetch_for_cross_pipe_fields(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Cross-pipe target pipe is fetched and fields validated (lines 604-631)."""
        mock_pipefy_client.get_pipe.side_effect = [
            _pipe_graph_with_field(),
            {
                "pipe": {
                    "phases": [{"id": "tp-1", "fields": [{"id": "tf-1"}]}],
                    "start_form_fields": [{"id": "tf-2"}],
                }
            },
        ]
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [{"child": {"id": "999"}}],
            "parents": [],
        }
        behavior = {
            "name": "Cross",
            "event_id": "card_created",
            "actionParams": {
                "aiBehaviorParams": {
                    "instruction": "go",
                    "actionsAttributes": [
                        {
                            "name": "cc",
                            "actionType": "create_connected_card",
                            "metadata": {
                                "pipeId": "999",
                                "fieldsAttributes": [
                                    {
                                        "fieldId": "tf-1",
                                        "inputMode": "fill_with_ai",
                                        "value": "",
                                    }
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
        # Field tf-1 exists on target pipe, so valid
        assert payload["valid"] is True

    async def test_target_pipe_fetch_failure_adds_warning(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Failure to fetch target pipe adds a warning (lines 627-634)."""
        mock_pipefy_client.get_pipe.side_effect = [
            _pipe_graph_with_field(),
            RuntimeError("target pipe fetch failed"),
        ]
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [{"child": {"id": "999"}}],
            "parents": [],
        }
        behavior = {
            "name": "Cross",
            "event_id": "card_created",
            "actionParams": {
                "aiBehaviorParams": {
                    "instruction": "go",
                    "actionsAttributes": [
                        {
                            "name": "cc",
                            "actionType": "create_connected_card",
                            "metadata": {
                                "pipeId": "999",
                                "fieldsAttributes": [
                                    {
                                        "fieldId": "some-field",
                                        "inputMode": "fill_with_ai",
                                        "value": "",
                                    }
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
        assert any("999" in w for w in payload["warnings"])


@pytest.mark.anyio
class TestEnrichWithValidation:
    """Cover _enrich_with_validation internal paths via update_ai_agent error flow."""

    async def test_record_not_saved_no_pipe_id_in_behaviors(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """When behaviors have no pipeId, enrichment skips validation (line 97)."""
        mock_pipefy_client.update_ai_agent.side_effect = TransportQueryError(
            "RECORD_NOT_SAVED", errors=[{"message": "RECORD_NOT_SAVED"}]
        )
        behavior_no_pipe = {
            "name": "Move",
            "event_id": "card_created",
            "actionParams": {
                "aiBehaviorParams": {
                    "instruction": "go",
                    "actionsAttributes": [
                        {
                            "name": "m",
                            "actionType": "move_card",
                            "metadata": {"destinationPhaseId": "ph-1"},
                        },
                    ],
                }
            },
        }
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_agent",
                {
                    "uuid": "agent-uuid",
                    "name": "Agent",
                    "repo_uuid": "repo-1",
                    "instruction": "Do things",
                    "behaviors": [behavior_no_pipe],
                },
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "RECORD_NOT_SAVED" in payload["error"]
        # No pipe_id found, so no validation suffix
        mock_pipefy_client.get_pipe.assert_not_called()

    async def test_record_not_saved_enrichment_exception_falls_back(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """When pipe fetch fails during enrichment, falls back (lines 152-153)."""
        mock_pipefy_client.update_ai_agent.side_effect = TransportQueryError(
            "RECORD_NOT_SAVED", errors=[{"message": "RECORD_NOT_SAVED"}]
        )
        mock_pipefy_client.get_pipe.side_effect = RuntimeError("unreachable")
        behavior = _behavior_update_card_on_pipe(
            pipe_id="306996636", field_id="425829426"
        )
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_agent",
                {
                    "uuid": "agent-uuid",
                    "name": "Agent",
                    "repo_uuid": "repo-1",
                    "instruction": "Do things",
                    "behaviors": [behavior],
                },
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "RECORD_NOT_SAVED" in payload["error"]
        # Falls back to standard enrichment, no validation suffix
        assert "Validation found problems" not in payload["error"]
        assert "pipe-specific restriction" not in payload["error"]

    async def test_record_not_saved_with_start_form_fields_and_relations(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Enrichment collects start_form_fields and parent relations (lines 114-116, 126-134)."""
        mock_pipefy_client.update_ai_agent.side_effect = TransportQueryError(
            "RECORD_NOT_SAVED", errors=[{"message": "RECORD_NOT_SAVED"}]
        )
        mock_pipefy_client.get_pipe.return_value = {
            "pipe": {
                "phases": [{"id": "ph-1", "fields": []}],
                "start_form_fields": [{"id": "sf-100"}],
            }
        }
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [{"child": {"id": "child-1"}}],
            "parents": [{"parent": {"id": "parent-1"}}],
        }
        behavior = _behavior_update_card_on_pipe(pipe_id="306996636", field_id="sf-100")
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_agent",
                {
                    "uuid": "agent-uuid",
                    "name": "Agent",
                    "repo_uuid": "repo-1",
                    "instruction": "Do things",
                    "behaviors": [behavior],
                },
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "RECORD_NOT_SAVED" in payload["error"]
        # sf-100 is valid (in start_form_fields), so payload should pass validation
        assert "pipe-specific restriction" in payload["error"]

    async def test_record_not_saved_relations_fetch_fails_still_validates(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """When relations fetch fails in enrichment, validation still runs (lines 133-134)."""
        mock_pipefy_client.update_ai_agent.side_effect = TransportQueryError(
            "RECORD_NOT_SAVED", errors=[{"message": "RECORD_NOT_SAVED"}]
        )
        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field(
            field_id="425829426", phase_id="ph-1"
        )
        mock_pipefy_client.get_pipe_relations.side_effect = RuntimeError("no relations")
        behavior = _behavior_update_card_on_pipe(
            pipe_id="306996636", field_id="425829426"
        )
        async with client_session as session:
            result = await session.call_tool(
                "update_ai_agent",
                {
                    "uuid": "agent-uuid",
                    "name": "Agent",
                    "repo_uuid": "repo-1",
                    "instruction": "Do things",
                    "behaviors": [behavior],
                },
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "RECORD_NOT_SAVED" in payload["error"]
        # Field is valid, relations failed, still validates with related_pipe_ids=None
        assert "pipe-specific restriction" in payload["error"]


@pytest.mark.anyio
async def test_get_ai_agent_tools_have_read_only_hint(client_session):
    async with client_session as session:
        listed = await session.list_tools()
    by_name = {t.name: t for t in listed.tools}
    for name in ("get_ai_agent", "get_ai_agents", "validate_ai_agent_behaviors"):
        tool = by_name[name]
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
