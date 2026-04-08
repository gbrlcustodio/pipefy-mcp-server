"""Payload builders and GraphQL error mapping for observability MCP tools."""

from __future__ import annotations

from typing import Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.tools.graphql_error_helpers import (
    handle_tool_graphql_error,
)


class ObservabilityReadSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    data: dict[str, Any]


class ObservabilityMutationSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    result: dict[str, Any]


def build_observability_read_success_payload(
    data: dict[str, Any],
    *,
    message: str,
) -> ObservabilityReadSuccessPayload:
    """``success``, ``message``, and GraphQL ``data`` for read tools.

    Args:
        data: Subtree returned by the observability query.
        message: Short summary for the client.
    """
    return cast(
        ObservabilityReadSuccessPayload,
        {
            "success": True,
            "message": message,
            "data": data,
        },
    )


def build_observability_mutation_success_payload(
    *,
    message: str,
    data: dict[str, Any],
) -> ObservabilityMutationSuccessPayload:
    """``success``, ``message``, and mutation ``result``.

    Args:
        message: Short summary for the client.
        data: Raw mutation payload (stored as ``result``).
    """
    return cast(
        ObservabilityMutationSuccessPayload,
        {"success": True, "message": message, "result": data},
    )


def build_observability_error_payload(*, message: str) -> dict[str, Any]:
    """``success: False`` with ``error`` text.

    Args:
        message: User-visible failure reason.
    """
    return {"success": False, "error": message}


def handle_observability_tool_graphql_error(
    exc: BaseException,
    fallback_msg: str,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    """Delegate to :func:`handle_tool_graphql_error`."""
    return handle_tool_graphql_error(exc, fallback_msg, debug=debug)
