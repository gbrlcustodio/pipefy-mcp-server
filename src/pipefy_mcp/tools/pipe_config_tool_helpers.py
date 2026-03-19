from __future__ import annotations

import json
from typing import Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.tools.graphql_error_helpers import (
    extract_error_strings,
    extract_graphql_correlation_id,
    extract_graphql_error_codes,
    with_debug_suffix,
)


class DeletePipePreviewPayload(TypedDict):
    success: Literal[False]
    requires_confirmation: Literal[True]
    pipe_id: int
    message: str
    pipe_summary: str


class DeletePipeSuccessPayload(TypedDict):
    success: Literal[True]
    pipe_id: int
    message: str


class DeletePipeErrorPayload(TypedDict):
    success: Literal[False]
    error: str


DeletePipePayload = (
    DeletePipePreviewPayload | DeletePipeSuccessPayload | DeletePipeErrorPayload
)


class PipeMutationSuccessPayload(TypedDict):
    """Structured success response for pipe-config mutation tools."""

    success: Literal[True]
    message: str
    result: dict[str, Any]


def _to_readable_json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def handle_pipe_config_tool_graphql_error(
    exc: BaseException,
    fallback_msg: str,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    """Map a GraphQL/client exception to a pipe-config tool error payload.

    When ``debug`` is False, skips correlation/code extraction (same user-visible message).

    Args:
        exc: Exception from the Pipefy client or transport layer.
        fallback_msg: Message when no extractable error strings exist.
        debug: When True, append GraphQL codes and correlation_id to the message.
    """
    msgs = extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else fallback_msg
    if not debug:
        return build_pipe_tool_error_payload(message=base)
    codes = extract_graphql_error_codes(exc)
    cid = extract_graphql_correlation_id(exc)
    return build_pipe_tool_error_payload(
        message=with_debug_suffix(base, debug=True, codes=codes, correlation_id=cid),
    )


def build_pipe_mutation_success_payload(
    *, label: str, data: dict[str, Any]
) -> PipeMutationSuccessPayload:
    """Build a success payload for pipe create/update/clone tools.

    ``result`` is the raw GraphQL response dict (structured), not a nested JSON string.
    """
    return cast(
        PipeMutationSuccessPayload,
        {"success": True, "message": label, "result": data},
    )


def build_pipe_tool_error_payload(*, message: str) -> dict[str, Any]:
    return {"success": False, "error": message}


def build_delete_pipe_preview_payload(
    *,
    pipe_id: int,
    pipe_name: str,
    pipe_data: dict[str, Any],
) -> DeletePipePreviewPayload:
    """Preview for delete_pipe when confirm is false."""
    return {
        "success": False,
        "requires_confirmation": True,
        "pipe_id": pipe_id,
        "pipe_summary": _to_readable_json(
            {
                "id": pipe_data.get("id"),
                "name": pipe_name,
                "phases": pipe_data.get("phases"),
            }
        ),
        "message": (
            "⚠️ You are about to permanently delete pipe "
            f"'{pipe_name}' (ID: {pipe_id}). "
            "This cannot be undone. Confirm with the user, then call again with confirm=True."
        ),
    }


def build_delete_pipe_success_payload(*, pipe_id: int) -> DeletePipeSuccessPayload:
    return {
        "success": True,
        "pipe_id": pipe_id,
        "message": f"Pipe {pipe_id} was permanently deleted.",
    }


def build_delete_pipe_error_payload(*, message: str) -> DeletePipeErrorPayload:
    return cast(DeletePipeErrorPayload, {"success": False, "error": message})


def map_delete_pipe_error_to_message(
    *, pipe_id: int, pipe_name: str, codes: list[str]
) -> str:
    """Map GraphQL error codes to user-facing text for delete_pipe."""
    for code in codes:
        if code == "RESOURCE_NOT_FOUND":
            return (
                f"Pipe with ID {pipe_id} not found. "
                "Verify the pipe exists and you have access."
            )
        if code == "PERMISSION_DENIED":
            return (
                f"You don't have permission to delete pipe {pipe_id}. "
                "Check your access permissions."
            )
        if code == "RECORD_NOT_DESTROYED":
            return (
                f"Failed to delete pipe '{pipe_name}' (ID: {pipe_id}). "
                "Try again or contact support."
            )

    if codes:
        return (
            f"Failed to delete pipe '{pipe_name}' (ID: {pipe_id}). "
            f"Codes: {', '.join(codes)}"
        )

    return (
        f"Failed to delete pipe '{pipe_name}' (ID: {pipe_id}). "
        "Try again or contact support."
    )


__all__ = [
    "DeletePipeErrorPayload",
    "DeletePipePayload",
    "DeletePipePreviewPayload",
    "DeletePipeSuccessPayload",
    "PipeMutationSuccessPayload",
    "build_delete_pipe_error_payload",
    "build_delete_pipe_preview_payload",
    "build_delete_pipe_success_payload",
    "build_pipe_mutation_success_payload",
    "build_pipe_tool_error_payload",
    "handle_pipe_config_tool_graphql_error",
    "map_delete_pipe_error_to_message",
]
