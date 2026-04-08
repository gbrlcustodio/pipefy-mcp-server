"""Payload builders and GraphQL error mapping for relation MCP tools."""

from __future__ import annotations

from typing import Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.tools.graphql_error_helpers import (
    handle_tool_graphql_error,
)


class RelationReadSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    data: dict[str, Any]


class RelationMutationSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    result: dict[str, Any]


def build_relation_read_success_payload(
    data: dict[str, Any],
    *,
    message: str,
) -> RelationReadSuccessPayload:
    """``success``, ``message``, and GraphQL ``data`` for read tools.

    Args:
        data: Subtree from the relation query.
        message: Short summary for the client.
    """
    return cast(
        RelationReadSuccessPayload,
        {
            "success": True,
            "message": message,
            "data": data,
        },
    )


def build_relation_error_payload(*, message: str) -> dict[str, Any]:
    """``success: False`` with ``error`` text.

    Args:
        message: User-visible failure reason.
    """
    return {"success": False, "error": message}


def build_relation_mutation_success_payload(
    *,
    message: str,
    data: dict[str, Any],
) -> RelationMutationSuccessPayload:
    """``success``, ``message``, and mutation ``result``.

    Args:
        message: Short summary for the client.
        data: Raw mutation payload (stored as ``result``).
    """
    return cast(
        RelationMutationSuccessPayload,
        {"success": True, "message": message, "result": data},
    )


def handle_relation_tool_graphql_error(
    exc: BaseException,
    fallback_msg: str,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    """Delegate to :func:`handle_tool_graphql_error`."""
    return handle_tool_graphql_error(exc, fallback_msg, debug=debug)
