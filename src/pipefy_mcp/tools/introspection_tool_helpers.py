"""MCP payloads for schema introspection and raw GraphQL tools."""

from __future__ import annotations

import json
from typing import Any


def _format_graphql_data_for_llm(data: dict[str, Any]) -> str:
    """Indented JSON (UTF-8) for LLM-facing tool text."""
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def build_success_payload(data: dict[str, Any]) -> dict[str, Any]:
    """``success: True`` with stringified ``result`` for MCP text content.

    Args:
        data: Introspection or execution dict from the service layer.
    """
    return {
        "success": True,
        "result": _format_graphql_data_for_llm(data),
    }


def build_error_payload(error_message: str) -> dict[str, Any]:
    """``success: False`` with ``error`` string.

    Args:
        error_message: Agent/user-facing explanation.
    """
    return {
        "success": False,
        "error": error_message,
    }
