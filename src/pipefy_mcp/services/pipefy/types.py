from typing import List, TypedDict


class CardSearch(TypedDict, total=False):
    """Type definition for card search parameters"""

    assignee_ids: List[str]
    ignore_ids: List[str]
    label_ids: List[str]
    title: str
    inbox_emails_read: bool
    include_done: bool
