from __future__ import annotations

from typing import Any, Literal

from typing_extensions import TypedDict


class CardSearch(TypedDict, total=False):
    """Type definition for card search parameters"""

    assignee_ids: list[str]
    ignore_ids: list[str]
    label_ids: list[str]
    title: str
    inbox_emails_read: bool
    include_done: bool


class AiAgentGraphPayload(TypedDict, total=False):
    """Common fields returned by Pipefy ``aiAgent`` (additional keys may be present)."""

    uuid: str
    name: str
    instruction: str
    disabledAt: str | None
    needReview: bool
    behaviors: list[dict[str, Any]]
    dataSourceIds: list[str]


class AgentServiceResult(TypedDict):
    agent_uuid: str
    message: str


class AutomationServiceResult(TypedDict):
    automation_id: str
    message: str


class ToggleAgentStatusResult(TypedDict):
    success: Literal[True]
    message: str
