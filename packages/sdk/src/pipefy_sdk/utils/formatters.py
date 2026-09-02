from __future__ import annotations

from typing import Any

from pipefy_infra.coerce import try_int


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


def normalize_field_condition_payload(
    condition: dict[str, Any],
) -> dict[str, Any]:
    """Return a copy of ``ConditionInput`` ready for ``createFieldCondition``.

    Pipefy's ``createFieldCondition`` mutation rejects payloads in two subtle ways
    that show up as ``Something went wrong (INTERNAL_SERVER_ERROR)``:

    1. ``ConditionExpressionInput.id`` is a persisted primary key. Sending an
       arbitrary client-side token causes ``RECORD_NOT_FOUND``. Drop it on create.
    2. ``structure_id`` and the inner values of ``expressions_structure`` must be
       integers; sending strings or mixed types triggers an opaque 500 instead of
       a clean validation error. Coerce both to ``int`` when possible.

    Unknown top-level keys on the condition are passed through, but a caller that
    reaches this through :class:`ConditionInput` cannot supply one: that model
    forbids extras, exactly as ``InputObject 'ConditionInput'`` does on the wire.

    Args:
        condition: Caller-provided ``ConditionInput`` dict (typically with
          ``expressions`` and ``expressions_structure``).

    Returns:
        A new dict safe to send as ``input.condition`` on ``createFieldCondition``
        / ``updateFieldCondition``.
    """

    expressions = condition.get("expressions")
    if not isinstance(expressions, list):
        return dict(condition)

    cleaned_expressions: list[dict[str, Any]] = []
    for expr in expressions:
        if not isinstance(expr, dict):
            cleaned_expressions.append(expr)
            continue
        row = {k: v for k, v in expr.items() if k != "id"}
        if "structure_id" in row and row["structure_id"] is not None:
            row["structure_id"] = try_int(row["structure_id"])
        cleaned_expressions.append(row)

    es = condition.get("expressions_structure")
    if isinstance(es, list):
        coerced_es: list[list[Any]] = []
        for group in es:
            if isinstance(group, list):
                coerced_es.append([try_int(v) for v in group])
            else:
                coerced_es.append([try_int(group)])
        return {
            **condition,
            "expressions": cleaned_expressions,
            "expressions_structure": coerced_es,
        }

    return {**condition, "expressions": cleaned_expressions}


def normalize_field_condition_actions(
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize ``FieldConditionActionInput`` items for create/update mutations.

    Maps the legacy ``actionId: "hidden"`` alias to the canonical ``"hide"`` value
    so callers that copied values from older payloads do not silently produce
    rules without a visible action. Each item is shallow-copied so caller dicts
    are not mutated.

    Args:
        actions: Iterable of ``FieldConditionActionInput`` dicts.

    Returns:
        A new list of shallow copies with ``actionId`` canonicalized.
    """
    normalized: list[dict[str, Any]] = []
    for item in actions:
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        row = dict(item)
        aid = row.get("actionId")
        if isinstance(aid, str) and aid.strip().lower() == "hidden":
            row["actionId"] = "hide"
        normalized.append(row)
    return normalized


def normalize_field_condition_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Repair the ``condition`` / ``actions`` entries of a raw mutation input.

    Runs before the input is parsed into ``CreateFieldConditionInput`` or
    ``UpdateFieldConditionInput``, because two shapes the API accepts do not
    match the schema those models mirror. GraphQL coerces a bare value into a
    single-item list, so ``expressions_structure: [0]`` is a legal way to write
    ``[[0]]`` on the wire, and a model typed from ``[[ID]]`` would refuse it.
    Repairing first keeps the models a faithful mirror without narrowing what a
    caller may send.

    Both helpers it calls are idempotent, so the service running them again on
    the serialized payload changes nothing.
    """
    repaired = dict(fields)
    condition = repaired.get("condition")
    if isinstance(condition, dict):
        repaired["condition"] = normalize_field_condition_payload(condition)
    actions = repaired.get("actions")
    if isinstance(actions, list):
        repaired["actions"] = normalize_field_condition_actions(actions)
    return repaired


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
