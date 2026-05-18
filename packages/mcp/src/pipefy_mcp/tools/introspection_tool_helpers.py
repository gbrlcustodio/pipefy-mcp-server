"""MCP payloads for schema introspection and raw GraphQL tools."""

from __future__ import annotations

import json
from typing import Any

from pipefy_mcp.tools.tool_error_envelope import tool_error


def _format_graphql_data_for_llm(data: dict[str, Any]) -> str:
    """Indented JSON (UTF-8) for LLM-facing tool text."""
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def build_success_payload(
    data: dict[str, Any],
    *,
    include_parsed: bool = False,
) -> dict[str, Any]:
    """``success: True`` with ``result`` (pretty-printed JSON string).

    When ``include_parsed`` is True, a ``data`` key is added with the same
    content as a native dict so typed clients and AI agents can access fields
    directly without ``json.loads``.  Off by default to avoid doubling the
    payload size over the MCP transport.

    Args:
        data: Introspection or execution dict from the service layer.
        include_parsed: When True, include ``data`` dict alongside ``result``.
    """
    payload: dict[str, Any] = {
        "success": True,
        "result": _format_graphql_data_for_llm(data),
    }
    if include_parsed:
        payload["data"] = data
    return payload


def build_error_payload(error_message: str) -> dict[str, Any]:
    """``success: False`` with structured ``error.message``.

    Args:
        error_message: Agent/user-facing explanation.
    """
    return tool_error(error_message)


__all__ = [
    "build_error_payload",
    "build_success_payload",
]
