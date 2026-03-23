from __future__ import annotations

import json
from typing import Any


def _format_graphql_data_for_llm(data: dict[str, Any]) -> str:
    """Serialize introspection or execution data as indented JSON for LLM consumption."""
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def build_success_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Build the MCP success payload for introspection or raw GraphQL tool results.

    Args:
        data: Raw dict from SchemaIntrospectionService (or compatible shape).
    """
    return {
        "success": True,
        "result": _format_graphql_data_for_llm(data),
    }


def build_error_payload(error_message: str) -> dict[str, Any]:
    """Build the MCP error payload for introspection or raw GraphQL tool failures.

    Args:
        error_message: User- or agent-facing explanation.
    """
    return {
        "success": False,
        "error": error_message,
    }
