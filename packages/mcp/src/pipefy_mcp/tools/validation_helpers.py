"""Shared validation helpers for MCP tool boundaries (IDs, optional dict args)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, TypeVar

from pipefy_sdk.graphql_inputs import GraphQLInput, describe_input_rejection
from pydantic import ValidationError

from pipefy_mcp.core.tool_error_envelope import tool_error

InputT = TypeVar("InputT", bound=GraphQLInput)

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def valid_repo_id(value: object) -> bool:
    """Return True if ``value`` looks like a Pipefy repo identifier (Pipe/Table ID).

    GraphQL ``RepoTypes`` cover Pipe and Table; tools accept a non-empty string slug
    or a positive integer. Other types are rejected without raising.
    """
    if isinstance(value, int):
        return value > 0
    if isinstance(value, str):
        return bool(value.strip())
    return False


def _is_non_positive_numeric(s: str) -> bool:
    """True when ``s`` is a numeric string representing zero or a negative number."""
    stripped = s.strip()
    if stripped.startswith("-") and stripped[1:].isdigit():
        return True
    return bool(stripped.isdigit() and int(stripped) <= 0)


def validate_tool_id(
    value: str | int,
    label: str = "id",
) -> tuple[str | None, dict[str, object] | None]:
    """Validate and normalize a Pipefy ID at the tool boundary.

    Returns ``(cleaned_id, None)`` on success or ``(None, error_payload)`` on
    failure.  Handles empty strings, booleans, zero, and negative numbers.

    Callers should **rebind** the parameter to the cleaned value::

        param, err = validate_tool_id(param, "param")

    Discarding the cleaned value (``_, err = ...``) defeats whitespace
    stripping and int→str normalization.

    Args:
        value: Raw ID value from the MCP tool parameter.
        label: Parameter name for the error message (e.g. ``card_id``).
    """
    if isinstance(value, bool) or not valid_repo_id(value):
        return None, tool_error(
            f"Invalid '{label}': provide a non-empty string or positive integer."
        )
    s = str(value).strip() if isinstance(value, int) else value.strip()
    if not s:
        return None, tool_error(f"Invalid '{label}': provide a non-empty ID.")
    if _is_non_positive_numeric(s):
        return None, tool_error(f"Invalid '{label}': provide a positive integer.")
    return s, None


def validate_optional_tool_id(
    value: str | int | None,
    label: str = "id",
) -> tuple[bool, str | None, dict[str, object] | None]:
    """Validate an optional Pipefy ID.  ``None`` passes through.

    Returns ``(ok, cleaned_id_or_none, error_payload_or_none)``.

    Args:
        value: Optional raw ID value.
        label: Parameter name for the error message.
    """
    if value is None:
        return True, None, None
    cleaned, err = validate_tool_id(value, label)
    if err is not None:
        return False, None, err
    return True, cleaned, None


def build_graphql_input(
    model: type[InputT],
    fields: Mapping[str, Any],
    *,
    operation: str,
) -> tuple[InputT | None, dict[str, object] | None]:
    """Build a typed GraphQL input, turning a rejection into a tool error payload.

    Pipefy rejects an unknown input field itself, so this only moves that
    rejection to before the request, where the message can name the field.
    The offending value is never repeated back, so a wrong field carrying a
    secret does not reach the transcript.

    The payload carries ``INVALID_ARGUMENTS``, the code every other pre-API
    argument-shape failure uses, so a client cannot tell a rejected
    ``extra_input`` key from a rejected declared argument.

    Returns ``(model, None)`` on success or ``(None, error_payload)``.
    """
    try:
        return model(**fields), None
    except ValidationError as exc:
        return None, tool_error(
            f"Invalid arguments for {operation}: {describe_input_rejection(exc)}.",
            code="INVALID_ARGUMENTS",
        )


def validate_optional_tool_id_list(
    values: list[str | int] | None,
    label: str = "ids",
) -> tuple[list[str] | None, dict[str, object] | None]:
    """Validate an optional list of Pipefy IDs at the tool boundary.

    ``None`` passes through as ``(None, None)``; a present list must be non-empty
    and every element pass :func:`validate_tool_id`. Returns
    ``(cleaned_ids, error_payload)``.
    """
    if values is None:
        return None, None
    if not values:
        return None, tool_error(
            f"Invalid '{label}': when provided, it must contain at least one ID."
        )
    cleaned: list[str] = []
    for value in values:
        cleaned_id, err = validate_tool_id(value, label)
        if cleaned_id is None:
            return None, err
        cleaned.append(cleaned_id)
    return cleaned, None


def mutation_error_if_not_optional_dict(
    value: Any,
    *,
    arg_name: str,
) -> dict[str, Any] | None:
    """Return a mutation error payload if ``value`` is present but not a mapping.

    MCP callers may send malformed JSON (e.g. list or string); tools should not
    raise ``AttributeError`` from ``.items()`` on those values.

    Args:
        value: Optional ``extra_input``-style argument from the tool boundary.
        arg_name: Parameter name for the error message (e.g. ``extra_input``).

    Returns:
        Error payload dict when validation fails; ``None`` when the value is
        omitted or is already a ``dict``.
    """
    if value is not None and not isinstance(value, dict):
        return tool_error(
            f"Invalid '{arg_name}': provide a JSON object (dict) when supplied."
        )
    return None


__all__ = [
    "UUID_RE",
    "build_graphql_input",
    "mutation_error_if_not_optional_dict",
    "valid_repo_id",
    "validate_optional_tool_id",
    "validate_tool_id",
]
