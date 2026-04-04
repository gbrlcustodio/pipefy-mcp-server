"""Pydantic models for AI Agent input validation."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipefy_mcp.models.validators import NonBlankStr

ACTION_ID_AI_BEHAVIOR = "ai_behavior"
MAX_BEHAVIORS = 5

# actionTypes that require pipeId + fieldsAttributes in metadata
_CARD_FIELD_ACTION_TYPES = frozenset(
    {"update_card", "create_card", "create_connected_card"}
)


def _validate_card_field_metadata(action_type: str, metadata: dict) -> None:
    """Validate metadata for actions that operate on card fields.

    Args:
        action_type: The actionType string (used in error messages).
        metadata: The metadata dict from the action.

    Raises:
        ValueError: When required keys are missing or malformed.
    """
    if not metadata.get("pipeId"):
        raise ValueError(
            f"actionType '{action_type}' requires metadata.pipeId "
            f"(the pipe where the action executes)."
        )
    fields = metadata.get("fieldsAttributes")
    if not isinstance(fields, list) or not fields:
        raise ValueError(
            f"actionType '{action_type}' requires metadata.fieldsAttributes "
            f"as a non-empty list of field entries."
        )
    for i, entry in enumerate(fields):
        if not isinstance(entry, dict):
            raise ValueError(
                f"actionType '{action_type}': fieldsAttributes[{i}] must be a dict."
            )
        if not entry.get("fieldId"):
            raise ValueError(
                f"actionType '{action_type}': fieldsAttributes[{i}] requires 'fieldId'."
            )
        if not entry.get("inputMode"):
            raise ValueError(
                f"actionType '{action_type}': fieldsAttributes[{i}] "
                f"requires 'inputMode'."
            )


def _validate_move_card_metadata(metadata: dict) -> None:
    """Validate metadata for move_card actions.

    Raises:
        ValueError: When destinationPhaseId is missing or blank.
    """
    dest = metadata.get("destinationPhaseId")
    if not isinstance(dest, str) or not dest.strip():
        raise ValueError(
            "actionType 'move_card' requires metadata.destinationPhaseId "
            "(the target phase ID)."
        )


def _validate_action_metadata(action: dict) -> None:
    """Validate metadata for a single action based on its actionType.

    Unknown actionTypes are passed through without validation.
    """
    action_type = action.get("actionType", "")
    metadata = action.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    if action_type in _CARD_FIELD_ACTION_TYPES:
        _validate_card_field_metadata(action_type, metadata)
    elif action_type == "move_card":
        _validate_move_card_metadata(metadata)


class BehaviorInput(BaseModel):
    """One AI agent behavior; accepts snake_case or camelCase, dumps with camelCase aliases.

    The Pipefy API requires ``actionParams.aiBehaviorParams.actionsAttributes`` with at least
    one action; otherwise ``updateAiAgent`` fails (e.g. "The instructions must contain at least 1 action").

    Optional ``eventParams`` configures the trigger. For each action dict, known ``actionType``
    values get ``metadata`` checks: ``update_card`` / ``create_card`` / ``create_connected_card``
    need ``pipeId`` and non-empty ``fieldsAttributes`` (each entry needs ``fieldId`` and
    ``inputMode``); ``move_card`` needs ``destinationPhaseId``. Other types are not validated here.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: NonBlankStr
    event_id: NonBlankStr = Field(alias="eventId")
    action_id: str = Field(default=ACTION_ID_AI_BEHAVIOR, alias="actionId")
    active: bool = True
    condition: dict | None = None
    event_params: dict | None = Field(default=None, alias="eventParams")
    action_params: dict | None = Field(default=None, alias="actionParams")

    @model_validator(mode="after")
    def ai_behavior_must_include_at_least_one_action(self) -> Self:
        """Reject behaviors that would fail updateAiAgent in production."""
        params = self.action_params
        if not params:
            raise ValueError(
                "Each behavior must include actionParams with aiBehaviorParams.actionsAttributes "
                'containing at least one action (e.g. actionType "move_card" with metadata).'
            )
        abp = None
        if isinstance(params, dict):
            abp = params.get("aiBehaviorParams") or params.get("ai_behavior_params")
        if not isinstance(abp, dict):
            raise ValueError(
                "Each behavior must include actionParams.aiBehaviorParams with "
                "a non-empty actionsAttributes list."
            )
        actions = abp.get("actionsAttributes") or abp.get("actions_attributes")
        if not isinstance(actions, list) or not actions:
            raise ValueError(
                "Each behavior must set actionParams.aiBehaviorParams.actionsAttributes with "
                'at least one action (Pipefy: "The instructions must contain at least 1 action").'
            )
        for action in actions:
            if isinstance(action, dict):
                _validate_action_metadata(action)
        return self


class CreateAiAgentInput(BaseModel):
    """Validated input for create-and-configure flow: create mutation uses name and repo_uuid only."""

    name: NonBlankStr
    repo_uuid: NonBlankStr
    instruction: NonBlankStr
    behaviors: list[BehaviorInput] = Field(
        min_length=1,
        max_length=MAX_BEHAVIORS,
        description="List of behaviors (1 to MAX_BEHAVIORS)",
    )
    data_source_ids: list[str] = Field(default_factory=list)


class UpdateAiAgentInput(BaseModel):
    """Validated input for updating an AI Agent."""

    uuid: NonBlankStr
    name: NonBlankStr
    repo_uuid: NonBlankStr
    behaviors: list[BehaviorInput] = Field(
        min_length=1,
        max_length=MAX_BEHAVIORS,
        description="List of behaviors (1 to MAX_BEHAVIORS)",
    )
    instruction: str | None = None
    data_source_ids: list[str] = Field(default_factory=list)
