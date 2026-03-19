"""Payload builders and GraphQL error mapping for database table MCP tools."""

from __future__ import annotations

import json
from typing import Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.tools.pipe_tool_helpers import (
    _extract_error_strings,
    _extract_graphql_correlation_id,
    _extract_graphql_error_codes,
    _with_debug_suffix,
)


def _to_readable_json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


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
    """Build a success payload for table read tools.

    When the GraphQL payload includes `table_records` or `findRecords`, copies
    `hasNextPage` and `endCursor` into `pagination` for clearer LLM consumption.
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


def build_table_read_error_payload(*, message: str) -> dict[str, Any]:
    return {"success": False, "error": message}


def build_table_mutation_success_payload(
    *, message: str, data: dict[str, Any]
) -> TableMutationSuccessPayload:
    """Structured success payload for table/record mutation tools."""
    return cast(
        TableMutationSuccessPayload,
        {"success": True, "message": message, "result": data},
    )


def build_table_mutation_error_payload(*, message: str) -> dict[str, Any]:
    return {"success": False, "error": message}


def mutation_error_if_not_optional_dict(
    value: Any,
    *,
    arg_name: str,
) -> dict[str, Any] | None:
    """Return a mutation error payload if ``value`` is present but not a mapping.

    MCP callers may send malformed JSON (e.g. list or string); tools should not
    raise ``AttributeError`` from ``.items()`` on those values.

    Args:
        value: Optional ``extra_input``-style argument from the tool boundary.
        arg_name: Parameter name for the error message (e.g. ``extra_input``).

    Returns:
        Error payload dict when validation fails; ``None`` when the value is
        omitted or is already a ``dict``.
    """
    if value is not None and not isinstance(value, dict):
        return build_table_mutation_error_payload(
            message=(
                f"Invalid '{arg_name}': provide a JSON object (dict) when supplied."
            ),
        )
    return None


def build_delete_table_preview_payload(
    *,
    table_id: str | int,
    table_name: str,
    table_data: dict[str, Any],
) -> DeleteTablePreviewPayload:
    """Preview when delete_table is called without confirmation."""
    return {
        "success": False,
        "requires_confirmation": True,
        "table_id": table_id,
        "table_summary": _to_readable_json(
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
    return {
        "success": True,
        "table_id": table_id,
        "message": f"Database table {table_id} was permanently deleted.",
    }


def build_delete_table_error_payload(*, message: str) -> DeleteTableErrorPayload:
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
    """Map a GraphQL/client exception to a table-tool error payload.

    Args:
        exc: Exception from the Pipefy client or transport layer.
        fallback_msg: Message when no extractable error strings exist.
        debug: When True, append GraphQL codes and correlation_id to the message.
    """
    msgs = _extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else fallback_msg
    if not debug:
        return build_table_read_error_payload(message=base)
    codes = _extract_graphql_error_codes(exc)
    cid = _extract_graphql_correlation_id(exc)
    return build_table_read_error_payload(
        message=_with_debug_suffix(base, debug=True, codes=codes, correlation_id=cid),
    )
