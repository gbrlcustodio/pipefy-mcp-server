"""Shared validation helpers for MCP tool boundaries (IDs, optional dict args)."""

from __future__ import annotations

import json
import re
from typing import Any

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def format_json_preview(data: Any) -> str:
    """Pretty-print arbitrary data for MCP confirmation summaries (UTF-8, non-ASCII preserved).

    Args:
        data: Any JSON-serializable or stringifiable structure.
    """
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


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
        return None, {
            "success": False,
            "error": (
                f"Invalid '{label}': provide a non-empty string or positive integer."
            ),
        }
    s = str(value).strip() if isinstance(value, int) else value.strip()
    if not s:
        return None, {
            "success": False,
            "error": f"Invalid '{label}': provide a non-empty ID.",
        }
    if _is_non_positive_numeric(s):
        return None, {
            "success": False,
            "error": f"Invalid '{label}': provide a positive integer.",
        }
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
        return {
            "success": False,
            "error": (
                f"Invalid '{arg_name}': provide a JSON object (dict) when supplied."
            ),
        }
    return None
