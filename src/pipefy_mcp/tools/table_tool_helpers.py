"""Payload builders and GraphQL error mapping for database table MCP tools."""

from __future__ import annotations

from typing import Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.tools.graphql_error_helpers import (
    handle_tool_graphql_error,
)
from pipefy_mcp.tools.validation_helpers import format_json_preview


class TableReadSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    data: dict[str, Any]
    pagination: dict[str, Any] | None


class TableMutationSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    result: dict[str, Any]


class DeleteTablePreviewPayload(TypedDict):
    success: Literal[False]
    requires_confirmation: Literal[True]
    table_id: str | int
    message: str
    table_summary: str


class DeleteTableSuccessPayload(TypedDict):
    success: Literal[True]
    table_id: str | int
    message: str


class DeleteTableErrorPayload(TypedDict):
    success: Literal[False]
    error: str


def _pagination_from_connection_block(block: dict[str, Any]) -> dict[str, Any] | None:
    page_info = block.get("pageInfo")
    if not isinstance(page_info, dict):
        return None
    return {
        "hasNextPage": page_info.get("hasNextPage"),
        "endCursor": page_info.get("endCursor"),
    }


def _extract_pagination(data: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("table_records", "findRecords"):
        block = data.get(key)
        if isinstance(block, dict):
            pg = _pagination_from_connection_block(block)
            if pg is not None:
                return pg
    return None


def build_table_read_success_payload(
    data: dict[str, Any],
    *,
    message: str,
) -> TableReadSuccessPayload:
    """Read envelope with optional ``pagination`` from connection ``pageInfo``.

    Fills ``pagination`` when ``data`` contains ``table_records`` or ``findRecords``.

    Args:
        data: Raw GraphQL payload for the tool.
        message: Short summary for the client.
    """
    return cast(
        TableReadSuccessPayload,
        {
            "success": True,
            "message": message,
            "data": data,
            "pagination": _extract_pagination(data),
        },
    )


def build_table_error_payload(*, message: str) -> dict[str, Any]:
    """``success: False`` with ``error`` text.

    Args:
        message: User-visible failure reason.
    """
    return {"success": False, "error": message}


build_table_read_error_payload = build_table_error_payload
build_table_mutation_error_payload = build_table_error_payload


def build_table_mutation_success_payload(
    *, message: str, data: dict[str, Any]
) -> TableMutationSuccessPayload:
    """``success``, ``message``, and mutation ``result``.

    Args:
        message: Short summary for the client.
        data: Raw mutation payload (stored as ``result``).
    """
    return cast(
        TableMutationSuccessPayload,
        {"success": True, "message": message, "result": data},
    )


def build_delete_table_preview_payload(
    *,
    table_id: str | int,
    table_name: str,
    table_data: dict[str, Any],
) -> DeleteTablePreviewPayload:
    """Two-step delete: preview before ``confirm=True``.

    Args:
        table_id: Target table id.
        table_name: Display name for messaging.
        table_data: Subset serialized into ``table_summary``.
    """
    return {
        "success": False,
        "requires_confirmation": True,
        "table_id": table_id,
        "table_summary": format_json_preview(
            {
                "id": table_data.get("id"),
                "name": table_name,
                "description": table_data.get("description"),
                "table_fields": table_data.get("table_fields"),
            }
        ),
        "message": (
            "⚠️ You are about to permanently delete database table "
            f"'{table_name}' (ID: {table_id}). "
            "This cannot be undone. Confirm with the user, then call again with confirm=True."
        ),
    }


def build_delete_table_success_payload(
    *, table_id: str | int
) -> DeleteTableSuccessPayload:
    """Confirmed table deletion.

    Args:
        table_id: Deleted table id.
    """
    return {
        "success": True,
        "table_id": table_id,
        "message": f"Database table {table_id} was permanently deleted.",
    }


def build_delete_table_error_payload(*, message: str) -> DeleteTableErrorPayload:
    """Failed delete_table attempt.

    Args:
        message: User-visible failure reason.
    """
    return cast(DeleteTableErrorPayload, {"success": False, "error": message})


def map_delete_table_error_to_message(
    *, table_id: str | int, table_name: str, codes: list[str]
) -> str:
    for code in codes:
        if code == "RESOURCE_NOT_FOUND":
            return (
                f"Table with ID {table_id} not found. "
                "Verify the table exists and you have access."
            )
        if code == "PERMISSION_DENIED":
            return (
                f"You don't have permission to delete table {table_id}. "
                "Check your access permissions."
            )
        if code == "RECORD_NOT_DESTROYED":
            return (
                f"Failed to delete table '{table_name}' (ID: {table_id}). "
                "Try again or contact support."
            )
    if codes:
        return (
            f"Failed to delete table '{table_name}' (ID: {table_id}). "
            f"Codes: {', '.join(codes)}"
        )
    return (
        f"Failed to delete table '{table_name}' (ID: {table_id}). "
        "Try again or contact support."
    )


def handle_table_tool_graphql_error(
    exc: BaseException,
    fallback_msg: str,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    """Delegate to :func:`handle_tool_graphql_error`."""
    return handle_tool_graphql_error(exc, fallback_msg, debug=debug)
