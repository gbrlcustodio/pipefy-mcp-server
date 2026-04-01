"""Pydantic models for AI Agent input validation."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipefy_mcp.models.validators import NonBlankStr

ACTION_ID_AI_BEHAVIOR = "ai_behavior"
MAX_BEHAVIORS = 5


class BehaviorInput(BaseModel):
    """One AI agent behavior; accepts snake_case or camelCase, dumps with camelCase aliases.

    The Pipefy API requires ``actionParams.aiBehaviorParams.actionsAttributes`` with at least
    one action; otherwise ``updateAiAgent`` fails (e.g. "The instructions must contain at least 1 action").
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
