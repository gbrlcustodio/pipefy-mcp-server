"""Pydantic models for Send a Task automation input validation."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, field_validator

from pipefy_mcp.models.validators import NonBlankStr, PipefyId

SEND_TASK_EVENT_ID_BLACKLIST = frozenset({"scheduler"})


def _reject_send_task_blacklisted_event_id(v: str) -> str:
    stripped = v.strip()
    if stripped.lower() in SEND_TASK_EVENT_ID_BLACKLIST:
        raise ValueError(f"event_id '{stripped}' is not allowed for send_a_task")
    return stripped


_SendTaskEventId = Annotated[
    str,
    BeforeValidator(_reject_send_task_blacklisted_event_id),
    Field(description="Trigger event ID; 'scheduler' is not allowed for send_a_task"),
]


class CreateSendTaskAutomationInput(BaseModel):
    """Validated input for creating a Send a Task automation (send_a_task)."""

    pipe_id: PipefyId
    name: NonBlankStr
    event_id: _SendTaskEventId
    task_title: NonBlankStr
    recipients: NonBlankStr
    event_params: dict | None = None
    condition: dict | None = None

    @field_validator("pipe_id")
    @classmethod
    def _strip_pipe_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("pipe_id cannot be blank")
        return stripped
