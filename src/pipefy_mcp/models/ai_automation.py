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
    """Validated input for creating an AI Automation (generate_with_ai).

    Attributes:
        name: Automation name (non-empty, stripped).
        event_id: Event trigger (e.g. card_created); scheduler is blacklisted.
        pipe_id: Pipe ID (event_repo_id / action_repo_id).
        prompt: AI prompt text (non-empty, stripped).
        field_ids: Non-empty list of field internal IDs as strings.
        condition: Optional condition structure; defaults to placeholder.
    """

    name: NonBlankStr
    event_id: _EventId
    pipe_id: NonBlankStr
    prompt: NonBlankStr
    field_ids: list[str] = Field(
        min_length=1,
        description="Non-empty list of field internal IDs as strings",
    )
    condition: dict = Field(default_factory=lambda: copy.deepcopy(DEFAULT_CONDITION))


class UpdateAiAutomationInput(BaseModel):
    """Validated input for updating an AI Automation.

    Attributes:
        automation_id: ID of the automation to update.
        name: Optional new name.
        active: Optional active state.
        prompt: Optional new prompt.
        field_ids: Optional new field IDs.
        condition: Optional new condition.
    """

    automation_id: str = Field(description="Automation ID to update")
    name: NonBlankStr | None = None
    active: bool | None = None
    prompt: NonBlankStr | None = None
    field_ids: list[str] | None = Field(default=None, min_length=1)
    condition: dict | None = None
