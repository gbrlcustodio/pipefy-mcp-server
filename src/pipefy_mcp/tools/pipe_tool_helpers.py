from __future__ import annotations

from typing import Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.services.pipefy.types import CardSearch
from pipefy_mcp.tools.destructive_tool_guard import (
    DestructiveCancelledPayload,
    DestructivePreviewPayload,
)
from pipefy_mcp.tools.graphql_error_helpers import extract_error_strings
from pipefy_mcp.tools.tool_error_envelope import (
    ToolErrorDetail,
    ToolSuccessPayload,
    is_unified_envelope_enabled,
    tool_error,
    tool_success,
)


class UserCancelledError(Exception):
    """Raised when a user cancels an interactive flow."""


# The ``Legacy*SuccessPayload`` TypedDicts below describe the flag=false shape
# only. Under the default ``PIPEFY_MCP_UNIFIED_ENVELOPE=true``, helpers return
# ``ToolSuccessPayload`` instead (see ADR-0001).


class LegacyAddCardCommentSuccessPayload(TypedDict):
    success: Literal[True]
    comment_id: str


class AddCardCommentErrorPayload(TypedDict):
    success: Literal[False]
    error: ToolErrorDetail


AddCardCommentPayload = (
    LegacyAddCardCommentSuccessPayload | ToolSuccessPayload | AddCardCommentErrorPayload
)


class LegacyUpdateCommentSuccessPayload(TypedDict):
    success: Literal[True]
    comment_id: str


class UpdateCommentErrorPayload(TypedDict):
    success: Literal[False]
    error: ToolErrorDetail


UpdateCommentPayload = (
    LegacyUpdateCommentSuccessPayload | ToolSuccessPayload | UpdateCommentErrorPayload
)


class LegacyDeleteCommentSuccessPayload(TypedDict):
    success: Literal[True]


class DeleteCommentErrorPayload(TypedDict):
    success: Literal[False]
    error: ToolErrorDetail


DeleteCommentPayload = (
    DestructivePreviewPayload
    | LegacyDeleteCommentSuccessPayload
    | ToolSuccessPayload
    | DeleteCommentErrorPayload
)


class LegacyDeleteCardSuccessPayload(TypedDict):
    success: Literal[True]
    card_id: str | int
    card_title: str
    pipe_name: str
    message: str


class DeleteCardErrorPayload(TypedDict):
    success: Literal[False]
    error: ToolErrorDetail


DeleteCardPayload = (
    DestructivePreviewPayload
    | DestructiveCancelledPayload
    | LegacyDeleteCardSuccessPayload
    | ToolSuccessPayload
    | DeleteCardErrorPayload
)

# Message returned by find_cards tool when the API returns no matching cards.
FIND_CARDS_EMPTY_MESSAGE = "No cards found for this field/value."


async def find_label_dependents(
    client: PipefyClient,
    *,
    pipe_id: str,
    label_id: str,
    sample_size: int = 5,
) -> dict[str, Any] | None:
    """Sample cards that carry ``label_id`` in ``pipe_id`` (for delete preview).

    Returns ``None`` when no cards use the label or when the auxiliary
    ``get_cards`` query fails. Otherwise returns a dict with:

    * ``sample_card_ids``: up to ``sample_size`` card ids.
    * ``sample_size``: **actual** length of ``sample_card_ids`` — so consumers
      can render accurate counts ("3 cards" not "5 cards") when fewer than the
      cap carry the label.
    * ``sample_cap``: the ``sample_size`` parameter value (the cap that was
      applied while sampling).
    * ``has_more``: ``True`` when Pipefy returned more cards than the cap
      (the real cascade is strictly larger than the sample).
    """
    try:
        search: CardSearch = {"label_ids": [str(label_id)]}
        payload = await client.get_cards(
            pipe_id,
            search,
            include_fields=False,
            first=sample_size + 1,
        )
    except Exception:  # noqa: BLE001
        return None
    cards_root = (payload or {}).get("cards") or {}
    edges = cards_root.get("edges") or []
    ids: list[str] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        node = edge.get("node") or {}
        cid = node.get("id")
        if cid is not None:
            ids.append(str(cid))
    if not ids:
        return None
    sampled = ids[:sample_size]
    has_more = len(ids) > sample_size
    return {
        "sample_card_ids": sampled,
        "sample_size": len(sampled),
        "sample_cap": sample_size,
        "has_more": has_more,
    }


def build_add_card_comment_success_payload(*, comment_id: object) -> dict[str, Any]:
    """Recorded comment id.

    Args:
        comment_id: New comment id from the API (coerced to str).
    """
    cid = str(comment_id)
    if is_unified_envelope_enabled():
        return tool_success(data={"comment_id": cid})
    return {"success": True, "comment_id": cid}


# Markers for mapping GraphQL errors to user-friendly messages.
_NOT_FOUND_MARKERS = [
    "not found",
    "record not found",
    "could not find",
    "does not exist",
    "doesn't exist",
]
_PERMISSION_MARKERS = [
    "permission",
    "not authorized",
    "unauthorized",
    "forbidden",
    "access denied",
    "not allowed",
]
_INVALID_INPUT_MARKERS = [
    "invalid",
    "validation",
    "must be",
    "can't be",
    "cannot be",
    "required",
    "blank",
]
_INVALID_INPUT_MARKERS_NO_BLANK = [
    "invalid",
    "validation",
    "must be",
    "can't be",
    "cannot be",
    "required",
]


def _map_comment_like_error(
    exc: BaseException,
    *,
    not_found_msg: str,
    permission_msg: str,
    invalid_msg: str,
    fallback_msg: str,
    invalid_markers: list[str] | None = None,
) -> str:
    """Map exception to a friendly message using shared not-found/permission/invalid markers."""
    messages = extract_error_strings(exc)
    haystack = " ".join(messages).lower()
    markers = invalid_markers if invalid_markers is not None else _INVALID_INPUT_MARKERS
    if any(m in haystack for m in _NOT_FOUND_MARKERS):
        return not_found_msg
    elif any(m in haystack for m in _PERMISSION_MARKERS):
        return permission_msg
    elif any(m in haystack for m in markers):
        return invalid_msg
    return fallback_msg


def map_add_card_comment_error_to_message(exc: BaseException) -> str:
    """Heuristic English message for add_comment failures."""
    return _map_comment_like_error(
        exc,
        not_found_msg="Card not found. Please verify 'card_id' and access permissions.",
        permission_msg="You don't have permission to comment on this card.",
        invalid_msg="Invalid input. Please provide a valid 'card_id' and non-empty 'text'.",
        fallback_msg="Unexpected error while adding comment. Please try again.",
    )


def map_update_comment_error_to_message(exc: BaseException) -> str:
    """Heuristic English message for update_comment failures."""
    return _map_comment_like_error(
        exc,
        not_found_msg="Comment not found. Please verify 'comment_id' and access permissions.",
        permission_msg="You don't have permission to update this comment.",
        invalid_msg="Invalid input. Please provide a valid 'comment_id' and non-empty 'text'.",
        fallback_msg="Unexpected error while updating comment. Please try again.",
    )


def map_delete_comment_error_to_message(exc: BaseException) -> str:
    """Heuristic English message for delete_comment failures."""
    return _map_comment_like_error(
        exc,
        not_found_msg="Comment not found. Please verify 'comment_id' and access permissions.",
        permission_msg="You don't have permission to delete this comment.",
        invalid_msg="Invalid input. Please provide a valid 'comment_id'.",
        fallback_msg="Unexpected error while deleting comment. Please try again.",
        invalid_markers=_INVALID_INPUT_MARKERS_NO_BLANK,
    )


def _build_comment_error_payload(message: str) -> dict:
    return tool_error(message)


def build_add_card_comment_error_payload(*, message: str) -> AddCardCommentErrorPayload:
    """add_card_comment failure envelope.

    Args:
        message: User-visible failure reason.
    """
    return cast(AddCardCommentErrorPayload, _build_comment_error_payload(message))


def build_update_comment_success_payload(*, comment_id: object) -> dict[str, Any]:
    """Updated comment id.

    Args:
        comment_id: Updated comment id (coerced to str).
    """
    cid = str(comment_id)
    if is_unified_envelope_enabled():
        return tool_success(data={"comment_id": cid})
    return {"success": True, "comment_id": cid}


def build_update_comment_error_payload(*, message: str) -> UpdateCommentErrorPayload:
    """update_comment failure envelope.

    Args:
        message: User-visible failure reason.
    """
    return cast(UpdateCommentErrorPayload, _build_comment_error_payload(message))


def build_delete_comment_success_payload() -> dict[str, Any]:
    """Minimal success body after delete_comment."""
    if is_unified_envelope_enabled():
        return tool_success()
    return {"success": True}


def build_delete_comment_error_payload(*, message: str) -> DeleteCommentErrorPayload:
    """delete_comment failure envelope.

    Args:
        message: User-visible failure reason.
    """
    return cast(DeleteCommentErrorPayload, _build_comment_error_payload(message))


def build_delete_card_success_payload(
    *, card_id: str | int, card_title: str, pipe_name: str
) -> dict[str, Any]:
    """Confirmed card deletion.

    Args:
        card_id: Deleted card id.
        card_title: Card title for messaging.
        pipe_name: Pipe name for messaging.
    """
    message = (
        f"Card '{card_title}' (ID: {card_id}) from pipe '{pipe_name}' "
        "has been permanently deleted."
    )
    if is_unified_envelope_enabled():
        return tool_success(
            data={
                "card_id": card_id,
                "card_title": card_title,
                "pipe_name": pipe_name,
            },
            message=message,
        )
    return {
        "success": True,
        "card_id": card_id,
        "card_title": card_title,
        "pipe_name": pipe_name,
        "message": message,
    }


def build_delete_card_error_payload(*, message: str) -> DeleteCardErrorPayload:
    """delete_card failure envelope.

    Args:
        message: User-visible failure reason.
    """
    return cast(DeleteCardErrorPayload, tool_error(message))


def _filter_editable_field_definitions(field_definitions: list) -> list[dict]:
    """Return only editable field definitions, preserving unknown shapes.

    Note: Fields without an explicit 'editable' key are assumed to be editable
    (defaults to True), matching Pipefy API behavior.
    """
    editable_fields: list[dict] = []
    for field_def in field_definitions:
        if not isinstance(field_def, dict):
            continue
        if field_def.get("editable", True):
            editable_fields.append(field_def)
    return editable_fields


def _filter_fields_by_definitions(
    fields: dict[str, object] | None, field_definitions: list[dict]
) -> dict[str, object]:
    """Filter provided field values to editable field IDs."""
    if not fields:
        return {}
    editable_ids = {field_def["id"] for field_def in field_definitions}
    return {
        field_id: value
        for field_id, value in fields.items()
        if field_id in editable_ids
    }


def map_delete_card_error_to_message(
    *, card_id: str | int, card_title: str, codes: list[str]
) -> str:
    """Map GraphQL error codes to short, actionable messages for delete_card."""
    for code in codes:
        if code == "RESOURCE_NOT_FOUND":
            return (
                f"Card with ID {card_id} not found. "
                "Verify the card exists and you have access permissions."
            )
        if code == "PERMISSION_DENIED":
            return (
                f"You don't have permission to delete card {card_id}. "
                "Please check your access permissions."
            )
        if code == "RECORD_NOT_DESTROYED":
            return (
                f"Failed to delete card '{card_title}' (ID: {card_id}). "
                "Please try again or contact support."
            )

    if codes:
        return (
            f"Failed to delete card '{card_title}' (ID: {card_id}). "
            f"Codes: {', '.join(codes)}"
        )

    return (
        f"Failed to delete card '{card_title}' (ID: {card_id}). "
        "Please try again or contact support."
    )


__all__ = [
    "AddCardCommentErrorPayload",
    "AddCardCommentPayload",
    "DeleteCardErrorPayload",
    "DeleteCardPayload",
    "DeleteCommentErrorPayload",
    "DeleteCommentPayload",
    "FIND_CARDS_EMPTY_MESSAGE",
    "LegacyAddCardCommentSuccessPayload",
    "LegacyDeleteCardSuccessPayload",
    "LegacyDeleteCommentSuccessPayload",
    "LegacyUpdateCommentSuccessPayload",
    "find_label_dependents",
    "UpdateCommentErrorPayload",
    "UpdateCommentPayload",
    "UserCancelledError",
    "build_add_card_comment_error_payload",
    "build_add_card_comment_success_payload",
    "build_delete_card_error_payload",
    "build_delete_card_success_payload",
    "build_delete_comment_error_payload",
    "build_delete_comment_success_payload",
    "build_update_comment_error_payload",
    "build_update_comment_success_payload",
    "map_add_card_comment_error_to_message",
    "map_delete_card_error_to_message",
    "map_delete_comment_error_to_message",
    "map_update_comment_error_to_message",
]
