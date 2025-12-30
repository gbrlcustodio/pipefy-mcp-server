from __future__ import annotations

import sys

if sys.version_info < (3, 12):
    from typing_extensions import TypedDict
else:
    from typing import TypedDict


class CardSearch(TypedDict, total=False):
    """Type definition for card search parameters"""

    assignee_ids: list[str]
    ignore_ids: list[str]
    label_ids: list[str]
    title: str
    inbox_emails_read: bool
    include_done: bool
