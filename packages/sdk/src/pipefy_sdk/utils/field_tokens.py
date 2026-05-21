"""Helpers to tell phase field tokens (slug vs internal id / uuid) apart."""

from __future__ import annotations

from pipefy_sdk.utils.organization_identifiers import (
    looks_like_uuid as looks_like_uuid_token,
)


def slug_like_field_token(token: str | int) -> bool:
    """True when ``token`` is probably a phase field slug (not internal id / uuid)."""
    s = str(token).strip()
    if not s or s.isdigit() or looks_like_uuid_token(s):
        return False
    return any(c.isalpha() for c in s)
