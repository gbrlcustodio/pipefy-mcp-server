"""Tests for CreateAiAutomationInput and UpdateAiAutomationInput Pydantic models."""

import pytest
from _shared.fixture_ids import EXAMPLE_FIELD_INTERNAL_ID
from pydantic import ValidationError

from pipefy_sdk.models.ai_automation import (
    DEFAULT_CONDITION,
    AutomationConditionInput,
    AutomationEventParamsInput,
    CreateAiAutomationInput,
    UpdateAiAutomationInput,
)


@pytest.mark.unit
def test_event_params_input_parses_all_declared_fields_from_wire():
    """Every declared inputField parses from its wire spelling (mixed casing)."""
    wire = {
        "kindOfSla": "Late",
        "fromPhaseId": "1",
        "inPhaseId": "2",
        "to_phase_id": "3",
        "triggerAutomationId": "4",
        "triggerFieldIds": ["5", "6"],
    }
    params = AutomationEventParamsInput.model_validate(wire)
    assert params.kind_of_sla == "Late"
    assert params.from_phase_id == "1"
    assert params.in_phase_id == "2"
    assert params.to_phase_id == "3"
    assert params.trigger_automation_id == "4"
    assert params.trigger_field_ids == ["5", "6"]
    # Dumps back to the exact declared wire names.
    assert params.model_dump(by_alias=True, exclude_none=True) == wire


@pytest.mark.unit
def test_event_params_input_accepts_python_names_via_populate_by_name():
    """populate_by_name lets snake_case python names in; dump normalizes to wire."""
    params = AutomationEventParamsInput(from_phase_id="10", trigger_field_ids=["11"])
    assert params.model_dump(by_alias=True, exclude_none=True) == {
        "fromPhaseId": "10",
        "triggerFieldIds": ["11"],
    }


@pytest.mark.unit
def test_event_params_input_passes_unknown_keys_through_verbatim():
    """extra='allow' round-trips sibling/unknown keys (GET responses carry extras)."""
    params = AutomationEventParamsInput.model_validate(
        {"to_phase_id": "3", "someNewField": "x"}
    )
    dumped = params.model_dump(by_alias=True, exclude_none=True)
    assert dumped["to_phase_id"] == "3"
    assert dumped["someNewField"] == "x"


@pytest.mark.unit
def test_create_ai_automation_input_requires_name_event_id_pipe_id_prompt_field_ids():
    """CreateAiAutomationInput requires name, event_id, pipe_id, prompt, field_ids."""
    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="123",
        prompt=f"Summarize the card %{{{EXAMPLE_FIELD_INTERNAL_ID}}}",
        field_ids=["133"],
    )
    assert inp.name == "My Automation"
    assert inp.event_id == "card_created"
    assert inp.pipe_id == "123"
    assert inp.prompt == f"Summarize the card %{{{EXAMPLE_FIELD_INTERNAL_ID}}}"
    assert inp.field_ids == ["133"]


@pytest.mark.unit
def test_create_ai_automation_input_skills_ids_defaults_to_empty_list():
    """CreateAiAutomationInput skills_ids defaults to empty list."""
    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="123",
        prompt="Summarize %{133}",
        field_ids=["133"],
    )
    assert inp.skills_ids == []


@pytest.mark.unit
def test_create_ai_automation_input_condition_defaults_to_placeholder():
    """CreateAiAutomationInput condition defaults to placeholder structure."""
    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="123",
        prompt="Summarize %{133}",
        field_ids=["133"],
    )
    assert inp.condition.model_dump(mode="python") == DEFAULT_CONDITION
    inp2 = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="123",
        prompt="Summarize %{133}",
        field_ids=["133"],
    )
    assert inp.condition is not inp2.condition


@pytest.mark.unit
def test_create_ai_automation_input_condition_explicit_override():
    """CreateAiAutomationInput uses caller-provided condition when passed."""
    custom = {
        "expressions": [
            {"structure_id": 1, "field_address": "f", "op": "x", "value": "y"}
        ],
        "expressions_structure": [[1]],
    }
    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="123",
        prompt="Summarize %{133}",
        field_ids=["133"],
        condition=custom,
    )
    assert inp.condition.model_dump(mode="python") == custom


@pytest.mark.unit
def test_create_ai_automation_input_condition_partial_arbitrary_keys_round_trip():
    """Partial condition dict does not populate unset ``expressions`` / ``expressions_structure``."""
    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="123",
        prompt="Summarize %{133}",
        field_ids=["133"],
        condition={"foo": "bar"},
    )
    dumped = inp.condition.model_dump(
        mode="python", exclude_unset=True, exclude_none=True
    )
    assert dumped == {"foo": "bar"}
    assert "expressions" not in dumped
    assert "expressions_structure" not in dumped


@pytest.mark.unit
def test_create_ai_automation_input_condition_partial_expressions_structure_only():
    """Caller may send only ``expressions_structure`` without default empty ``expressions``."""
    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="123",
        prompt="Summarize %{133}",
        field_ids=["133"],
        condition={"expressions_structure": [[1]]},
    )
    dumped = inp.condition.model_dump(
        mode="python", exclude_unset=True, exclude_none=True
    )
    assert dumped == {"expressions_structure": [[1]]}
    assert "expressions" not in dumped


@pytest.mark.unit
def test_create_ai_automation_input_field_ids_rejects_empty_list():
    """CreateAiAutomationInput rejects empty field_ids."""
    with pytest.raises(ValidationError):
        CreateAiAutomationInput(
            name="My Automation",
            event_id="card_created",
            pipe_id="123",
            prompt="Summarize %{133}",
            field_ids=[],
        )


@pytest.mark.unit
def test_create_ai_automation_input_field_ids_values_must_be_strings():
    """CreateAiAutomationInput field_ids values must be strings."""
    with pytest.raises(ValidationError):
        CreateAiAutomationInput(
            name="My Automation",
            event_id="card_created",
            pipe_id="123",
            prompt="Summarize %{133}",
            field_ids=[133],
        )


@pytest.mark.unit
def test_create_ai_automation_input_field_ids_accepts_strings():
    """CreateAiAutomationInput accepts string field_ids."""
    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="123",
        prompt="Summarize %{133}",
        field_ids=["133", "456"],
    )
    assert inp.field_ids == ["133", "456"]


@pytest.mark.unit
@pytest.mark.parametrize("name", ["", "   ", "\n\t  "])
def test_create_ai_automation_input_rejects_blank_or_whitespace_name(name):
    """CreateAiAutomationInput rejects empty or whitespace-only name."""
    with pytest.raises(ValidationError):
        CreateAiAutomationInput(
            name=name,
            event_id="card_created",
            pipe_id="123",
            prompt="Summarize %{133}",
            field_ids=["133"],
        )


@pytest.mark.unit
@pytest.mark.parametrize("prompt", ["", "   ", "\n\t  "])
def test_create_ai_automation_input_rejects_blank_or_whitespace_prompt(prompt):
    """CreateAiAutomationInput rejects empty or whitespace-only prompt."""
    with pytest.raises(ValidationError):
        CreateAiAutomationInput(
            name="My Automation",
            event_id="card_created",
            pipe_id="123",
            prompt=prompt,
            field_ids=["133"],
        )


@pytest.mark.unit
def test_create_ai_automation_input_rejects_scheduler_event_id():
    """CreateAiAutomationInput rejects event_id 'scheduler' (blacklisted)."""
    with pytest.raises(ValidationError):
        CreateAiAutomationInput(
            name="My Automation",
            event_id="scheduler",
            pipe_id="123",
            prompt="Summarize %{133}",
            field_ids=["133"],
        )


@pytest.mark.unit
def test_create_ai_automation_input_event_params_defaults_to_none():
    """CreateAiAutomationInput event_params defaults to None when omitted."""
    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="123",
        prompt="Summarize %{133}",
        field_ids=["133"],
    )
    assert inp.event_params is None


@pytest.mark.unit
def test_create_ai_automation_input_event_params_pass_through():
    """CreateAiAutomationInput stores event_params as-is."""
    params = {"to_phase_id": "phase-42"}
    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_moved",
        pipe_id="123",
        prompt="Summarize %{133}",
        field_ids=["133"],
        event_params=params,
    )
    assert inp.event_params is not None
    assert inp.event_params.to_phase_id == "phase-42"
    assert inp.event_params.model_dump(by_alias=True, exclude_none=True) == params


@pytest.mark.unit
def test_update_ai_automation_input_requires_automation_id():
    """UpdateAiAutomationInput requires automation_id."""
    inp = UpdateAiAutomationInput(automation_id="456")
    assert inp.automation_id == "456"


@pytest.mark.unit
def test_update_ai_automation_input_accepts_optional_fields():
    """UpdateAiAutomationInput accepts optional name, active, prompt, field_ids, condition."""
    inp = UpdateAiAutomationInput(
        automation_id="456",
        name="Updated Name",
        active=False,
        prompt="New prompt %{133}",
        field_ids=["133", "789"],
        condition={"expressions": [], "expressions_structure": []},
    )
    assert inp.automation_id == "456"
    assert inp.name == "Updated Name"
    assert inp.active is False
    assert inp.prompt == "New prompt %{133}"
    assert inp.field_ids == ["133", "789"]
    assert isinstance(inp.condition, AutomationConditionInput)
    assert inp.condition.model_dump(mode="python") == {
        "expressions": [],
        "expressions_structure": [],
    }


@pytest.mark.unit
def test_update_ai_automation_input_minimal():
    """UpdateAiAutomationInput accepts only automation_id."""
    inp = UpdateAiAutomationInput(automation_id="456")
    assert inp.automation_id == "456"
    assert inp.name is None
    assert inp.active is None
    assert inp.prompt is None
    assert inp.field_ids is None
    assert inp.event_params is None
    assert inp.condition is None


@pytest.mark.unit
def test_update_ai_automation_input_event_params_pass_through():
    """UpdateAiAutomationInput stores event_params when provided."""
    params = {"to_phase_id": "phase-99"}
    inp = UpdateAiAutomationInput(automation_id="456", event_params=params)
    assert inp.event_params is not None
    assert inp.event_params.to_phase_id == "phase-99"
    assert inp.event_params.model_dump(by_alias=True, exclude_none=True) == params


@pytest.mark.unit
@pytest.mark.parametrize("event_id", ["", "   ", "\n\t  "])
def test_create_ai_automation_input_rejects_blank_or_whitespace_event_id(event_id):
    """CreateAiAutomationInput rejects empty or whitespace-only event_id."""
    with pytest.raises(ValidationError):
        CreateAiAutomationInput(
            name="My Automation",
            event_id=event_id,
            pipe_id="123",
            prompt="Summarize %{133}",
            field_ids=["133"],
        )


@pytest.mark.unit
def test_update_ai_automation_input_field_ids_rejects_empty_list():
    """UpdateAiAutomationInput rejects empty field_ids when provided."""
    with pytest.raises(ValidationError):
        UpdateAiAutomationInput(automation_id="456", field_ids=[])


@pytest.mark.unit
def test_create_ai_automation_input_rejects_prompt_without_field_reference():
    """CreateAiAutomationInput rejects prompt that has no %{...} field reference."""
    with pytest.raises(ValidationError, match="prompt must reference at least one"):
        CreateAiAutomationInput(
            name="My Automation",
            event_id="card_created",
            pipe_id="123",
            prompt="Summarize this card",
            field_ids=["133"],
        )


@pytest.mark.unit
def test_create_ai_automation_input_accepts_prompt_with_field_reference():
    """CreateAiAutomationInput accepts prompt containing %{internal_id}."""
    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="123",
        prompt=f"Summarize: %{{{EXAMPLE_FIELD_INTERNAL_ID}}}",
        field_ids=["133"],
    )
    assert f"%{{{EXAMPLE_FIELD_INTERNAL_ID}}}" in inp.prompt


@pytest.mark.unit
def test_update_ai_automation_input_rejects_prompt_without_field_reference():
    """UpdateAiAutomationInput rejects prompt without %{...} when provided."""
    with pytest.raises(ValidationError, match="prompt must reference at least one"):
        UpdateAiAutomationInput(automation_id="456", prompt="Just summarize")


@pytest.mark.unit
def test_update_ai_automation_input_accepts_prompt_with_field_reference():
    """UpdateAiAutomationInput accepts prompt with %{internal_id}."""
    inp = UpdateAiAutomationInput(automation_id="456", prompt="Summarize %{133}")
    assert "%{133}" in inp.prompt


@pytest.mark.unit
def test_update_ai_automation_input_accepts_none_prompt():
    """UpdateAiAutomationInput allows None prompt (field not being updated)."""
    inp = UpdateAiAutomationInput(automation_id="456")
    assert inp.prompt is None
