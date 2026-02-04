from __future__ import annotations

from typing_extensions import TypedDict


class CardSearch(TypedDict, total=False):
    """Type definition for card search parameters"""

    assignee_ids: list[str]
    ignore_ids: list[str]
    label_ids: list[str]
    title: str
    inbox_emails_read: bool
    include_done: bool


class FindCardsSearch(TypedDict):
    """findCards search (fieldId + fieldValue)."""

    field_id: str
    field_value: str
