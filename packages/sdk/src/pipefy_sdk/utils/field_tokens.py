"""Helpers to tell phase field tokens (slug vs internal id / uuid) apart."""

from __future__ import annotations

import uuid as uuid_mod


def looks_like_uuid_token(token: str) -> bool:
    """True when ``token`` parses as a UUID (Pipefy often uses uuid for field ``id``)."""
    try:
        uuid_mod.UUID(str(token).strip())
    except ValueError:
        return False
    return True


def slug_like_field_token(token: str | int) -> bool:
    """True when ``token`` is probably a phase field slug (not internal id / uuid)."""
    s = str(token).strip()
    if not s or s.isdigit() or looks_like_uuid_token(s):
        return False
    return any(c.isalpha() for c in s)
