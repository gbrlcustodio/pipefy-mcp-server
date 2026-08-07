"""Tests for AI Agent MCP tools."""

import asyncio
import copy
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from _mcp_compat import (
    create_connected_server_and_client_session as create_client_session,
)
from _shared.ai_agent_test_payloads import behavior_with_action, minimal_behavior_dict
from _shared.fixture_ids import (
    EXAMPLE_FIELD_INTERNAL_ID,
    EXAMPLE_FIELD_SLUG,
    make_field_id,
    make_pipe_id,
)
from pipefy_sdk import PipefyGraphQLError
from pipefy_sdk.models.ai_agent import CreateAiAgentInput, UpdateAiAgentInput

from pipefy_mcp.core.tool_error_envelope import tool_error_message
from pipefy_mcp.tools.ai_agent_tools import AiAgentTools
from tools.conftest import (
    assert_invalid_arguments_envelope,
    build_tool_test_server,
)


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
        "AI Agent Tools Test", AiAgentTools.register, mock_pipefy_client
    )


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
            "disabled_at": None,
        }
        mock_pipefy_client.update_ai_agent.return_value = {
            "agent_uuid": "abc-123",
            "message": "updated",
            "disabled_at": None,
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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is True
        update_arg = mock_pipefy_client.update_ai_agent.call_args[0][0]
        assert isinstance(update_arg, UpdateAiAgentInput)
        assert update_arg.data_source_ids == []
        create_arg = mock_pipefy_client.create_ai_agent.call_args[0][0]
        assert isinstance(create_arg, CreateAiAgentInput)
        assert create_arg.disabled_at is None

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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert isinstance(tool_error_message(payload), str)
        assert "GraphQL error" in tool_error_message(payload)
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
        assert result.is_error is False
        mock_pipefy_client.create_ai_agent.assert_not_called()
        mock_pipefy_client.update_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    async def test_rejects_legacy_capability_shape(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        behavior = minimal_behavior_dict(name="B1")
        behavior["actionParams"]["aiBehaviorParams"]["capabilitiesAttributes"] = [
            {"type": "advanced_ocr"}
        ]
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Purpose",
                    "behaviors": [behavior],
                },
            )
        assert result.is_error is False
        mock_pipefy_client.create_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "capabilityType" in str(payload["error"])

    async def test_rejects_both_provider_ids(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        behavior = minimal_behavior_dict(name="B1")
        abp = behavior["actionParams"]["aiBehaviorParams"]
        abp["providerId"] = "prov-1"
        abp["systemProviderId"] = "sys-1"
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "Agent",
                    "repo_uuid": "repo-456",
                    "instruction": "Purpose",
                    "behaviors": [behavior],
                },
            )
        assert result.is_error is False
        mock_pipefy_client.create_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "at most one" in str(payload["error"])

    async def test_create_and_configure_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        envelope_flag,
    ):
        mock_pipefy_client.create_ai_agent.return_value = {
            "agent_uuid": "new-uuid",
            "message": "created",
            "disabled_at": None,
        }
        mock_pipefy_client.update_ai_agent.return_value = {
            "agent_uuid": "new-uuid",
            "message": "updated",
            "disabled_at": None,
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
        assert result.is_error is False
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
        if envelope_flag:
            assert payload["data"]["agent_uuid"] == "new-uuid"
            assert payload["data"]["disabled_at"] is None
            assert payload["data"]["active"] is True
        else:
            assert payload["agent_uuid"] == "new-uuid"
            assert payload["disabled_at"] is None
            assert payload["active"] is True

    async def test_partial_failure_returns_uuid_and_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        stub_disabled_at = "2026-08-04T12:00:00+00:00"
        mock_pipefy_client.create_ai_agent.return_value = {
            "agent_uuid": "created-uuid",
            "message": "AI Agent created successfully. UUID: created-uuid",
            "disabled_at": stub_disabled_at,
            "active": False,
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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert payload["agent_uuid"] == "created-uuid"
        assert payload["disabled_at"] == stub_disabled_at
        assert payload["active"] is False
        assert "error" in payload
        err_msg = tool_error_message(payload)
        assert "update failed" in err_msg
        assert "toggle_ai_agent_status" in err_msg
        assert "disabled" in err_msg.lower()

    async def test_update_passes_disabled_at_when_provided(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
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
                    "disabled_at": stub_disabled_at,
                },
            )
        assert result.is_error is False
        update_arg = mock_pipefy_client.update_ai_agent.call_args[0][0]
        assert isinstance(update_arg, UpdateAiAgentInput)
        assert update_arg.disabled_at == stub_disabled_at
        assert update_arg.preserve_disabled_at is True
        payload = extract_payload(result)
        assert payload["success"] is True

    async def test_graphql_error_extracts_messages(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.create_ai_agent.side_effect = PipefyGraphQLError(
            [{"message": "permission denied"}]
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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "permission denied" in tool_error_message(payload)
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
        assert result.is_error is False
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
        assert result.is_error is False
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
        assert result.is_error is False
        mock_pipefy_client.create_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "repo_uuid" in tool_error_message(payload)

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
        assert result.is_error is False
        mock_pipefy_client.create_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "name" in tool_error_message(payload)


@pytest.mark.anyio
class TestUpdateAiAgent:
    async def test_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        legacy_envelope,
    ):
        mock_pipefy_client.update_ai_agent.return_value = {
            "agent_uuid": "agent-uuid",
            "message": "AI Agent updated successfully. UUID: agent-uuid",
            "disabled_at": None,
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
        payload = extract_payload(result)
        assert payload == {
            "success": True,
            "agent_uuid": "agent-uuid",
            "message": "AI Agent updated successfully. UUID: agent-uuid",
            "disabled_at": None,
            "active": True,
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
        assert result.is_error is False
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
        assert result.is_error is False
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
        assert result.is_error is False
        mock_pipefy_client.update_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "uuid" in tool_error_message(payload)

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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    async def test_record_not_saved_with_valid_payload_shows_pipe_restriction(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.update_ai_agent.side_effect = PipefyGraphQLError(
            [{"message": "RECORD_NOT_SAVED"}]
        )
        pipe_id = make_pipe_id()
        field_id = make_field_id()
        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field(
            field_id=field_id, phase_id="ph-1"
        )
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        behavior = _behavior_update_card_on_pipe(pipe_id=pipe_id, field_id=field_id)
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
        assert "RECORD_NOT_SAVED" in tool_error_message(payload)
        assert "pipe-specific restriction" in tool_error_message(payload)
        assert "Do NOT retry" in tool_error_message(payload)

    async def test_record_not_saved_with_invalid_payload_shows_problems(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.update_ai_agent.side_effect = PipefyGraphQLError(
            [{"message": "RECORD_NOT_SAVED"}]
        )
        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field(
            field_id="100", phase_id="ph-1"
        )
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        behavior = _behavior_update_card_on_pipe(pipe_id=make_pipe_id(), field_id="999")
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
        assert "RECORD_NOT_SAVED" in tool_error_message(payload)
        assert "Validation found problems" in tool_error_message(payload)
        assert '"999"' in tool_error_message(payload)

    async def test_record_not_saved_resolves_field_refs_for_enrichment(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Error-path enrichment uses resolved field ids (not raw slug tokens)."""

        pipe_id = make_pipe_id()
        field_id = make_field_id()

        async def fake_resolve(_client, behaviors):
            out = copy.deepcopy(behaviors)
            for b in out:
                ap = b.get("actionParams") or {}
                abp = ap.get("aiBehaviorParams") or {}
                for aa in abp.get("actionsAttributes") or []:
                    meta = aa.get("metadata") or {}
                    for fa in meta.get("fieldsAttributes") or []:
                        if fa.get("fieldId") == "email_slug":
                            fa["fieldId"] = field_id
            return out

        mock_pipefy_client.update_ai_agent.side_effect = PipefyGraphQLError(
            [{"message": "RECORD_NOT_SAVED"}]
        )
        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field(
            field_id=field_id, phase_id="ph-1"
        )
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        behavior = _behavior_update_card_on_pipe(pipe_id=pipe_id, field_id="email_slug")
        with patch(
            "pipefy_mcp.tools.ai_agent_tools.resolve_and_populate_field_refs",
            new=AsyncMock(side_effect=fake_resolve),
        ) as resolve_m:
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

        resolve_m.assert_awaited_once()
        msg = tool_error_message(extract_payload(result))
        assert "RECORD_NOT_SAVED" in msg
        assert "pipe-specific restriction" in msg
        assert "email_slug" not in msg

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
        assert "timeout" in tool_error_message(payload)
        assert "pipe-specific restriction" not in tool_error_message(payload)
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
        assert result.is_error is False
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
        assert result.is_error is False
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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert isinstance(tool_error_message(payload), str)

    async def test_graphql_error_extracts_message(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.toggle_ai_agent_status.side_effect = PipefyGraphQLError(
            [{"message": "Agent is locked"}]
        )
        async with client_session as session:
            result = await session.call_tool(
                "toggle_ai_agent_status",
                {"uuid": "agent-uuid", "active": True},
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "locked" in tool_error_message(payload)


def _behavior_update_card_on_pipe(
    pipe_id: str | None = None,
    field_id: str | None = None,
):
    resolved_pipe_id = pipe_id if pipe_id is not None else make_pipe_id()
    resolved_field_id = field_id if field_id is not None else make_field_id()
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
                            "pipeId": resolved_pipe_id,
                            "fieldsAttributes": [
                                {
                                    "fieldId": resolved_field_id,
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


def _pipe_graph_with_field(
    field_id: str | None = None,
    phase_id: str = "ph-1",
):
    resolved_field_id = field_id if field_id is not None else make_field_id()
    return {
        "pipe": {
            "phases": [
                {
                    "id": phase_id,
                    "fields": [{"id": resolved_field_id}],
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
        pipe_id = make_pipe_id()
        field_id = make_field_id()
        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field(
            field_id=field_id
        )
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {
                    "pipe_id": pipe_id,
                    "behaviors": [
                        _behavior_update_card_on_pipe(
                            pipe_id=pipe_id, field_id=field_id
                        )
                    ],
                    "strict_unknown_action_types": True,
                },
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["valid"] is True
        assert payload["problems"] == []
        assert payload["warnings"] == []
        mock_pipefy_client.get_pipe.assert_awaited_once_with(pipe_id)
        mock_pipefy_client.get_pipe_relations.assert_awaited_once_with(pipe_id)

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
        mock_pipefy_client.get_pipe_relations.side_effect = PipefyGraphQLError(
            [{"message": "denied"}]
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
        pipe_id = make_pipe_id()
        field_id = make_field_id()
        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field(
            field_id=field_id
        )
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {
                    "pipe_id": pipe_id,
                    "behaviors": [
                        _behavior_update_card_on_pipe(pipe_id=pipe_id, field_id="999")
                    ],
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
        from _shared.ai_agent_test_payloads import behavior_with_action

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
        legacy_envelope,
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
        assert result.is_error is False
        mock_pipefy_client.get_ai_agent.assert_awaited_once_with("agent-1")
        payload = extract_payload(result)
        assert payload == {"success": True, "agent": agent}

    async def test_success_unified_envelope(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        unified_envelope,
    ):
        """Flag=True — agent payload sits under ``data.agent`` (ADR-0001)."""
        agent = {"uuid": "agent-1", "name": "Assistant"}
        mock_pipefy_client.get_ai_agent.return_value = agent
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_agent",
                {"uuid": "agent-1"},
            )
        payload = extract_payload(result)
        assert payload == {"success": True, "data": {"agent": agent}}

    async def test_success_with_behaviors(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        legacy_envelope,
    ):
        """Behaviors from the API are included verbatim in the MCP tool response."""
        from _shared.ai_agent_test_payloads import mock_agent_with_behaviors

        agent = mock_agent_with_behaviors()
        mock_pipefy_client.get_ai_agent.return_value = agent
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_agent",
                {"uuid": "agent-with-behaviors"},
            )
        assert result.is_error is False
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
        legacy_envelope,
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
        assert result.is_error is False
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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "not found" in tool_error_message(payload).lower()

    async def test_blank_uuid_returns_error_payload(
        self, client_session, mock_pipefy_client, extract_payload
    ):
        async with client_session as session:
            result = await session.call_tool("get_ai_agent", {"uuid": "  "})
        mock_pipefy_client.get_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "blank" in tool_error_message(payload).lower()

    async def test_graphql_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_ai_agent.side_effect = PipefyGraphQLError(
            [{"message": "not found"}]
        )
        async with client_session as session:
            result = await session.call_tool("get_ai_agent", {"uuid": "missing"})
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "not found" in tool_error_message(payload)


@pytest.mark.anyio
class TestGetAiAgents:
    async def test_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        legacy_envelope,
    ):
        agents = [{"uuid": "a1", "name": "One"}]
        mock_pipefy_client.get_ai_agents.return_value = agents
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_agents",
                {"repo_uuid": "pipe-uuid-9"},
            )
        assert result.is_error is False
        mock_pipefy_client.get_ai_agents.assert_awaited_once_with("pipe-uuid-9")
        payload = extract_payload(result)
        assert payload == {"success": True, "agents": agents}

    async def test_success_unified_envelope(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        unified_envelope,
    ):
        """Flag=True — agents list sits under ``data.agents`` (ADR-0001)."""
        agents = [{"uuid": "a1"}, {"uuid": "a2"}]
        mock_pipefy_client.get_ai_agents.return_value = agents
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_agents",
                {"repo_uuid": "pipe-uuid-9"},
            )
        payload = extract_payload(result)
        assert payload == {"success": True, "data": {"agents": agents}}

    async def test_blank_repo_uuid_returns_error_payload(
        self, client_session, mock_pipefy_client, extract_payload
    ):
        async with client_session as session:
            result = await session.call_tool("get_ai_agents", {"repo_uuid": ""})
        mock_pipefy_client.get_ai_agents.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "blank" in tool_error_message(payload).lower()

    async def test_graphql_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_ai_agents.side_effect = PipefyGraphQLError(
            [{"message": "denied"}]
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_agents",
                {"repo_uuid": "repo-x"},
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "denied" in tool_error_message(payload)


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
        assert result.is_error is False
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
        assert "success=false" in tool_error_message(payload).lower()

    async def test_blank_uuid_returns_error_payload(
        self, client_session, mock_pipefy_client, extract_payload
    ):
        async with client_session as session:
            result = await session.call_tool("delete_ai_agent", {"uuid": "\t"})
        mock_pipefy_client.delete_ai_agent.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "blank" in tool_error_message(payload).lower()

    async def test_graphql_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.delete_ai_agent.side_effect = PipefyGraphQLError(
            [{"message": "gone"}]
        )
        async with client_session as session:
            result = await session.call_tool(
                "delete_ai_agent",
                {"uuid": "bad", "confirm": True},
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "gone" in tool_error_message(payload)

    async def test_has_destructive_hint(self, client_session):
        async with client_session as session:
            listed = await session.list_tools()
        delete_tool = next(t for t in listed.tools if t.name == "delete_ai_agent")
        assert delete_tool.annotations is not None
        assert delete_tool.annotations.destructive_hint is True
        assert delete_tool.annotations.read_only_hint is False


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
        assert "server down" in tool_error_message(payload)


@pytest.mark.anyio
class TestGetAiAgentsErrorPaths:
    """Cover get_ai_agents empty-list and GraphQL error paths."""

    async def test_empty_list_returns_success_with_empty_agents(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        legacy_envelope,
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
        assert "boom" in tool_error_message(payload)

    @pytest.mark.parametrize("exc_message", ["", "   "])
    async def test_empty_exception_message_uses_fallback(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        exc_message,
    ):
        mock_pipefy_client.get_ai_agents.side_effect = RuntimeError(exc_message)
        async with client_session as session:
            result = await session.call_tool(
                "get_ai_agents", {"repo_uuid": "pipe-uuid"}
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        message = tool_error_message(payload)
        assert message.strip()
        assert "AI request failed." in message
        assert "do not blind-retry" in message


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
        assert "blank" in tool_error_message(payload).lower()


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
        assert "network" in tool_error_message(payload)


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
        assert "instruction" in tool_error_message(payload)


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
        assert "name" in tool_error_message(payload)

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
        assert "repo_uuid" in tool_error_message(payload)


@pytest.mark.anyio
class TestValidateAiAgentBehaviorsErrorPaths:
    """Cover pipe fetch timeout, pipe fetch error, blank pipe_id, pydantic validation,
    start_form_fields, relations child/parent, target pipe fetch, and cross-pipe fields."""

    async def test_blank_pipe_id_returns_error(
        self,
        client_session,
        mock_pipefy_client,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {"pipe_id": "  ", "behaviors": [minimal_behavior_dict()]},
            )
        assert_invalid_arguments_envelope(result)

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
        assert any(
            "event_id" in p.lower() or "eventid" in p.lower()
            for p in payload["problems"]
        )

    async def test_pydantic_validation_missing_name_hint(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Missing behavior name returns an actionable lead problem."""
        no_name = {"event_id": "card_created"}
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {"pipe_id": "1", "behaviors": [no_name]},
            )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["valid"] is False
        assert any(
            "name" in p.lower() and "behavior" in p.lower() for p in payload["problems"]
        )

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
        assert "timed out" in tool_error_message(payload).lower()

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
        assert "db down" in tool_error_message(payload)

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
        mock_pipefy_client.get_phase_fields = AsyncMock(return_value={"fields": []})
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

    async def test_validate_accepts_start_form_internal_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Regression: fieldId with numeric internal_id must pass when slug also exists."""
        mock_pipefy_client.get_pipe.return_value = {
            "pipe": {
                "phases": [{"id": "ph-1"}],
                "start_form_fields": [
                    {
                        "id": EXAMPLE_FIELD_SLUG,
                        "internal_id": EXAMPLE_FIELD_INTERNAL_ID,
                    },
                ],
            }
        }
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        mock_pipefy_client.get_phase_fields = AsyncMock(return_value={"fields": []})
        behavior = _behavior_update_card_on_pipe(
            pipe_id="1", field_id=EXAMPLE_FIELD_INTERNAL_ID
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

    async def test_move_card_reports_invalid_transition_when_trigger_phase_known(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe.return_value = {
            "pipe": {
                "phases": [
                    {"id": "100", "fields": []},
                    {"id": "200", "fields": []},
                ],
                "start_form_fields": [],
            }
        }
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        mock_pipefy_client.get_phase_allowed_move_targets.return_value = {
            "phase": {
                "id": "100",
                "name": "Doing",
                "cards_can_be_moved_to_phases": [{"id": "200", "name": "Done"}],
            }
        }
        behavior = {
            "name": "After valid lands",
            "event_id": "card_moved",
            "eventParams": {"to_phase_id": "100"},
            "actionParams": {
                "aiBehaviorParams": {
                    "instruction": "move",
                    "actionsAttributes": [
                        {
                            "name": "m",
                            "actionType": "move_card",
                            "metadata": {"destinationPhaseId": "999"},
                        }
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
        assert payload["valid"] is False
        assert any("999" in p for p in payload["problems"])

    async def test_move_card_transition_ok_when_destination_allowed(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.get_pipe.return_value = {
            "pipe": {
                "phases": [{"id": "100", "fields": []}, {"id": "200", "fields": []}],
                "start_form_fields": [],
            }
        }
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }
        mock_pipefy_client.get_phase_allowed_move_targets.return_value = {
            "phase": {
                "id": "100",
                "name": "Doing",
                "cards_can_be_moved_to_phases": [{"id": "200", "name": "Done"}],
            }
        }
        behavior = {
            "name": "Move when landed",
            "event_id": "card_moved",
            "eventParams": {"to_phase_id": "100"},
            "actionParams": {
                "aiBehaviorParams": {
                    "instruction": "move",
                    "actions_attributes": [
                        {
                            "name": "m",
                            "actionType": "move_card",
                            "metadata": {"destinationPhaseId": "200"},
                        }
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
                    "phases": [{"id": "tp-1", "name": "Target phase"}],
                    "start_form_fields": [{"id": "tf-2"}],
                }
            },
        ]
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={"fields": [{"id": "tf-1"}]}
        )
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

    async def test_target_pipe_fetch_max_distinct_pipes_rejected(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        monkeypatch,
    ):
        """Enforces MAX_CROSS_PIPE_FIELD_FETCH on distinct create_connected_card targets."""
        monkeypatch.setattr(
            "pipefy_sdk.ai_preflight.MAX_CROSS_PIPE_FIELD_FETCH",
            1,
            raising=False,
        )
        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field()
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [
                {"child": {"id": "999"}},
                {"child": {"id": "888"}},
            ],
            "parents": [],
        }
        b1 = {
            "name": "Cross1",
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
                        }
                    ],
                }
            },
        }
        b2 = {
            "name": "Cross2",
            "event_id": "card_created",
            "actionParams": {
                "aiBehaviorParams": {
                    "instruction": "go2",
                    "actionsAttributes": [
                        {
                            "name": "cc2",
                            "actionType": "create_connected_card",
                            "metadata": {
                                "pipeId": "888",
                                "fieldsAttributes": [
                                    {
                                        "fieldId": "tf-8",
                                        "inputMode": "fill_with_ai",
                                        "value": "",
                                    }
                                ],
                            },
                        }
                    ],
                }
            },
        }
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {"pipe_id": "1", "behaviors": [b1, b2]},
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "Too many distinct cross-pipe target pipes" in tool_error_message(
            payload
        )

    async def test_target_pipe_fetch_two_targets_parallel_uses_per_pipe_data(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Cross-pipe fetches run in parallel; responses must map by pipe id, not call order."""
        rel = {
            "children": [
                {"child": {"id": "999"}},
                {"child": {"id": "888"}},
            ],
            "parents": [],
        }
        main = _pipe_graph_with_field()
        t999 = {
            "pipe": {
                "phases": [{"id": "tp-1", "fields": [{"id": "tf-1"}]}],
                "start_form_fields": [],
            }
        }
        t888 = {
            "pipe": {
                "phases": [{"id": "tp-2", "fields": [{"id": "tf-88"}]}],
                "start_form_fields": [],
            }
        }

        async def get_pipe_by_id(tpid, *args, **kwargs):
            tpid = str(tpid)
            if tpid == "1":
                return main
            if tpid == "999":
                return t999
            if tpid == "888":
                return t888
            return {"pipe": {}}

        mock_pipefy_client.get_pipe.side_effect = get_pipe_by_id
        mock_pipefy_client.get_pipe_relations.return_value = rel
        b1 = {
            "name": "B1",
            "event_id": "card_created",
            "actionParams": {
                "aiBehaviorParams": {
                    "instruction": "go",
                    "actionsAttributes": [
                        {
                            "name": "cc1",
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
                        }
                    ],
                }
            },
        }
        b2 = {
            "name": "B2",
            "event_id": "card_created",
            "actionParams": {
                "aiBehaviorParams": {
                    "instruction": "go2",
                    "actionsAttributes": [
                        {
                            "name": "cc2",
                            "actionType": "create_connected_card",
                            "metadata": {
                                "pipeId": "888",
                                "fieldsAttributes": [
                                    {
                                        "fieldId": "tf-88",
                                        "inputMode": "fill_with_ai",
                                        "value": "",
                                    }
                                ],
                            },
                        }
                    ],
                }
            },
        }
        async with client_session as session:
            result = await session.call_tool(
                "validate_ai_agent_behaviors",
                {"pipe_id": "1", "behaviors": [b1, b2]},
            )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["valid"] is True


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
        mock_pipefy_client.update_ai_agent.side_effect = PipefyGraphQLError(
            [{"message": "RECORD_NOT_SAVED"}]
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
        assert "RECORD_NOT_SAVED" in tool_error_message(payload)
        # No pipe_id found, so no validation suffix
        mock_pipefy_client.get_pipe.assert_not_called()

    async def test_record_not_saved_enrichment_exception_falls_back(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """When pipe fetch fails during enrichment, falls back (lines 152-153)."""
        mock_pipefy_client.update_ai_agent.side_effect = PipefyGraphQLError(
            [{"message": "RECORD_NOT_SAVED"}]
        )
        mock_pipefy_client.get_pipe.side_effect = RuntimeError("unreachable")
        pipe_id = make_pipe_id()
        field_id = make_field_id()
        behavior = _behavior_update_card_on_pipe(pipe_id=pipe_id, field_id=field_id)
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
        assert "RECORD_NOT_SAVED" in tool_error_message(payload)
        # Falls back to standard enrichment, no validation suffix
        assert "Validation found problems" not in tool_error_message(payload)
        assert "pipe-specific restriction" not in tool_error_message(payload)

    async def test_record_not_saved_with_start_form_fields_and_relations(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Enrichment collects start_form_fields and parent relations (lines 114-116, 126-134)."""
        mock_pipefy_client.update_ai_agent.side_effect = PipefyGraphQLError(
            [{"message": "RECORD_NOT_SAVED"}]
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
        behavior = _behavior_update_card_on_pipe(
            pipe_id=make_pipe_id(), field_id="sf-100"
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
        assert "RECORD_NOT_SAVED" in tool_error_message(payload)
        # sf-100 is valid (in start_form_fields), so payload should pass validation
        assert "pipe-specific restriction" in tool_error_message(payload)

    async def test_record_not_saved_relations_fetch_fails_still_validates(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """When relations fetch fails in enrichment, validation still runs (lines 133-134)."""
        mock_pipefy_client.update_ai_agent.side_effect = PipefyGraphQLError(
            [{"message": "RECORD_NOT_SAVED"}]
        )
        pipe_id = make_pipe_id()
        field_id = make_field_id()
        mock_pipefy_client.get_pipe.return_value = _pipe_graph_with_field(
            field_id=field_id, phase_id="ph-1"
        )
        mock_pipefy_client.get_pipe_relations.side_effect = RuntimeError("no relations")
        behavior = _behavior_update_card_on_pipe(pipe_id=pipe_id, field_id=field_id)
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
        assert "RECORD_NOT_SAVED" in tool_error_message(payload)
        # Field is valid, relations failed, still validates with related_pipe_ids=None
        assert "pipe-specific restriction" in tool_error_message(payload)


@pytest.mark.anyio
async def test_get_ai_agent_tools_have_read_only_hint(client_session):
    async with client_session as session:
        listed = await session.list_tools()
    by_name = {t.name: t for t in listed.tools}
    for name in ("get_ai_agent", "get_ai_agents", "validate_ai_agent_behaviors"):
        tool = by_name[name]
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True


@pytest.mark.anyio
class TestFetchPipeValidationContext:
    """Unit tests for the fetch_pipe_validation_context helper."""

    async def test_extracts_fields_phases_and_relations(self, mock_pipefy_client):
        from pipefy_mcp.tools.ai_tool_helpers import fetch_pipe_validation_context

        mock_pipefy_client.get_pipe.return_value = {
            "pipe": {
                "phases": [
                    {
                        "id": "ph-1",
                        "fields": [{"id": "f1"}, {"id": "f2", "internal_id": "f2i"}],
                    },
                    {
                        "id": "ph-2",
                        "fields": [{"id": "f3"}],
                    },
                ],
                "start_form_fields": [{"id": "sf-1"}, {"internal_id": "sf-2"}],
            }
        }
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [{"child": {"id": "child-10"}}],
            "parents": [{"parent": {"id": "parent-20"}}],
        }
        mock_pipefy_client.get_phase_fields = AsyncMock(
            side_effect=[
                {"fields": [{"id": "f3"}]},
                {"fields": []},
            ]
        )

        (
            field_ids,
            phase_ids,
            related_pipe_ids,
            fetch_warnings,
        ) = await fetch_pipe_validation_context(mock_pipefy_client, "42")

        assert phase_ids == {"ph-1", "ph-2"}
        assert "f1" in field_ids
        assert "f2" in field_ids
        assert "f2i" in field_ids
        assert "f3" in field_ids
        assert "sf-1" in field_ids
        assert "sf-2" in field_ids
        assert related_pipe_ids == {"child-10", "parent-20"}
        assert fetch_warnings == []
        mock_pipefy_client.get_pipe.assert_awaited_once_with("42")
        mock_pipefy_client.get_pipe_relations.assert_awaited_once_with("42")
        mock_pipefy_client.get_phase_fields.assert_not_awaited()

    async def test_relations_failure_returns_none(self, mock_pipefy_client):
        from pipefy_mcp.tools.ai_tool_helpers import fetch_pipe_validation_context

        mock_pipefy_client.get_pipe.return_value = {
            "pipe": {
                "phases": [{"id": "ph-1", "fields": [{"id": "f1"}]}],
                "start_form_fields": [],
            }
        }
        mock_pipefy_client.get_pipe_relations.side_effect = RuntimeError("denied")
        mock_pipefy_client.get_phase_fields = AsyncMock(return_value={"fields": []})

        (
            field_ids,
            phase_ids,
            related_pipe_ids,
            fetch_warnings,
        ) = await fetch_pipe_validation_context(mock_pipefy_client, "99")

        assert phase_ids == {"ph-1"}
        assert field_ids == {"f1"}
        assert related_pipe_ids is None
        assert fetch_warnings == []

    async def test_get_pipe_error_propagates(self, mock_pipefy_client):
        from pipefy_mcp.tools.ai_tool_helpers import fetch_pipe_validation_context

        mock_pipefy_client.get_pipe.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError, match="db down"):
            await fetch_pipe_validation_context(mock_pipefy_client, "1")

    async def test_get_pipe_timeout_propagates(self, mock_pipefy_client):
        from pipefy_mcp.tools.ai_tool_helpers import fetch_pipe_validation_context

        mock_pipefy_client.get_pipe.side_effect = asyncio.TimeoutError()

        with pytest.raises(asyncio.TimeoutError):
            await fetch_pipe_validation_context(mock_pipefy_client, "1")

    async def test_empty_pipe_returns_empty_sets(self, mock_pipefy_client):
        from pipefy_mcp.tools.ai_tool_helpers import fetch_pipe_validation_context

        mock_pipefy_client.get_pipe.return_value = {"pipe": {}}
        mock_pipefy_client.get_pipe_relations.return_value = {
            "children": [],
            "parents": [],
        }

        (
            field_ids,
            phase_ids,
            related_pipe_ids,
            fetch_warnings,
        ) = await fetch_pipe_validation_context(mock_pipefy_client, "1")

        assert field_ids == set()
        assert phase_ids == set()
        assert related_pipe_ids == set()
        assert fetch_warnings == []


## ---------------------------------------------------------------------------
## Cross-pipe PERMISSION_DENIED enrichment at tool level
## ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestCreateAiAgentPermissionEnrichment:
    async def test_permission_denied_enriches_error_with_membership_guidance(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        mock_pipefy_client.create_ai_agent.side_effect = PipefyGraphQLError(
            [
                {
                    "message": "forbidden",
                    "extensions": {"code": "PERMISSION_DENIED"},
                }
            ]
        )
        # get_pipe_members fails for the target pipe (no access)
        mock_pipefy_client.get_pipe_members.side_effect = RuntimeError("no access")
        async with client_session as session:
            result = await session.call_tool(
                "create_ai_agent",
                {
                    "name": "Agent",
                    "repo_uuid": "uuid-1",
                    "instruction": "Do stuff",
                    "behaviors": [minimal_behavior_dict()],
                },
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        # Enrichment message is prepended to the error
        assert "invite_members" in tool_error_message(payload)
        assert "forbidden" in tool_error_message(payload)
