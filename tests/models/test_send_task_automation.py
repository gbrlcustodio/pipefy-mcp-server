"""Tests for CreateSendTaskAutomationInput Pydantic model."""

import pytest
from pydantic import ValidationError

from pipefy_mcp.models import CreateSendTaskAutomationInput


@pytest.mark.unit
def test_create_send_task_automation_input_valid_minimal():
    inp = CreateSendTaskAutomationInput(
        pipe_id="123",
        name="Test",
        event_id="card_created",
        task_title="Do this",
        recipients="a@b.com",
    )
    assert inp.pipe_id == "123"
    assert inp.name == "Test"
    assert inp.event_id == "card_created"
    assert inp.task_title == "Do this"
    assert inp.recipients == "a@b.com"
    assert inp.event_params is None
    assert inp.condition is None


@pytest.mark.unit
def test_create_send_task_automation_input_pipe_id_int_coerced():
    inp = CreateSendTaskAutomationInput(
        pipe_id=12345,
        name="Test",
        event_id="card_created",
        task_title="T",
        recipients="a@b.com",
    )
    assert inp.pipe_id == "12345"


@pytest.mark.unit
@pytest.mark.parametrize(
    "field_name,bad_value,kwargs",
    [
        (
            "name",
            "",
            {
                "pipe_id": "1",
                "event_id": "card_created",
                "task_title": "T",
                "recipients": "a@b.com",
            },
        ),
        (
            "name",
            "   ",
            {
                "pipe_id": "1",
                "event_id": "card_created",
                "task_title": "T",
                "recipients": "a@b.com",
            },
        ),
        (
            "task_title",
            "",
            {
                "pipe_id": "1",
                "name": "N",
                "event_id": "card_created",
                "recipients": "a@b.com",
            },
        ),
        (
            "recipients",
            "",
            {
                "pipe_id": "1",
                "name": "N",
                "event_id": "card_created",
                "task_title": "T",
            },
        ),
        (
            "recipients",
            "  ",
            {
                "pipe_id": "1",
                "name": "N",
                "event_id": "card_created",
                "task_title": "T",
            },
        ),
    ],
)
def test_create_send_task_automation_input_rejects_blank_fields(
    field_name, bad_value, kwargs
):
    with pytest.raises(ValidationError) as exc_info:
        CreateSendTaskAutomationInput(**{field_name: bad_value, **kwargs})
    assert (
        field_name in str(exc_info.value).lower()
        or field_name.replace("_", " ") in str(exc_info.value).lower()
    )


@pytest.mark.unit
def test_create_send_task_automation_input_rejects_blank_pipe_id():
    with pytest.raises(ValidationError):
        CreateSendTaskAutomationInput(
            pipe_id="",
            name="Test",
            event_id="card_created",
            task_title="T",
            recipients="a@b.com",
        )


@pytest.mark.unit
def test_create_send_task_automation_input_rejects_whitespace_only_pipe_id():
    with pytest.raises(ValidationError):
        CreateSendTaskAutomationInput(
            pipe_id="   ",
            name="Test",
            event_id="card_created",
            task_title="T",
            recipients="a@b.com",
        )


@pytest.mark.unit
def test_create_send_task_automation_input_rejects_scheduler_event_id():
    with pytest.raises(ValidationError) as exc_info:
        CreateSendTaskAutomationInput(
            pipe_id="1",
            name="Test",
            event_id="scheduler",
            task_title="T",
            recipients="a@b.com",
        )
    msg = str(exc_info.value)
    assert "send_a_task" in msg


@pytest.mark.unit
def test_create_send_task_automation_input_rejects_scheduler_case_insensitive_trimmed():
    with pytest.raises(ValidationError) as exc_info:
        CreateSendTaskAutomationInput(
            pipe_id="1",
            name="Test",
            event_id=" Scheduler ",
            task_title="T",
            recipients="a@b.com",
        )
    assert "send_a_task" in str(exc_info.value)


@pytest.mark.unit
def test_create_send_task_automation_input_optional_pass_through():
    inp = CreateSendTaskAutomationInput(
        pipe_id="1",
        name="N",
        event_id="card_created",
        task_title="T",
        recipients="a@b.com",
        event_params={"to_phase_id": "123"},
        condition={"expressions": []},
    )
    assert inp.event_params == {"to_phase_id": "123"}
    assert inp.condition == {"expressions": []}
