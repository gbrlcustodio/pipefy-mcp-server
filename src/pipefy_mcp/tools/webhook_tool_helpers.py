"""Payload builders and GraphQL error mapping for email and webhook MCP tools."""

from __future__ import annotations

from typing import Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.tools.graphql_error_helpers import (
    handle_tool_graphql_error,
)
from pipefy_mcp.tools.tool_error_envelope import tool_error


class WebhookMutationSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    result: dict[str, Any]


def build_webhook_success_payload(
    *,
    message: str,
    data: dict[str, Any],
) -> WebhookMutationSuccessPayload:
    """``success``, ``message``, and mutation ``result``.

    Args:
        message: Short summary for the client.
        data: Raw mutation payload (stored as ``result``).
    """
    return cast(
        WebhookMutationSuccessPayload,
        {"success": True, "message": message, "result": data},
    )


def build_webhook_error_payload(*, message: str) -> dict[str, Any]:
    """``success: False`` with ``error`` text.

    Args:
        message: User-visible failure reason.
    """
    return tool_error(message)


def handle_webhook_tool_graphql_error(
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
    "WebhookMutationSuccessPayload",
    "build_webhook_error_payload",
    "build_webhook_success_payload",
    "handle_webhook_tool_graphql_error",
]
