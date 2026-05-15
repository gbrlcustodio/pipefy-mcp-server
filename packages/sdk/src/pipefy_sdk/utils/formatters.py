from __future__ import annotations

from typing import Any


def convert_fields_to_array(fields: Any) -> list[dict[str, Any]]:
    """Convert card fields input into Pipefy `FieldValueInput` array format.

    This preserves the current behavior of `PipefyClient.create_card`:
    - If `fields` is a dict, convert each (key, value) into a dict containing:
      `field_id`, `field_value`, and `generated_by_ai=True`.
    - If `fields` is a list, ensure each dict entry has `generated_by_ai=True` by default.
    - Otherwise, wrap the value in a list (or return [] if falsy).

    Args:
        fields: The input fields provided by callers (dict, list, or other).

    Returns:
        A list of dictionaries ready for GraphQL `fields_attributes`.
    """

    if isinstance(fields, dict):
        return [
            {"field_id": field_id, "field_value": value, "generated_by_ai": True}
            for field_id, value in fields.items()
        ]

    if isinstance(fields, list):
        normalized: list[dict[str, Any]] = []
        for item in fields:
            if isinstance(item, dict):
                if "generated_by_ai" not in item:
                    item = {**item, "generated_by_ai": True}
                normalized.append(item)
            else:
                # Legacy: allow non-dict items for backward compatibility.
                normalized.append(item)
        return normalized

    return [fields] if fields else []


def convert_values_to_camel_case(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert values to camelCase format for `updateFieldsValues` mutation.

    - Each input dict must contain `field_id` (or `fieldId`) and `value`.
    - Output uses `fieldId`, `value`, `operation` (uppercased, default "REPLACE"),
      and `generatedByAi=True`.

    Pipefy API responses use camelCase (`fieldId`), so accepting both keys lets
    callers copy ids straight from a `get_cards`/`get_card` payload into the
    `field_updates` array without manual renaming.

    Args:
        values: List of dicts with `field_id` or `fieldId`, `value`, and
          optional `operation`.

    Returns:
        Formatted list of dicts for GraphQL `UpdateFieldsValuesInput.values`.

    Raises:
        ValueError: If any item is missing the required field id or `value`.
    """

    formatted: list[dict[str, Any]] = []
    for i, v in enumerate(values):
        field_id = v.get("field_id", v.get("fieldId"))
        if field_id is None:
            raise ValueError(
                f"Value at index {i} is missing required 'field_id' key "
                "('fieldId' camelCase is also accepted)"
            )
        if "value" not in v:
            raise ValueError(f"Value at index {i} is missing required 'value' key")

        formatted.append(
            {
                "fieldId": field_id,
                "value": v["value"],
                "operation": str(v.get("operation", "REPLACE")).upper(),
                "generatedByAi": True,
            }
        )

    return formatted
