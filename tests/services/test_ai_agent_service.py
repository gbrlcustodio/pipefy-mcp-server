"""Unit tests for AiAgentService."""

import copy
import re
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from gql.transport.exceptions import TransportQueryError

from pipefy_mcp.models.ai_agent import CreateAiAgentInput, UpdateAiAgentInput
from pipefy_mcp.services.pipefy.ai_agent_service import (
    AiAgentService,
    inject_reference_ids,
)
from pipefy_mcp.services.pipefy.base_client import unwrap_relay_connection_nodes
from pipefy_mcp.services.pipefy.queries.ai_agent_queries import (
    DELETE_AI_AGENT_MUTATION,
    GET_AI_AGENT_QUERY,
    GET_AI_AGENTS_QUERY,
)
from pipefy_mcp.settings import PipefySettings

UUID_PATTERN = re.compile(r"%\{action:([a-f0-9-]{36})\}")


def _make_behavior_dict(instruction="", actions=None):
    result = {
        "name": "Test Behavior",
        "actionId": "ai_behavior",
        "active": True,
        "eventId": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": instruction,
                "actionsAttributes": actions or [],
                "referencedFieldIds": [],
                "dataSourceIds": [],
            }
        },
    }
    return result


def _make_action_dict(name="Move card", action_type="move_card"):
    return {"name": name, "actionType": action_type, "metadata": {}}


_MOCK_SETTINGS = PipefySettings(
    graphql_url="https://api.pipefy.com/graphql",
    oauth_url="https://auth.pipefy.com/oauth/token",
    oauth_client="test-client",
    oauth_secret="test-secret",
)


def _create_mock_service(execute_return=None):
    """Create an AiAgentService with mocked execute_query."""
    service = AiAgentService(settings=_MOCK_SETTINGS)
    service.execute_query = AsyncMock(
        return_value=execute_return or {"createAiAgent": {"agent": {"uuid": "abc-123"}}}
    )
    return service


@pytest.mark.unit
def test_inject_reference_ids_single_behavior_single_action():
    """1 behavior with 1 action: output has exactly 1 UUID in referenceId and 1 %{action:...} in instruction."""
    action = _make_action_dict()
    behavior = _make_behavior_dict(instruction="Do something", actions=[action])
    behaviors = [behavior]

    result = inject_reference_ids(behaviors)

    assert len(result) == 1
    out_behavior = result[0]
    out_actions = out_behavior["actionParams"]["aiBehaviorParams"]["actionsAttributes"]
    assert len(out_actions) == 1
    ref_id = out_actions[0]["referenceId"]
    assert ref_id is not None
    instruction = out_behavior["actionParams"]["aiBehaviorParams"]["instruction"]
    placeholders = UUID_PATTERN.findall(instruction)
    assert len(placeholders) == 1
    assert placeholders[0] == ref_id


@pytest.mark.unit
def test_inject_reference_ids_two_behaviors_two_actions_each():
    """2 behaviors with 2 actions each: output has 4 unique UUIDs total."""
    action1 = _make_action_dict(name="Move", action_type="move_card")
    action2 = _make_action_dict(name="Comment", action_type="add_comment")
    behavior1 = _make_behavior_dict(instruction="First", actions=[action1, action2])
    behavior2 = _make_behavior_dict(instruction="Second", actions=[action1, action2])
    behaviors = [behavior1, behavior2]

    result = inject_reference_ids(behaviors)

    all_ref_ids = []
    for b in result:
        for a in b["actionParams"]["aiBehaviorParams"]["actionsAttributes"]:
            all_ref_ids.append(a["referenceId"])
        placeholders = UUID_PATTERN.findall(
            b["actionParams"]["aiBehaviorParams"]["instruction"]
        )
        all_ref_ids.extend(placeholders)
    assert len(set(all_ref_ids)) == 4
    for b in result:
        ref_ids = [
            a["referenceId"]
            for a in b["actionParams"]["aiBehaviorParams"]["actionsAttributes"]
        ]
        instruction = b["actionParams"]["aiBehaviorParams"]["instruction"]
        placeholders = UUID_PATTERN.findall(instruction)
        for rid in ref_ids:
            assert rid in placeholders


@pytest.mark.unit
def test_inject_reference_ids_generates_valid_uuid_v4():
    """Generated referenceId is a valid UUID v4 string."""
    action = _make_action_dict()
    behavior = _make_behavior_dict(actions=[action])

    result = inject_reference_ids([behavior])

    ref_id = result[0]["actionParams"]["aiBehaviorParams"]["actionsAttributes"][0][
        "referenceId"
    ]
    uuid.UUID(ref_id, version=4)


@pytest.mark.unit
def test_inject_reference_ids_preserves_existing_instruction():
    """Output instruction contains original text plus %{action:...} placeholder(s)."""
    action = _make_action_dict()
    behavior = _make_behavior_dict(
        instruction="Do something important", actions=[action]
    )

    result = inject_reference_ids([behavior])

    instruction = result[0]["actionParams"]["aiBehaviorParams"]["instruction"]
    assert "Do something important" in instruction
    assert UUID_PATTERN.search(instruction) is not None


@pytest.mark.unit
def test_inject_reference_ids_does_not_mutate_input():
    """Original input list is unchanged; returned list is a deep copy."""
    action = _make_action_dict()
    behavior = _make_behavior_dict(instruction="Test", actions=[action])
    input_list = [behavior]
    input_copy = copy.deepcopy(input_list)

    result = inject_reference_ids(input_list)

    assert input_list == input_copy
    assert result is not input_list


@pytest.mark.unit
def test_inject_reference_ids_no_actions_returns_behavior_unchanged():
    """Behavior with actionsAttributes: [] or missing returns unchanged."""
    behavior_empty = _make_behavior_dict(instruction="Empty", actions=[])
    behavior_missing = {
        "name": "Test",
        "actionId": "ai_behavior",
        "active": True,
        "eventId": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "No actions",
                "referencedFieldIds": [],
                "dataSourceIds": [],
            }
        },
    }

    result_empty = inject_reference_ids([behavior_empty])
    result_missing = inject_reference_ids([behavior_missing])

    assert (
        result_empty[0]["actionParams"]["aiBehaviorParams"]["actionsAttributes"] == []
    )
    assert result_empty[0]["actionParams"]["aiBehaviorParams"]["instruction"] == "Empty"
    assert (
        "actionsAttributes" not in behavior_missing["actionParams"]["aiBehaviorParams"]
    )
    assert (
        result_missing[0]["actionParams"]["aiBehaviorParams"]["instruction"]
        == "No actions"
    )


@pytest.mark.unit
def test_inject_reference_ids_no_ai_behavior_params_returns_behavior_unchanged():
    """Behavior with action_params but no aiBehaviorParams passes through unchanged."""
    behavior = {
        "name": "Test",
        "actionId": "ai_behavior",
        "active": True,
        "eventId": "card_created",
        "actionParams": {},
    }

    result = inject_reference_ids([behavior])

    assert result[0]["actionParams"] == {}
    assert "aiBehaviorParams" not in result[0]["actionParams"]


@pytest.mark.unit
def test_inject_reference_ids_instruction_with_existing_placeholders():
    """Instruction with existing %{action:old-uuid} still gets new placeholders for current actions."""
    action = _make_action_dict()
    behavior = _make_behavior_dict(
        instruction="Old %{action:00000000-0000-4000-8000-000000000001}",
        actions=[action],
    )

    result = inject_reference_ids([behavior])

    instruction = result[0]["actionParams"]["aiBehaviorParams"]["instruction"]
    ref_id = result[0]["actionParams"]["aiBehaviorParams"]["actionsAttributes"][0][
        "referenceId"
    ]
    assert ref_id != "00000000-0000-4000-8000-000000000001"
    assert f"%{{action:{ref_id}}}" in instruction


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_agent_calls_execute_query_with_correct_variables():
    """create_agent calls execute_query with createAiAgent mutation and correct variables."""
    service = _create_mock_service(
        {"createAiAgent": {"agent": {"uuid": "new-uuid-123"}}}
    )
    inp = CreateAiAgentInput(name="My Agent", repo_uuid="repo-456")

    result = await service.create_agent(inp)

    service.execute_query.assert_called_once()
    call_args = service.execute_query.call_args
    variables = call_args[0][1]

    assert variables["agent"]["name"] == "My Agent"
    assert variables["agent"]["repoUuid"] == "repo-456"
    assert result["agent_uuid"] == "new-uuid-123"
    assert "AI Agent created successfully" in result["message"]
    assert "new-uuid-123" in result["message"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_agent_returns_success_format():
    """create_agent returns agent_uuid and message in success format."""
    service = _create_mock_service({"createAiAgent": {"agent": {"uuid": "xyz-789"}}})
    inp = CreateAiAgentInput(name="Test", repo_uuid="repo-1")

    result = await service.create_agent(inp)

    assert result == {
        "agent_uuid": "xyz-789",
        "message": "AI Agent created successfully. UUID: xyz-789",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_agent_calls_execute_query_with_correct_variables():
    """update_agent calls execute_query with updateAiAgent mutation and correct variables."""
    service = _create_mock_service({"updateAiAgent": {"agent": {"uuid": "agent-uuid"}}})
    inp = UpdateAiAgentInput(
        uuid="agent-uuid",
        name="Updated Agent",
        repo_uuid="repo-456",
        instruction="Do things",
        data_source_ids=["ds1"],
        behaviors=[{"name": "B1", "event_id": "card_created"}],
    )

    result = await service.update_agent(inp)

    service.execute_query.assert_called_once()
    call_args = service.execute_query.call_args
    variables = call_args[0][1]

    assert variables["uuid"] == "agent-uuid"
    assert variables["agent"]["name"] == "Updated Agent"
    assert variables["agent"]["repoUuid"] == "repo-456"
    assert variables["agent"]["instruction"] == "Do things"
    assert variables["agent"]["dataSourceIds"] == ["ds1"]
    assert len(variables["agent"]["behaviors"]) == 1
    assert result["agent_uuid"] == "agent-uuid"
    assert "AI Agent updated successfully" in result["message"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_agent_calls_inject_reference_ids():
    """update_agent calls inject_reference_ids before building the payload."""
    service = _create_mock_service({"updateAiAgent": {"agent": {"uuid": "agent-uuid"}}})
    inp = UpdateAiAgentInput(
        uuid="agent-uuid",
        name="Agent",
        repo_uuid="repo-1",
        behaviors=[{"name": "B1", "event_id": "card_created"}],
    )

    with patch(
        "pipefy_mcp.services.pipefy.ai_agent_service.inject_reference_ids",
        wraps=inject_reference_ids,
    ) as mock_inject:
        await service.update_agent(inp)
        mock_inject.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_agent_propagates_execute_query_error():
    """create_agent propagates errors when execute_query raises."""
    service = _create_mock_service()
    service.execute_query = AsyncMock(side_effect=ValueError("GraphQL error"))
    inp = CreateAiAgentInput(name="Test", repo_uuid="repo-1")

    with pytest.raises(ValueError, match="GraphQL error"):
        await service.create_agent(inp)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_agent_propagates_execute_query_error():
    """update_agent propagates errors when execute_query raises."""
    service = _create_mock_service()
    service.execute_query = AsyncMock(side_effect=RuntimeError("Network error"))
    inp = UpdateAiAgentInput(
        uuid="agent-uuid",
        name="Agent",
        repo_uuid="repo-1",
        behaviors=[{"name": "B1", "event_id": "card_created"}],
    )

    with pytest.raises(RuntimeError, match="Network error"):
        await service.update_agent(inp)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_agent_missing_uuid_returns_clear_error():
    """create_agent returns clear error when API response missing agent.uuid."""
    service = _create_mock_service({"createAiAgent": {}})
    inp = CreateAiAgentInput(name="Test", repo_uuid="repo-1")

    with pytest.raises(ValueError, match="agent.*uuid|unexpected.*payload"):
        await service.create_agent(inp)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_agent_missing_uuid_returns_clear_error():
    """update_agent returns clear error when API response missing agent.uuid."""
    service = _create_mock_service({"updateAiAgent": {"agent": {}}})
    inp = UpdateAiAgentInput(
        uuid="agent-uuid",
        name="Agent",
        repo_uuid="repo-1",
        behaviors=[{"name": "B1", "event_id": "card_created"}],
    )

    with pytest.raises(ValueError, match="agent.*uuid|unexpected.*payload"):
        await service.update_agent(inp)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_toggle_agent_status_enable_calls_execute_query():
    """toggle_agent_status(active=True) calls execute_query with correct variables and returns activation message."""
    service = _create_mock_service({"updateAiAgentStatus": {"success": True}})

    result = await service.toggle_agent_status("agent-uuid", True)

    service.execute_query.assert_called_once()
    call_args = service.execute_query.call_args
    variables = call_args[0][1]
    assert variables["uuid"] == "agent-uuid"
    assert variables["active"] is True
    assert result == {"success": True, "message": "AI Agent activated successfully."}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_toggle_agent_status_disable_returns_correct_message():
    """toggle_agent_status(active=False) returns deactivation message."""
    service = _create_mock_service({"updateAiAgentStatus": {"success": True}})

    result = await service.toggle_agent_status("agent-uuid", False)

    assert result == {"success": True, "message": "AI Agent deactivated successfully."}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_toggle_agent_status_propagates_error():
    """toggle_agent_status propagates errors when execute_query raises."""
    service = _create_mock_service()
    service.execute_query = AsyncMock(side_effect=RuntimeError("Network error"))

    with pytest.raises(RuntimeError, match="Network error"):
        await service.toggle_agent_status("agent-uuid", True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_toggle_agent_status_api_returns_failure():
    """toggle_agent_status raises ValueError when API returns success=False."""
    service = _create_mock_service({"updateAiAgentStatus": {"success": False}})

    with pytest.raises(ValueError, match="failed|unexpected"):
        await service.toggle_agent_status("agent-uuid", True)


@pytest.mark.unit
def test_unwrap_relay_connection_nodes_skips_invalid_edges():
    conn = {"edges": [{"node": {"id": "1"}}, {"x": 1}, {"node": "not-a-dict"}]}
    assert unwrap_relay_connection_nodes(conn) == [{"id": "1"}]
    assert unwrap_relay_connection_nodes({}) == []
    assert unwrap_relay_connection_nodes(None) == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agent_success():
    agent_payload = {
        "uuid": "agent-1",
        "name": "Assistant",
        "instruction": "Help users",
        "disabledAt": None,
        "needReview": False,
    }
    service = _create_mock_service({"aiAgent": agent_payload})

    result = await service.get_agent("agent-1")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is GET_AI_AGENT_QUERY
    assert variables == {"uuid": "agent-1"}
    assert result == agent_payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agent_returns_empty_when_ai_agent_null():
    service = _create_mock_service({"aiAgent": None})

    result = await service.get_agent("missing")

    assert result == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agent_transport_error():
    service = AiAgentService(settings=_MOCK_SETTINGS)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_agent("agent-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agents_success():
    rows = [{"uuid": "a1", "name": "N1"}, {"uuid": "a2", "name": "N2"}]
    connection = {"edges": [{"node": row} for row in rows]}
    service = _create_mock_service({"aiAgents": connection})

    result = await service.get_agents("repo-uuid-99")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is GET_AI_AGENTS_QUERY
    assert variables == {"repoUuid": "repo-uuid-99"}
    assert result == rows


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agents_transport_error():
    service = AiAgentService(settings=_MOCK_SETTINGS)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "missing"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_agents("repo-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_agent_success():
    service = _create_mock_service({"deleteAiAgent": {"success": True}})

    result = await service.delete_agent("agent-to-delete")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_AI_AGENT_MUTATION
    assert variables == {"uuid": "agent-to-delete"}
    assert result == {"success": True}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_agent_transport_error():
    service = AiAgentService(settings=_MOCK_SETTINGS)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "gone"}])
    )
    with pytest.raises(TransportQueryError):
        await service.delete_agent("agent-1")
