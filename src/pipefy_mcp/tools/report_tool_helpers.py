"""Payload builders and GraphQL error mapping for report MCP tools."""

from __future__ import annotations

from typing import Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.tools.graphql_error_helpers import (
    extract_error_strings,
    extract_graphql_correlation_id,
    extract_graphql_error_codes,
    with_debug_suffix,
)


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
    return {"success": False, "error": message}


def handle_report_tool_graphql_error(
    exc: BaseException,
    fallback_msg: str,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    """Turn transport/GraphQL failures into ``build_report_error_payload`` output.

    Args:
        exc: Root exception from gql/httpx.
        fallback_msg: Used when ``extract_error_strings`` is empty.
        debug: When True, append codes and ``correlation_id``.
    """
    msgs = extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else fallback_msg
    if not debug:
        return build_report_error_payload(message=base)
    codes = extract_graphql_error_codes(exc)
    cid = extract_graphql_correlation_id(exc)
    return build_report_error_payload(
        message=with_debug_suffix(base, debug=True, codes=codes, correlation_id=cid),
    )
