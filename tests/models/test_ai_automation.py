"""Tests for CreateAiAutomationInput and UpdateAiAutomationInput Pydantic models."""

import pytest
from pydantic import ValidationError

from pipefy_mcp.models.ai_automation import (
    CreateAiAutomationInput,
    UpdateAiAutomationInput,
)

DEFAULT_CONDITION = {
    "expressions": [
        {"structure_id": 0, "field_address": "", "operation": "", "value": ""}
    ],
    "expressions_structure": [[0]],
}


@pytest.mark.unit
def test_create_ai_automation_input_requires_name_event_id_pipe_id_prompt_field_ids():
    """CreateAiAutomationInput requires name, event_id, pipe_id, prompt, field_ids."""
    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="123",
        prompt="Summarize the card",
        field_ids=["133"],
    )
    assert inp.name == "My Automation"
    assert inp.event_id == "card_created"
    assert inp.pipe_id == "123"
    assert inp.prompt == "Summarize the card"
    assert inp.field_ids == ["133"]


@pytest.mark.unit
def test_create_ai_automation_input_skills_ids_defaults_to_empty_list():
    """CreateAiAutomationInput skills_ids defaults to empty list."""
    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="123",
        prompt="Summarize",
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
        prompt="Summarize",
        field_ids=["133"],
    )
    assert inp.condition == DEFAULT_CONDITION


@pytest.mark.unit
def test_create_ai_automation_input_field_ids_rejects_empty_list():
    """CreateAiAutomationInput rejects empty field_ids."""
    with pytest.raises(ValidationError):
        CreateAiAutomationInput(
            name="My Automation",
            event_id="card_created",
            pipe_id="123",
            prompt="Summarize",
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
            prompt="Summarize",
            field_ids=[133],
        )


@pytest.mark.unit
def test_create_ai_automation_input_field_ids_accepts_strings():
    """CreateAiAutomationInput accepts string field_ids."""
    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="123",
        prompt="Summarize",
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
            prompt="Summarize",
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
            prompt="Summarize",
            field_ids=["133"],
        )


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
        prompt="New prompt",
        field_ids=["133", "789"],
        condition={"expressions": [], "expressions_structure": []},
    )
    assert inp.automation_id == "456"
    assert inp.name == "Updated Name"
    assert inp.active is False
    assert inp.prompt == "New prompt"
    assert inp.field_ids == ["133", "789"]
    assert inp.condition == {"expressions": [], "expressions_structure": []}


@pytest.mark.unit
def test_update_ai_automation_input_minimal():
    """UpdateAiAutomationInput accepts only automation_id."""
    inp = UpdateAiAutomationInput(automation_id="456")
    assert inp.automation_id == "456"
    assert inp.name is None
    assert inp.active is None
    assert inp.prompt is None
    assert inp.field_ids is None
    assert inp.condition is None


@pytest.mark.unit
def test_update_ai_automation_input_field_ids_rejects_empty_list():
    """UpdateAiAutomationInput rejects empty field_ids when provided."""
    with pytest.raises(ValidationError):
        UpdateAiAutomationInput(automation_id="456", field_ids=[])
