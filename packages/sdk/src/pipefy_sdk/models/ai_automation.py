"""Pydantic models for AI Automation input validation."""

from __future__ import annotations

import copy
import re
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from pipefy_sdk.models.validators import NonBlankStr

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


# The operations Pipefy's condition engine accepts. Documented here for
# discoverability; treated as a soft enum (any string passes through, the API
# validates on write) so the set can grow server-side without an SDK release.
CONDITION_OPERATIONS: tuple[str, ...] = (
    "equals",
    "not_equals",
    "present",
    "blank",
    "string_contains",
    "string_not_contains",
    "number_greater_than",
    "number_less_than",
    "date_is_today",
    "date_is_yesterday",
    "date_in_current_week",
    "date_in_last_week",
    "date_in_current_month",
    "date_in_last_month",
    "date_in_current_year",
    "date_in_last_year",
    "date_is",
    "date_is_after",
    "date_is_before",
)


class ConditionExpressionInput(BaseModel):
    """One Pipefy ``ConditionExpressionInput`` — a single field test in a condition.

    Every field is optional at the GraphQL layer; the API validates the combination.
    ``operation`` is a soft enum: any value passes through (see
    :data:`CONDITION_OPERATIONS` for the documented set). ``field_address`` is a field
    ``internal_id`` (the last dotted segment when addressing a connected card's field,
    e.g. ``<connectorFieldId>.<targetFieldId>``), never a field slug. ``extra="allow"``
    round-trips unknown keys.
    """

    model_config = ConfigDict(extra="allow")

    field_address: str | None = Field(
        default=None,
        description="Field internal_id to test (last dotted segment for a connected field); not a slug.",
    )
    operation: str | None = Field(
        default=None,
        description=(
            "Comparison operation, e.g. equals, not_equals, present, blank, "
            "string_contains, number_greater_than, date_is_after. Soft enum — any "
            "value passes; the API validates it."
        ),
    )
    value: str | None = Field(
        default=None,
        description="Value (or field id) to compare against. Omit for present/blank.",
    )
    structure_id: str | int | None = Field(
        default=None,
        description="Groups this expression within expressions_structure.",
    )
    id: str | None = Field(
        default=None,
        description="Existing condition-expression id, when editing one in place.",
    )


class AutomationConditionInput(BaseModel):
    """Pipefy ``ConditionInput``-shaped payload. Unknown top-level keys are preserved.

    ``expressions_structure`` is an array of arrays that groups the ``expressions``
    (by their ``structure_id``) into an AND-of-ORs tree: each inner array is OR'd,
    and the inner arrays are AND'd together — e.g. ``[[0, 1], [2]]`` means
    ``(expr0 OR expr1) AND expr2``.
    """

    model_config = ConfigDict(extra="allow")

    expressions: list[ConditionExpressionInput] = Field(
        default_factory=list,
        description="Condition expressions (Pipefy ConditionExpressionInput).",
    )
    expressions_structure: list[Any] | None = Field(
        default=None,
        description="AND-of-ORs grouping of expressions by structure_id (array of arrays).",
    )

    def to_api_payload(self) -> dict[str, Any]:
        """Serialize to the GraphQL ``ConditionInput`` shape, omitting unset/None keys.

        Only the keys the caller actually set are emitted, so an expression that
        provides just ``field_address``/``operation``/``value`` does not send empty
        ``structure_id``/``id`` fields.
        """
        return self.model_dump(mode="python", exclude_unset=True, exclude_none=True)


class FieldMapInput(BaseModel):
    """Shared ``FieldMapInput`` shell: a single field-mapping entry.

    Used by both behavior action ``metadata.fieldsAttributes`` and classic-automation
    ``action_params.field_map``. The GraphQL type marks ``fieldId`` and ``inputMode``
    NON_NULL, but this is a lenient parse shell — required-ness is enforced by the
    consumer (behavior metadata validators with pinned messages; the API for classic
    automations) so a malformed entry yields an actionable error, not an opaque
    Pydantic one. ``extra="allow"`` round-trips unknown keys.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    field_id: str | None = Field(default=None, alias="fieldId")
    input_mode: str | None = Field(default=None, alias="inputMode")
    value: str | None = None


class AutomationEventParamsInput(BaseModel):
    """Pipefy ``AutomationEventParamsInput`` trigger params.

    The declared inputFields mix casing in one type: ``to_phase_id`` is snake while
    its siblings are camel. Aliases are per declared field (never a blanket
    snake→camel pass); ``to_phase_id`` keeps its wire name (no alias) so it round-trips
    for both reads (GET selects ``to_phase_id``) and writes. ``extra="allow"`` lets
    sibling/unknown keys pass through verbatim. Dump with ``by_alias=True``.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    kind_of_sla: str | None = Field(default=None, alias="kindOfSla")
    from_phase_id: str | None = Field(default=None, alias="fromPhaseId")
    in_phase_id: str | None = Field(default=None, alias="inPhaseId")
    to_phase_id: str | None = None
    trigger_automation_id: str | None = Field(default=None, alias="triggerAutomationId")
    trigger_field_ids: list[str] | None = Field(default=None, alias="triggerFieldIds")


class AutomationActionParamsInput(BaseModel):
    """Classic-automation ``AutomationActionParamsInput`` subtree read by preflight.

    Only the fields preflight touches are typed (``field_map``, ``to_phase_id`` — both
    snake wire names, so no alias); ``extra="allow"`` passes every other declared or
    unknown key (``card_id``, ``aiBehaviorParams``, ``httpMethod``, …) through verbatim.
    There is deliberately no ``phase`` field: it is not a declared write input (Core
    rejects it), only an output-type convenience derived from ``to_phase_id``.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    field_map: list[FieldMapInput] | None = None
    to_phase_id: str | None = None


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
    field via ``%{internal_id}`` (e.g. ``%{900000101}`` — any numeric
    internal_id from the target pipe; the digits are illustrative).  Without it
    the API returns the opaque error ``"Input parameters are required"``.
    """
    stripped = v.strip()
    if not stripped:
        raise ValueError("prompt must not be blank")
    if not FIELD_REF_PATTERN.search(stripped):
        raise ValueError(
            "prompt must reference at least one pipe field using %{internal_id} "
            "syntax (e.g. 'Summarize: %{900000101}' — use your field's "
            "internal_id from get_start_form_fields / get_phase_fields). "
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
            "using %{internal_id} syntax (e.g. 'Summarize: %{900000101}'); "
            "substitute the numeric internal_id from the target pipe."
        ),
    ),
]


class CreateAiAutomationInput(BaseModel):
    """Validated input for creating an AI Automation (generate_with_ai).

    When ``condition`` is omitted, it defaults to a deep copy of
    :data:`DEFAULT_CONDITION` so the internal API always receives an explicit
    condition object (see ``docs/mcp/tools/automations-and-ai.md``).
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
