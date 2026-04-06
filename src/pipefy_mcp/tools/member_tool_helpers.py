"""Payload builders and GraphQL error mapping for member MCP tools."""

from __future__ import annotations

from typing import Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.tools.graphql_error_helpers import (
    extract_error_strings,
    extract_graphql_correlation_id,
    extract_graphql_error_codes,
    with_debug_suffix,
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
    """Turn transport/GraphQL failures into ``build_member_error_payload`` output.

    Args:
        exc: Root exception from gql/httpx.
        fallback_msg: Used when ``extract_error_strings`` is empty.
        debug: When True, append codes and ``correlation_id``.
    """
    msgs = extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else fallback_msg
    if not debug:
        return build_member_error_payload(message=base)
    codes = extract_graphql_error_codes(exc)
    cid = extract_graphql_correlation_id(exc)
    return build_member_error_payload(
        message=with_debug_suffix(base, debug=True, codes=codes, correlation_id=cid),
    )
