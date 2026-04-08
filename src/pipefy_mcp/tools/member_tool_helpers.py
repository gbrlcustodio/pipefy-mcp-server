"""Payload builders and GraphQL error mapping for member MCP tools."""

from __future__ import annotations

from typing import Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.tools.graphql_error_helpers import (
    handle_tool_graphql_error,
)


class MemberMutationSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    result: dict[str, Any]


class MemberMutationWarningPayload(TypedDict):
    success: Literal[True]
    message: str
    warning: str
    result: dict[str, Any]


def build_member_success_payload(
    *,
    message: str,
    data: dict[str, Any],
    warning: str | None = None,
) -> MemberMutationSuccessPayload | MemberMutationWarningPayload:
    """``success``, ``message``, and mutation ``result``.

    Args:
        message: Short summary for the client.
        data: Raw mutation payload (stored as ``result``).
        warning: Optional warning appended when the operation succeeded
            but post-verification detected an anomaly.
    """
    payload: dict[str, Any] = {"success": True, "message": message, "result": data}
    if warning is not None:
        payload["warning"] = warning
    return cast(MemberMutationSuccessPayload, payload)


def build_member_error_payload(*, message: str) -> dict[str, Any]:
    """``success: False`` with ``error`` text.

    Args:
        message: User-visible failure reason.
    """
    return {"success": False, "error": message}


def handle_member_tool_graphql_error(
    exc: BaseException,
    fallback_msg: str,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    """Delegate to :func:`handle_tool_graphql_error`."""
    return handle_tool_graphql_error(exc, fallback_msg, debug=debug)
