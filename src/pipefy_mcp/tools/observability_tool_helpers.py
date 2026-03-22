"""Payload builders and GraphQL error mapping for observability MCP tools."""

from __future__ import annotations

from typing import Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.tools.graphql_error_helpers import (
    extract_error_strings,
    extract_graphql_correlation_id,
    extract_graphql_error_codes,
    with_debug_suffix,
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
    """Build a success payload for observability read tools."""
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
    """Structured success payload for observability mutation tools."""
    return cast(
        ObservabilityMutationSuccessPayload,
        {"success": True, "message": message, "result": data},
    )


def build_observability_error_payload(*, message: str) -> dict[str, Any]:
    return {"success": False, "error": message}


def handle_observability_tool_graphql_error(
    exc: BaseException,
    fallback_msg: str,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    """Map a GraphQL/client exception to an observability-tool error payload.

    Args:
        exc: Exception from the Pipefy client or transport layer.
        fallback_msg: Message when no extractable error strings exist.
        debug: When True, append GraphQL codes and correlation_id to the message.
    """
    msgs = extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else fallback_msg
    if not debug:
        return build_observability_error_payload(message=base)
    codes = extract_graphql_error_codes(exc)
    cid = extract_graphql_correlation_id(exc)
    return build_observability_error_payload(
        message=with_debug_suffix(base, debug=True, codes=codes, correlation_id=cid),
    )
