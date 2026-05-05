"""Pydantic models for AI Automation input validation."""

from __future__ import annotations

import copy
import re
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from pipefy_mcp.models.validators import NonBlankStr

EVENT_ID_BLACKLIST = frozenset({"scheduler"})

FIELD_REF_PATTERN = re.compile(r"%\{[^}]+\}")

# Sent on every create when the caller omits ``condition``. Pipefy's internal
# ``createAutomation`` expects a condition object; omitting the variable can
# differ semantically from an explicit "no user condition" shape. This placeholder
# matches an empty expression list so the API receives a stable payload.
DEFAULT_CONDITION: dict[str, Any] = {
    "expressions": [
        {"structure_id": 0, "field_address": "", "operation": "", "value": ""}
    ],
    "expressions_structure": [[0]],
}


class AutomationConditionInput(BaseModel):
    """Pipefy ``ConditionInput``-shaped payload. Unknown top-level keys are preserved."""

    model_config = ConfigDict(extra="allow")

    expressions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Condition expressions (Pipefy ConditionInput).",
    )
    expressions_structure: list[Any] | None = Field(
        default=None,
        description="Expression grouping indices for Pipefy condition trees.",
    )


class AutomationEventParamsInput(BaseModel):
    """Pipefy automation trigger params (e.g. ``to_phase_id``, ``triggerFieldIds``)."""

    model_config = ConfigDict(extra="allow")


def _default_automation_condition() -> AutomationConditionInput:
    """Fresh placeholder condition (deep copy) for each new create input."""
    return AutomationConditionInput.model_validate(copy.deepcopy(DEFAULT_CONDITION))


def _reject_blacklisted_event_id(v: str) -> str:
    stripped = v.strip()
    if not stripped:
        raise ValueError("event_id must not be blank")
    if stripped.lower() in EVENT_ID_BLACKLIST:
        raise ValueError(f"event_id '{stripped}' is not allowed for generate_with_ai")
    return stripped


def _require_field_reference(v: str) -> str:
    """Validate that the prompt contains at least one ``%{field_id}`` reference.

    Why: the Pipefy API requires the prompt to reference at least one pipe
    field via ``%{internal_id}`` (e.g. ``%{425829426}``).  Without it the API
    returns the opaque error ``"Input parameters are required"``.
    """
    stripped = v.strip()
    if not stripped:
        raise ValueError("prompt must not be blank")
    if not FIELD_REF_PATTERN.search(stripped):
        raise ValueError(
            "prompt must reference at least one pipe field using %{internal_id} "
            "syntax (e.g. 'Summarize: %{425829426}'). "
            "The Pipefy API rejects prompts without field references."
        )
    return stripped


_EventId = Annotated[
    str,
    BeforeValidator(_reject_blacklisted_event_id),
    Field(description="Event ID (e.g. card_created); 'scheduler' is blacklisted"),
]

_AiPrompt = Annotated[
    str,
    BeforeValidator(_require_field_reference),
    Field(
        description=(
            "AI prompt text. Must contain at least one field reference "
            "using %{internal_id} syntax (e.g. 'Summarize: %{425829426}')."
        ),
    ),
]


class CreateAiAutomationInput(BaseModel):
    """Validated input for creating an AI Automation (generate_with_ai).

    When ``condition`` is omitted, it defaults to a deep copy of
    :data:`DEFAULT_CONDITION` so the internal API always receives an explicit
    condition object (see ``docs/tools/automations-and-ai.md``).
    """

    name: NonBlankStr
    event_id: _EventId
    pipe_id: NonBlankStr
    action_repo_id: NonBlankStr | None = Field(
        default=None,
        description="Pipe ID where the action executes. Defaults to pipe_id when omitted.",
    )
    prompt: _AiPrompt
    field_ids: list[str] = Field(
        min_length=1,
        description="Non-empty list of field internal IDs as strings",
    )
    skills_ids: list[str] = Field(
        default_factory=list,
        description="AI skill IDs to attach. Defaults to empty (no skills).",
    )
    event_params: AutomationEventParamsInput | None = Field(
        default=None,
        description=(
            "Trigger-specific filters (e.g. to_phase_id for card_moved, "
            "triggerFieldIds for field_updated). Omit when not needed."
        ),
    )
    condition: AutomationConditionInput = Field(
        default_factory=_default_automation_condition,
        description=(
            "Trigger condition for the automation. Omit to use DEFAULT_CONDITION "
            "(empty-expression placeholder sent to Pipefy). Pass a dict to override."
        ),
    )


class UpdateAiAutomationInput(BaseModel):
    """Validated input for updating an AI Automation."""

    automation_id: NonBlankStr = Field(description="Automation ID to update")
    name: NonBlankStr | None = None
    active: bool | None = None
    prompt: _AiPrompt | None = None
    field_ids: list[str] | None = Field(default=None, min_length=1)
    skills_ids: list[str] | None = None
    event_params: AutomationEventParamsInput | None = Field(
        default=None,
        description="Trigger-specific filters. Pass to change; omit to keep current.",
    )
    condition: AutomationConditionInput | None = None
