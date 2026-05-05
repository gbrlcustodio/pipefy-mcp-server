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
from tests.ai_agent_test_payloads import behavior_with_action, minimal_behavior_dict


def _make_behavior(name="Test Behavior", event_id="card_created"):
    return minimal_behavior_dict(name=name, event_id=event_id)


@pytest.mark.unit
def test_create_ai_agent_input_requires_name_repo_instruction_behaviors():
    inp = CreateAiAgentInput(
        name="My Agent",
        repo_uuid="repo-123",
        instruction="Purpose",
        behaviors=[_make_behavior()],
    )
    assert inp.name == "My Agent"
    assert inp.repo_uuid == "repo-123"
    assert inp.instruction == "Purpose"
    assert len(inp.behaviors) == 1
    assert inp.data_source_ids == []


@pytest.mark.unit
@pytest.mark.parametrize("name", ["", "   ", "\n\t  "])
def test_create_ai_agent_input_rejects_blank_name(name):
    with pytest.raises(ValidationError):
        CreateAiAgentInput(
            name=name,
            repo_uuid="repo-123",
            instruction="Purpose",
            behaviors=[_make_behavior()],
        )


@pytest.mark.unit
@pytest.mark.parametrize("repo_uuid", ["", "   "])
def test_create_ai_agent_input_rejects_blank_repo_uuid(repo_uuid):
    with pytest.raises(ValidationError):
        CreateAiAgentInput(
            name="My Agent",
            repo_uuid=repo_uuid,
            instruction="Purpose",
            behaviors=[_make_behavior()],
        )


@pytest.mark.unit
def test_create_ai_agent_input_strips_name():
    inp = CreateAiAgentInput(
        name="  My Agent  ",
        repo_uuid="repo-123",
        instruction="Purpose",
        behaviors=[_make_behavior()],
    )
    assert inp.name == "My Agent"


@pytest.mark.unit
def test_create_ai_agent_input_rejects_blank_instruction():
    with pytest.raises(ValidationError):
        CreateAiAgentInput(
            name="My Agent",
            repo_uuid="repo-123",
            instruction="   ",
            behaviors=[_make_behavior()],
        )


@pytest.mark.unit
def test_create_ai_agent_input_rejects_empty_behaviors():
    with pytest.raises(ValidationError):
        CreateAiAgentInput(
            name="My Agent",
            repo_uuid="repo-123",
            instruction="Purpose",
            behaviors=[],
        )


@pytest.mark.unit
def test_create_ai_agent_input_rejects_more_than_five_behaviors():
    behaviors = [_make_behavior(name=f"Behavior {i}") for i in range(MAX_BEHAVIORS + 1)]
    with pytest.raises(ValidationError):
        CreateAiAgentInput(
            name="My Agent",
            repo_uuid="repo-123",
            instruction="Purpose",
            behaviors=behaviors,
        )


@pytest.mark.unit
def test_create_ai_agent_input_accepts_data_source_ids():
    inp = CreateAiAgentInput(
        name="My Agent",
        repo_uuid="repo-123",
        instruction="Purpose",
        behaviors=[_make_behavior()],
        data_source_ids=["ds-1", "ds-2"],
    )
    assert inp.data_source_ids == ["ds-1", "ds-2"]


@pytest.mark.unit
def test_behavior_input_requires_name_and_event_id():
    inp = BehaviorInput.model_validate(minimal_behavior_dict())
    assert inp.name == "Test Behavior"
    assert inp.event_id == "card_created"
    assert inp.action_id == ACTION_ID_AI_BEHAVIOR
    assert inp.active is True


@pytest.mark.unit
@pytest.mark.parametrize("name", ["", "   ", "\n\t  "])
def test_behavior_input_rejects_blank_name(name):
    payload = minimal_behavior_dict()
    payload["name"] = name
    with pytest.raises(ValidationError):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
def test_behavior_input_rejects_missing_action_params():
    with pytest.raises(ValidationError, match="actionParams"):
        BehaviorInput(name="Test", event_id="card_created")


@pytest.mark.unit
def test_behavior_input_rejects_empty_actions_attributes():
    payload = minimal_behavior_dict()
    payload["actionParams"]["aiBehaviorParams"]["actionsAttributes"] = []
    with pytest.raises(ValidationError, match="at least one action"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
def test_behavior_input_accepts_condition_and_action_params():
    condition = {"expressions": []}
    payload = minimal_behavior_dict()
    payload["condition"] = condition
    inp = BehaviorInput.model_validate(payload)
    assert inp.condition == condition
    assert inp.action_params is not None
    assert "aiBehaviorParams" in inp.action_params


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


@pytest.mark.unit
def test_behavior_input_accepts_event_params_with_trigger_field_ids():
    payload = minimal_behavior_dict(event_id="field_updated")
    payload["eventParams"] = {"triggerFieldIds": ["425829426"]}
    inp = BehaviorInput.model_validate(payload)
    assert inp.event_params == {"triggerFieldIds": ["425829426"]}


@pytest.mark.unit
def test_behavior_input_accepts_event_params_with_to_phase_id():
    payload = minimal_behavior_dict(event_id="card_moved")
    payload["eventParams"] = {"to_phase_id": "12345678"}
    inp = BehaviorInput.model_validate(payload)
    assert inp.event_params == {"to_phase_id": "12345678"}


@pytest.mark.unit
def test_behavior_input_event_params_included_in_alias_dump():
    payload = minimal_behavior_dict(event_id="field_updated")
    payload["eventParams"] = {"triggerFieldIds": ["425829426"]}
    inp = BehaviorInput.model_validate(payload)
    dumped = inp.model_dump(by_alias=True, exclude_none=True)
    assert dumped["eventParams"] == {"triggerFieldIds": ["425829426"]}
    assert "event_params" not in dumped


@pytest.mark.unit
def test_behavior_input_event_params_defaults_none():
    payload = minimal_behavior_dict()
    inp = BehaviorInput.model_validate(payload)
    assert inp.event_params is None
    dumped = inp.model_dump(by_alias=True, exclude_none=True)
    assert "eventParams" not in dumped


# --- metadata validation per actionType ---

VALID_FIELDS_ATTR = {"fieldId": "425829426", "inputMode": "fill_with_ai", "value": ""}


@pytest.mark.unit
@pytest.mark.parametrize(
    "action_type", ["update_card", "create_card", "create_connected_card"]
)
def test_metadata_valid_for_card_field_actions(action_type):
    metadata = {
        "pipeId": "306996636",
        "fieldsAttributes": [VALID_FIELDS_ATTR],
    }
    payload = behavior_with_action(action_type, metadata)
    inp = BehaviorInput.model_validate(payload)
    action = inp.action_params["aiBehaviorParams"]["actionsAttributes"][0]
    assert action["metadata"]["pipeId"] == "306996636"


@pytest.mark.unit
@pytest.mark.parametrize(
    "action_type", ["update_card", "create_card", "create_connected_card"]
)
def test_metadata_rejects_empty_dict_for_card_field_actions(action_type):
    payload = behavior_with_action(action_type, {})
    with pytest.raises(ValidationError, match="pipeId"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
@pytest.mark.parametrize(
    "action_type", ["update_card", "create_card", "create_connected_card"]
)
def test_metadata_rejects_missing_fields_attributes(action_type):
    payload = behavior_with_action(action_type, {"pipeId": "123"})
    with pytest.raises(ValidationError, match="fieldsAttributes"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
@pytest.mark.parametrize(
    "action_type", ["update_card", "create_card", "create_connected_card"]
)
def test_metadata_rejects_empty_fields_attributes(action_type):
    payload = behavior_with_action(
        action_type, {"pipeId": "123", "fieldsAttributes": []}
    )
    with pytest.raises(ValidationError, match="fieldsAttributes"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
@pytest.mark.parametrize(
    "action_type", ["update_card", "create_card", "create_connected_card"]
)
def test_metadata_rejects_field_entry_missing_field_id(action_type):
    metadata = {
        "pipeId": "123",
        "fieldsAttributes": [{"inputMode": "fill_with_ai", "value": ""}],
    }
    payload = behavior_with_action(action_type, metadata)
    with pytest.raises(ValidationError, match="fieldId"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
@pytest.mark.parametrize(
    "action_type", ["update_card", "create_card", "create_connected_card"]
)
def test_metadata_rejects_field_entry_missing_input_mode(action_type):
    metadata = {
        "pipeId": "123",
        "fieldsAttributes": [{"fieldId": "425829426", "value": ""}],
    }
    payload = behavior_with_action(action_type, metadata)
    with pytest.raises(ValidationError, match="inputMode"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
@pytest.mark.parametrize(
    "action_type", ["update_card", "create_card", "create_connected_card"]
)
def test_metadata_allows_empty_value_in_fields_attributes(action_type):
    metadata = {
        "pipeId": "123",
        "fieldsAttributes": [
            {"fieldId": "1", "inputMode": "fill_with_ai", "value": ""}
        ],
    }
    payload = behavior_with_action(action_type, metadata)
    inp = BehaviorInput.model_validate(payload)
    assert inp.action_params is not None


@pytest.mark.unit
def test_metadata_valid_for_move_card():
    payload = behavior_with_action("move_card", {"destinationPhaseId": "999"})
    inp = BehaviorInput.model_validate(payload)
    action = inp.action_params["aiBehaviorParams"]["actionsAttributes"][0]
    assert action["metadata"]["destinationPhaseId"] == "999"


@pytest.mark.unit
def test_metadata_rejects_empty_dict_for_move_card():
    payload = behavior_with_action("move_card", {})
    with pytest.raises(ValidationError, match="destinationPhaseId"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
def test_metadata_rejects_blank_destination_phase_id_for_move_card():
    payload = behavior_with_action("move_card", {"destinationPhaseId": "  "})
    with pytest.raises(ValidationError, match="destinationPhaseId"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
def test_metadata_passes_through_unknown_action_type():
    payload = behavior_with_action("send_email", {"to": "user@example.com"})
    inp = BehaviorInput.model_validate(payload)
    action = inp.action_params["aiBehaviorParams"]["actionsAttributes"][0]
    assert action["metadata"]["to"] == "user@example.com"


@pytest.mark.unit
def test_metadata_allows_empty_dict_for_unknown_action_type():
    payload = behavior_with_action("send_email", {})
    BehaviorInput.model_validate(payload)


@pytest.mark.unit
def test_metadata_valid_for_create_table_record():
    metadata = {
        "tableId": "tbl-999",
        "fieldsAttributes": [VALID_FIELDS_ATTR],
    }
    payload = behavior_with_action("create_table_record", metadata)
    inp = BehaviorInput.model_validate(payload)
    action = inp.action_params["aiBehaviorParams"]["actionsAttributes"][0]
    assert action["metadata"]["tableId"] == "tbl-999"


@pytest.mark.unit
def test_metadata_rejects_missing_table_id_for_create_table_record():
    payload = behavior_with_action(
        "create_table_record",
        {"fieldsAttributes": [VALID_FIELDS_ATTR]},
    )
    with pytest.raises(ValidationError, match="tableId"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
def test_metadata_rejects_missing_fields_attributes_for_create_table_record():
    payload = behavior_with_action("create_table_record", {"tableId": "tbl-1"})
    with pytest.raises(ValidationError, match="fieldsAttributes"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
def test_metadata_create_table_record_does_not_require_pipe_id():
    metadata = {
        "tableId": "tbl-1",
        "fieldsAttributes": [VALID_FIELDS_ATTR],
    }
    payload = behavior_with_action("create_table_record", metadata)
    BehaviorInput.model_validate(payload)


@pytest.mark.unit
def test_metadata_rejects_field_entry_missing_field_id_for_create_table_record():
    metadata = {
        "tableId": "tbl-1",
        "fieldsAttributes": [{"inputMode": "fill_with_ai", "value": ""}],
    }
    payload = behavior_with_action("create_table_record", metadata)
    with pytest.raises(ValidationError, match="fieldId"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
def test_metadata_valid_for_send_email_template():
    payload = behavior_with_action(
        "send_email_template",
        {"emailTemplateId": "tmpl-1"},
    )
    inp = BehaviorInput.model_validate(payload)
    meta = inp.action_params["aiBehaviorParams"]["actionsAttributes"][0]["metadata"]
    assert meta["emailTemplateId"] == "tmpl-1"


@pytest.mark.unit
def test_metadata_send_email_template_accepts_allow_template_modifications():
    payload = behavior_with_action(
        "send_email_template",
        {"emailTemplateId": "tmpl-1", "allowTemplateModifications": False},
    )
    inp = BehaviorInput.model_validate(payload)
    meta = inp.action_params["aiBehaviorParams"]["actionsAttributes"][0]["metadata"]
    assert meta["allowTemplateModifications"] is False


@pytest.mark.unit
def test_metadata_rejects_missing_email_template_id():
    payload = behavior_with_action("send_email_template", {})
    with pytest.raises(ValidationError, match="emailTemplateId"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
def test_metadata_rejects_blank_email_template_id():
    payload = behavior_with_action("send_email_template", {"emailTemplateId": "  "})
    with pytest.raises(ValidationError, match="emailTemplateId"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
def test_metadata_rejects_non_bool_allow_template_modifications():
    payload = behavior_with_action(
        "send_email_template",
        {"emailTemplateId": "tmpl-1", "allowTemplateModifications": "yes"},
    )
    with pytest.raises(ValidationError, match="allowTemplateModifications"):
        BehaviorInput.model_validate(payload)


@pytest.mark.unit
def test_behavior_input_accepts_capabilities_attributes_on_ai_behavior_params():
    payload = minimal_behavior_dict()
    abp = payload["actionParams"]["aiBehaviorParams"]
    abp["capabilitiesAttributes"] = [{"type": "advanced_ocr"}, {"type": "web_search"}]
    inp = BehaviorInput.model_validate(payload)
    caps = inp.action_params["aiBehaviorParams"]["capabilitiesAttributes"]
    assert caps == [{"type": "advanced_ocr"}, {"type": "web_search"}]


# --- snake_case / camelCase normalization ---


@pytest.mark.unit
def test_behavior_input_accepts_snake_case_keys():
    payload = {
        "name": "Snake Behavior",
        "event_id": "card_created",
        "action_params": {
            "aiBehaviorParams": {
                "instruction": "Test instruction.",
                "actionsAttributes": [
                    {
                        "name": "Update card fields",
                        "actionType": "update_card",
                        "metadata": {
                            "pipeId": "123",
                            "fieldsAttributes": [
                                {
                                    "fieldId": "1",
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
    inp = BehaviorInput.model_validate(payload)
    assert inp.event_id == "card_created"
    assert inp.action_params is not None


@pytest.mark.unit
def test_behavior_input_accepts_camel_case_keys():
    payload = {
        "name": "Camel Behavior",
        "eventId": "card_moved",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "Test instruction.",
                "actionsAttributes": [
                    {
                        "name": "Move",
                        "actionType": "move_card",
                        "metadata": {"destinationPhaseId": "999"},
                    },
                ],
            }
        },
    }
    inp = BehaviorInput.model_validate(payload)
    assert inp.event_id == "card_moved"


@pytest.mark.unit
def test_behavior_input_snake_case_dumps_to_camel_case():
    payload = {
        "name": "Mixed",
        "event_id": "field_updated",
        "event_params": {"triggerFieldIds": ["1"]},
        "action_params": {
            "aiBehaviorParams": {
                "instruction": "Go.",
                "actionsAttributes": [
                    {
                        "name": "Move",
                        "actionType": "move_card",
                        "metadata": {"destinationPhaseId": "5"},
                    },
                ],
            }
        },
    }
    inp = BehaviorInput.model_validate(payload)
    dumped = inp.model_dump(by_alias=True, exclude_none=True)
    assert "eventId" in dumped
    assert "event_id" not in dumped
    assert "eventParams" in dumped
    assert "event_params" not in dumped
    assert "actionParams" in dumped
    assert "action_params" not in dumped
    assert "actionId" in dumped
    assert "action_id" not in dumped
    assert inp.action_params is not None
