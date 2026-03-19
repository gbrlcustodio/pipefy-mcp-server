"""Pydantic models for AI Agent input validation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from pipefy_mcp.models.validators import NonBlankStr

ACTION_ID_AI_BEHAVIOR = "ai_behavior"
MAX_BEHAVIORS = 5


class CreateAiAgentInput(BaseModel):
    """Validated input for creating an AI Agent.

    Attributes:
        name: Agent name (non-empty, stripped).
        repo_uuid: Repository UUID (non-empty, stripped).
    """

    name: NonBlankStr
    repo_uuid: NonBlankStr


class BehaviorInput(BaseModel):
    """Validated input for an AI Agent behavior.

    Accepts both snake_case and camelCase field names (e.g. event_id or eventId).
    Serializes to camelCase for the GraphQL API when using model_dump(by_alias=True).

    Attributes:
        name: Behavior name (non-empty, stripped).
        event_id: Event trigger ID (eventId in GraphQL).
        action_id: Action ID; defaults to ai_behavior (actionId in GraphQL).
        active: Whether the behavior is active; defaults to True.
        condition: Optional condition structure.
        action_params: Optional action parameters (actionParams in GraphQL).
    """

    model_config = ConfigDict(populate_by_name=True)

    name: NonBlankStr
    event_id: NonBlankStr = Field(alias="eventId")
    action_id: str = Field(default=ACTION_ID_AI_BEHAVIOR, alias="actionId")
    active: bool = True
    condition: dict | None = None
    action_params: dict | None = Field(default=None, alias="actionParams")


class UpdateAiAgentInput(BaseModel):
    """Validated input for updating an AI Agent.

    Attributes:
        uuid: Agent UUID (non-empty, stripped).
        name: Agent name (non-empty, stripped).
        repo_uuid: Repository UUID (non-empty, stripped).
        behaviors: List of behaviors (1 to MAX_BEHAVIORS).
        instruction: Optional instruction text.
        data_source_ids: Optional list of data source IDs.
    """

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
