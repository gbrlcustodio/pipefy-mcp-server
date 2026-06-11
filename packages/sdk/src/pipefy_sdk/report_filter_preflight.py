"""Pure validation for GraphQL ``ReportCardsFilter`` JSON before report mutations."""

from __future__ import annotations

from typing import Any

REPORT_CARDS_FILTER_GROUP_KEYS = frozenset(
    {"operator", "queries", "groups", "id", "lastId"}
)
REPORT_CARDS_FILTER_QUERY_KEYS = frozenset(
    {"field", "operator", "value", "type", "label", "id"}
)
REPORT_CARDS_FILTER_GROUP_OPERATORS = frozenset({"and", "or"})

REPORT_CARDS_FILTER_REJECTED_ROOT_KEYS = frozenset(
    {
        "current_phase",
        "current_phase_id",
        "phase_id",
        "phase_ids",
        "phases_ids",
    }
)

EXAMPLE_PHASE_FILTER: dict[str, Any] = {
    "operator": "and",
    "queries": [
        {
            "field": "current_phase",
            "operator": "eq",
            "type": "select",
            "value": "<phase_id>",
        }
    ],
}


def normalize_report_cards_filter(filter_obj: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with JSON integer ``value`` scalars coerced to strings."""
    return _normalize_filter_group(filter_obj)


def _normalize_filter_group(node: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = dict(node)
    queries = node.get("queries")
    if isinstance(queries, list):
        normalized["queries"] = [
            _normalize_filter_query(query) if isinstance(query, dict) else query
            for query in queries
        ]
    groups = node.get("groups")
    if isinstance(groups, list):
        normalized["groups"] = [
            _normalize_filter_group(group) if isinstance(group, dict) else group
            for group in groups
        ]
    return normalized


def _normalize_filter_query(node: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(node)
    if "value" in normalized:
        normalized["value"] = _coerce_filter_query_value(normalized["value"])
    return normalized


def _coerce_filter_query_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    return value


def prepare_report_cards_filter(
    filter_obj: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Normalize a ``ReportCardsFilter`` and raise ``ValueError`` when invalid."""
    if filter_obj is None:
        return None
    normalized = normalize_report_cards_filter(filter_obj)
    message = report_cards_filter_error(normalized)
    if message is not None:
        raise ValueError(message)
    return normalized


def report_cards_filter_error(filter_obj: dict[str, Any] | None) -> str | None:
    """Return an error message for an invalid ``ReportCardsFilter``, or ``None`` when valid."""
    if filter_obj is None:
        return None
    if not isinstance(filter_obj, dict):
        return f"filter must be a JSON object (ReportCardsFilter), received {type(filter_obj).__name__}"
    return _validate_filter_group(filter_obj, path="filter")


def _validate_filter_group(node: dict[str, Any], *, path: str) -> str | None:
    if path == "filter":
        for rejected in REPORT_CARDS_FILTER_REJECTED_ROOT_KEYS:
            if rejected in node:
                return (
                    f"filter must use ReportCardsFilter shape (operator + queries), not top-level "
                    f"'{rejected}'. Discover the phase predicate field via "
                    "get_pipe_report_filterable_fields; use field/operator/value inside queries."
                )

    unknown = set(node) - REPORT_CARDS_FILTER_GROUP_KEYS
    if unknown:
        keys = ", ".join(sorted(unknown))
        return f"{path} has unknown key(s): {keys}. Allowed: {', '.join(sorted(REPORT_CARDS_FILTER_GROUP_KEYS))}."

    operator = node.get("operator")
    if operator is None:
        return f"{path}.operator is required (and | or)."
    if not isinstance(operator, str) or not operator.strip():
        return f"{path}.operator must be a non-empty string, received {operator!r}."
    if operator not in REPORT_CARDS_FILTER_GROUP_OPERATORS:
        return (
            f"{path}.operator must be one of {sorted(REPORT_CARDS_FILTER_GROUP_OPERATORS)!r}, "
            f"received {operator!r}."
        )

    queries = node.get("queries")
    if queries is not None:
        if not isinstance(queries, list):
            return f"{path}.queries must be a list, received {type(queries).__name__}."
        for index, query in enumerate(queries):
            err = _validate_filter_query(query, path=f"{path}.queries[{index}]")
            if err is not None:
                return err

    groups = node.get("groups")
    if groups is not None:
        if not isinstance(groups, list):
            return f"{path}.groups must be a list, received {type(groups).__name__}."
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                return f"{path}.groups[{index}] must be an object, received {type(group).__name__}."
            err = _validate_filter_group(group, path=f"{path}.groups[{index}]")
            if err is not None:
                return err

    return None


def _validate_filter_query(node: Any, *, path: str) -> str | None:
    if not isinstance(node, dict):
        return f"{path} must be an object, received {type(node).__name__}."

    unknown = set(node) - REPORT_CARDS_FILTER_QUERY_KEYS
    if unknown:
        keys = ", ".join(sorted(unknown))
        return (
            f"{path} has unknown key(s): {keys}. Allowed: "
            f"{', '.join(sorted(REPORT_CARDS_FILTER_QUERY_KEYS))}."
        )

    field = node.get("field")
    if field is None:
        return f"{path}.field is required (internal name from get_pipe_report_filterable_fields)."
    if not isinstance(field, str) or not field.strip():
        return f"{path}.field must be a non-empty string, received {field!r}."

    op = node.get("operator")
    if op is None:
        return f"{path}.operator is required (eq, not_eq, contains, ...)."
    if not isinstance(op, str) or not op.strip():
        return f"{path}.operator must be a non-empty string, received {op!r}."

    value = node.get("value")
    if value is not None and not isinstance(value, str):
        return (
            f"{path}.value must be a string when set, received {type(value).__name__}."
        )

    field_type = node.get("type")
    if field_type is not None and (
        not isinstance(field_type, str) or not field_type.strip()
    ):
        return (
            f"{path}.type must be a non-empty string when set, received {field_type!r}."
        )

    return None


__all__ = [
    "EXAMPLE_PHASE_FILTER",
    "REPORT_CARDS_FILTER_GROUP_KEYS",
    "REPORT_CARDS_FILTER_QUERY_KEYS",
    "REPORT_CARDS_FILTER_REJECTED_ROOT_KEYS",
    "normalize_report_cards_filter",
    "prepare_report_cards_filter",
    "report_cards_filter_error",
]
