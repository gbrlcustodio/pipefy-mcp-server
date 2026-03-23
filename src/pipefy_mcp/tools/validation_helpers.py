"""Shared validation helpers for MCP tool boundaries (IDs, optional dict args)."""

from __future__ import annotations

import re
from typing import Any

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
