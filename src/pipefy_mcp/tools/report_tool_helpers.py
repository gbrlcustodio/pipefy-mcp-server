"""Payload builders and GraphQL error mapping for report MCP tools."""

from __future__ import annotations

from typing import Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.tools.graphql_error_helpers import (
    handle_tool_graphql_error,
)
from pipefy_mcp.tools.tool_error_envelope import tool_error


class ReportReadSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    data: dict[str, Any]


class ReportMutationSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    result: dict[str, Any]


def build_report_read_success_payload(
    data: dict[str, Any],
    *,
    message: str,
) -> ReportReadSuccessPayload:
    """``success``, ``message``, and GraphQL ``data`` for read tools.

    Args:
        data: Subtree returned by the report query.
        message: Short summary for the client.
    """
    return cast(
        ReportReadSuccessPayload,
        {
            "success": True,
            "message": message,
            "data": data,
        },
    )


def build_report_mutation_success_payload(
    *,
    message: str,
    data: dict[str, Any],
) -> ReportMutationSuccessPayload:
    """``success``, ``message``, and mutation ``result``.

    Args:
        message: Short summary for the client.
        data: Raw mutation payload (stored as ``result``).
    """
    return cast(
        ReportMutationSuccessPayload,
        {"success": True, "message": message, "result": data},
    )


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
) -> dict[str, Any]:
    """Delegate to :func:`handle_tool_graphql_error`."""
    return handle_tool_graphql_error(exc, fallback_msg, debug=debug)


__all__ = [
    "ReportMutationSuccessPayload",
    "ReportReadSuccessPayload",
    "build_report_error_payload",
    "build_report_mutation_success_payload",
    "build_report_read_success_payload",
    "handle_report_tool_graphql_error",
]
