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


def copy_card_search(search: CardSearch) -> CardSearch:
    """Shallow copy containing only keys defined on :class:`CardSearch`.

    Drops any extra keys so MCP-supplied dicts match the schema expected by
    :meth:`PipefyClient.get_cards`.
    """
    return {k: search[k] for k in CardSearch.__optional_keys__ if k in search}


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
