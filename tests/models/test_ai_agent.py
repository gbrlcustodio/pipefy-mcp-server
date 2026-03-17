"""Tests for AI Agent Pydantic input validation models."""

import pytest
from pydantic import ValidationError

from pipefy_mcp.models.ai_agent import (
    ACTION_ID_AI_BEHAVIOR,
    MAX_BEHAVIORS,
    BehaviorInput,
    CreateAiAgentInput,
    UpdateAiAgentInput,
)


def _make_behavior(name="Test Behavior", event_id="card_created"):
    return {"name": name, "event_id": event_id}


@pytest.mark.unit
def test_create_ai_agent_input_requires_name_and_repo_uuid():
    inp = CreateAiAgentInput(name="My Agent", repo_uuid="repo-123")
    assert inp.name == "My Agent"
    assert inp.repo_uuid == "repo-123"


@pytest.mark.unit
@pytest.mark.parametrize("name", ["", "   ", "\n\t  "])
def test_create_ai_agent_input_rejects_blank_name(name):
    with pytest.raises(ValidationError):
        CreateAiAgentInput(name=name, repo_uuid="repo-123")


@pytest.mark.unit
@pytest.mark.parametrize("repo_uuid", ["", "   "])
def test_create_ai_agent_input_rejects_blank_repo_uuid(repo_uuid):
    with pytest.raises(ValidationError):
        CreateAiAgentInput(name="My Agent", repo_uuid=repo_uuid)


@pytest.mark.unit
def test_create_ai_agent_input_strips_name():
    inp = CreateAiAgentInput(name="  My Agent  ", repo_uuid="repo-123")
    assert inp.name == "My Agent"


@pytest.mark.unit
def test_behavior_input_requires_name_and_event_id():
    inp = BehaviorInput(name="Test Behavior", event_id="card_created")
    assert inp.name == "Test Behavior"
    assert inp.event_id == "card_created"
    assert inp.action_id == ACTION_ID_AI_BEHAVIOR
    assert inp.active is True


@pytest.mark.unit
@pytest.mark.parametrize("name", ["", "   ", "\n\t  "])
def test_behavior_input_rejects_blank_name(name):
    with pytest.raises(ValidationError):
        BehaviorInput(name=name, event_id="card_created")


@pytest.mark.unit
def test_behavior_input_optional_fields():
    inp = BehaviorInput(name="Test", event_id="card_created")
    assert inp.condition is None
    assert inp.action_params is None


@pytest.mark.unit
def test_behavior_input_accepts_condition_and_action_params():
    condition = {"expressions": []}
    action_params = {"key": "value"}
    inp = BehaviorInput(
        name="Test",
        event_id="card_created",
        condition=condition,
        action_params=action_params,
    )
    assert inp.condition == condition
    assert inp.action_params == action_params


@pytest.mark.unit
def test_update_ai_agent_input_requires_uuid_name_repo_uuid_behaviors():
    inp = UpdateAiAgentInput(
        uuid="agent-123",
        name="My Agent",
        repo_uuid="repo-456",
        behaviors=[_make_behavior()],
    )
    assert inp.uuid == "agent-123"
    assert inp.name == "My Agent"
    assert inp.repo_uuid == "repo-456"
    assert len(inp.behaviors) == 1


@pytest.mark.unit
@pytest.mark.parametrize("uuid_val", ["", "   ", "\n\t  "])
def test_update_ai_agent_input_rejects_blank_uuid(uuid_val):
    with pytest.raises(ValidationError):
        UpdateAiAgentInput(
            uuid=uuid_val,
            name="My Agent",
            repo_uuid="repo-456",
            behaviors=[_make_behavior()],
        )


@pytest.mark.unit
@pytest.mark.parametrize("name", ["", "   ", "\n\t  "])
def test_update_ai_agent_input_rejects_blank_name(name):
    with pytest.raises(ValidationError):
        UpdateAiAgentInput(
            uuid="agent-123",
            name=name,
            repo_uuid="repo-456",
            behaviors=[_make_behavior()],
        )


@pytest.mark.unit
@pytest.mark.parametrize("repo_uuid", ["", "   ", "\n\t  "])
def test_update_ai_agent_input_rejects_blank_repo_uuid(repo_uuid):
    with pytest.raises(ValidationError):
        UpdateAiAgentInput(
            uuid="agent-123",
            name="My Agent",
            repo_uuid=repo_uuid,
            behaviors=[_make_behavior()],
        )


@pytest.mark.unit
def test_update_ai_agent_input_rejects_empty_behaviors():
    with pytest.raises(ValidationError):
        UpdateAiAgentInput(
            uuid="agent-123",
            name="My Agent",
            repo_uuid="repo-456",
            behaviors=[],
        )


@pytest.mark.unit
def test_update_ai_agent_input_rejects_more_than_five_behaviors():
    behaviors = [_make_behavior(name=f"Behavior {i}") for i in range(MAX_BEHAVIORS + 1)]
    with pytest.raises(ValidationError):
        UpdateAiAgentInput(
            uuid="agent-123",
            name="My Agent",
            repo_uuid="repo-456",
            behaviors=behaviors,
        )


@pytest.mark.unit
def test_update_ai_agent_input_accepts_one_behavior():
    inp = UpdateAiAgentInput(
        uuid="agent-123",
        name="My Agent",
        repo_uuid="repo-456",
        behaviors=[_make_behavior()],
    )
    assert len(inp.behaviors) == 1


@pytest.mark.unit
def test_update_ai_agent_input_accepts_three_behaviors():
    inp = UpdateAiAgentInput(
        uuid="agent-123",
        name="My Agent",
        repo_uuid="repo-456",
        behaviors=[
            _make_behavior(name="B1"),
            _make_behavior(name="B2"),
            _make_behavior(name="B3"),
        ],
    )
    assert len(inp.behaviors) == 3


@pytest.mark.unit
def test_update_ai_agent_input_accepts_five_behaviors():
    inp = UpdateAiAgentInput(
        uuid="agent-123",
        name="My Agent",
        repo_uuid="repo-456",
        behaviors=[_make_behavior(name=f"B{i}") for i in range(MAX_BEHAVIORS)],
    )
    assert len(inp.behaviors) == MAX_BEHAVIORS


@pytest.mark.unit
def test_update_ai_agent_input_optional_instruction_defaults_none():
    inp = UpdateAiAgentInput(
        uuid="agent-123",
        name="My Agent",
        repo_uuid="repo-456",
        behaviors=[_make_behavior()],
    )
    assert inp.instruction is None


@pytest.mark.unit
def test_update_ai_agent_input_optional_data_source_ids_defaults_empty():
    inp = UpdateAiAgentInput(
        uuid="agent-123",
        name="My Agent",
        repo_uuid="repo-456",
        behaviors=[_make_behavior()],
    )
    assert inp.data_source_ids == []


@pytest.mark.unit
def test_update_ai_agent_input_accepts_instruction_and_data_source_ids():
    inp = UpdateAiAgentInput(
        uuid="agent-123",
        name="My Agent",
        repo_uuid="repo-456",
        behaviors=[_make_behavior()],
        instruction="Do something",
        data_source_ids=["ds1", "ds2"],
    )
    assert inp.instruction == "Do something"
    assert inp.data_source_ids == ["ds1", "ds2"]
