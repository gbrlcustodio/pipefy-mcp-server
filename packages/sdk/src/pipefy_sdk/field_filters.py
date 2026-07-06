"""Pure helpers for filtering card field values against phase/start-form definitions."""

from __future__ import annotations

from typing import Any


def filter_editable_field_definitions(
    field_definitions: list[Any],
) -> list[dict[str, Any]]:
    """Return editable field definitions; missing ``editable`` defaults to True."""
    editable_fields: list[dict[str, Any]] = []
    for field_def in field_definitions:
        if not isinstance(field_def, dict):
            continue
        if field_def.get("editable", True):
            editable_fields.append(field_def)
    return editable_fields


def filter_fields_by_definitions(
    fields: dict[str, Any] | None,
    field_definitions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Keep only ``fields`` keys that match an ``id`` in ``field_definitions``."""
    if not fields:
        return {}
    editable_ids = {
        field_id for field_def in field_definitions if (field_id := field_def.get("id"))
    }
    return {
        field_id: value
        for field_id, value in fields.items()
        if field_id in editable_ids
    }


def skipped_field_ids(
    fields: dict[str, Any],
    kept_fields: dict[str, Any],
) -> list[str]:
    """Field ids present in ``fields`` but dropped by ``filter_fields_by_definitions``."""
    return [field_id for field_id in fields if field_id not in kept_fields]
