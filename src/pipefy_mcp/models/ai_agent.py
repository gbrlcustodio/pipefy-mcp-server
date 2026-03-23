"""Pydantic models for AI Agent input validation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from pipefy_mcp.models.validators import NonBlankStr

ACTION_ID_AI_BEHAVIOR = "ai_behavior"
MAX_BEHAVIORS = 5


class CreateAiAgentInput(BaseModel):
    """Validated input for creating an AI Agent."""

    name: NonBlankStr
    repo_uuid: NonBlankStr


class BehaviorInput(BaseModel):
    """One AI agent behavior; accepts snake_case or camelCase, dumps with camelCase aliases."""

    model_config = ConfigDict(populate_by_name=True)

    name: NonBlankStr
    event_id: NonBlankStr = Field(alias="eventId")
    action_id: str = Field(default=ACTION_ID_AI_BEHAVIOR, alias="actionId")
    active: bool = True
    condition: dict | None = None
    action_params: dict | None = Field(default=None, alias="actionParams")


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
