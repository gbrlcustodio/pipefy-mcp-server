"""Shared validation helpers for pipe configuration MCP tools."""

from __future__ import annotations


def valid_phase_field_id(field_id: str | int) -> bool:
    """True for a non-blank string ID or a positive integer ID (phases, fields, conditions)."""
    if isinstance(field_id, int):
        return field_id > 0
    if isinstance(field_id, str):
        return bool(field_id.strip())
    return False
