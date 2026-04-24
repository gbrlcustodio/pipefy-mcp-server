"""Payload builders and GraphQL error mapping for report MCP tools."""

from __future__ import annotations

from typing import Any, Literal

from typing_extensions import TypedDict

from pipefy_mcp.settings import settings
from pipefy_mcp.tools.graphql_error_helpers import (
    handle_tool_graphql_error,
)
from pipefy_mcp.tools.tool_error_envelope import tool_error, tool_success

# The ``Legacy*SuccessPayload`` TypedDicts below describe the flag=false shape
# only. Under the default ``PIPEFY_MCP_UNIFIED_ENVELOPE=true``, helpers return
# ``ToolSuccessPayload`` instead (see ADR-0001).


class LegacyReportReadSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    data: dict[str, Any]


class LegacyReportMutationSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    result: dict[str, Any]


def build_report_read_success_payload(
    data: dict[str, Any],
    *,
    message: str,
) -> dict[str, Any]:
    """``success``, ``message``, and GraphQL ``data`` for read tools.

    Args:
        data: Subtree returned by the report query.
        message: Short summary for the client.
    """
    if settings.pipefy.mcp_unified_envelope:
        return tool_success(data=data, message=message)
    return {"success": True, "message": message, "data": data}


def build_report_mutation_success_payload(
    *,
    message: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """``success``, ``message``, and mutation ``result``.

    Args:
        message: Short summary for the client.
        data: Mutation payload (legacy path exposes it as ``result``).
    """
    if settings.pipefy.mcp_unified_envelope:
        return tool_success(data=data, message=message)
    return {"success": True, "message": message, "result": data}


def build_report_error_payload(*, message: str) -> dict[str, Any]:
    """``success: False`` with ``error`` text.

    Args:
        message: User-visible failure reason.
    """
    return tool_error(message)


def handle_report_tool_graphql_error(
    exc: BaseException,
    fallback_msg: str,
    *,
    debug: bool = False,
    resource_kind: str | None = None,
    resource_id: str | None = None,
    invalid_args_hint: str | None = None,
) -> dict[str, Any]:
    """Delegate to :func:`handle_tool_graphql_error` with enrichment opt-ins."""
    return handle_tool_graphql_error(
        exc,
        fallback_msg,
        debug=debug,
        resource_kind=resource_kind,
        resource_id=resource_id,
        invalid_args_hint=invalid_args_hint,
    )


__all__ = [
    "LegacyReportMutationSuccessPayload",
    "LegacyReportReadSuccessPayload",
    "build_report_error_payload",
    "build_report_mutation_success_payload",
    "build_report_read_success_payload",
    "handle_report_tool_graphql_error",
]
