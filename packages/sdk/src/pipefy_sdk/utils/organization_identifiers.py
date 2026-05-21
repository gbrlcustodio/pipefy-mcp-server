"""Helpers for organization UUID vs numeric id resolution."""

from __future__ import annotations

import uuid


def looks_like_uuid(value: str) -> bool:
    """True when ``value`` parses as a UUID."""
    try:
        uuid.UUID(value.strip())
    except ValueError:
        return False
    return True
