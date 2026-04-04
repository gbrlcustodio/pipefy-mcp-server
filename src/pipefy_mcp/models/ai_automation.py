"""Pydantic models for AI Automation input validation."""

from __future__ import annotations

import copy
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from pipefy_mcp.models.validators import NonBlankStr

EVENT_ID_BLACKLIST = frozenset({"scheduler"})

DEFAULT_CONDITION = {
    "expressions": [
        {"structure_id": 0, "field_address": "", "operation": "", "value": ""}
    ],
    "expressions_structure": [[0]],
}


def _reject_blacklisted_event_id(v: str) -> str:
    stripped = v.strip()
    if stripped.lower() in EVENT_ID_BLACKLIST:
        raise ValueError(f"event_id '{stripped}' is not allowed for generate_with_ai")
    return stripped


_EventId = Annotated[
    str,
    BeforeValidator(_reject_blacklisted_event_id),
    Field(description="Event ID (e.g. card_created); 'scheduler' is blacklisted"),
]


class CreateAiAutomationInput(BaseModel):
    """Validated input for creating an AI Automation (generate_with_ai)."""

    name: NonBlankStr
    event_id: _EventId
    pipe_id: NonBlankStr
    action_repo_id: NonBlankStr | None = Field(
        default=None,
        description="Pipe ID where the action executes. Defaults to pipe_id when omitted.",
    )
    prompt: NonBlankStr
    field_ids: list[str] = Field(
        min_length=1,
        description="Non-empty list of field internal IDs as strings",
    )
    condition: dict = Field(default_factory=lambda: copy.deepcopy(DEFAULT_CONDITION))


class UpdateAiAutomationInput(BaseModel):
    """Validated input for updating an AI Automation."""

    automation_id: NonBlankStr = Field(description="Automation ID to update")
    name: NonBlankStr | None = None
    active: bool | None = None
    prompt: NonBlankStr | None = None
    field_ids: list[str] | None = Field(default=None, min_length=1)
    condition: dict | None = None
