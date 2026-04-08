from __future__ import annotations

from typing import Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.tools.destructive_tool_guard import (
    DestructiveCancelledPayload,
    DestructivePreviewPayload,
)
from pipefy_mcp.tools.graphql_error_helpers import extract_error_strings


class UserCancelledError(Exception):
    """Raised when a user cancels an interactive flow."""


class AddCardCommentSuccessPayload(TypedDict):
    success: Literal[True]
    comment_id: str


class AddCardCommentErrorPayload(TypedDict):
    success: Literal[False]
    error: str


AddCardCommentPayload = AddCardCommentSuccessPayload | AddCardCommentErrorPayload


class UpdateCommentSuccessPayload(TypedDict):
    success: Literal[True]
    comment_id: str


class UpdateCommentErrorPayload(TypedDict):
    success: Literal[False]
    error: str


UpdateCommentPayload = UpdateCommentSuccessPayload | UpdateCommentErrorPayload


class DeleteCommentSuccessPayload(TypedDict):
    success: Literal[True]


class DeleteCommentErrorPayload(TypedDict):
    success: Literal[False]
    error: str


DeleteCommentPayload = DeleteCommentSuccessPayload | DeleteCommentErrorPayload


class DeleteCardSuccessPayload(TypedDict):
    success: Literal[True]
    card_id: int
    card_title: str
    pipe_name: str
    message: str


class DeleteCardErrorPayload(TypedDict):
    success: Literal[False]
    error: str


DeleteCardPayload = (
    DestructivePreviewPayload
    | DestructiveCancelledPayload
    | DeleteCardSuccessPayload
    | DeleteCardErrorPayload
)

# Message returned by find_cards tool when the API returns no matching cards.
FIND_CARDS_EMPTY_MESSAGE = "No cards found for this field/value."


def build_add_card_comment_success_payload(
    *, comment_id: object
) -> AddCardCommentSuccessPayload:
    """Recorded comment id.

    Args:
        comment_id: New comment id from the API (coerced to str).
    """
    return {"success": True, "comment_id": str(comment_id)}


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
    return {"success": False, "error": message}


def build_add_card_comment_error_payload(*, message: str) -> AddCardCommentErrorPayload:
    """add_card_comment failure envelope.

    Args:
        message: User-visible failure reason.
    """
    return cast(AddCardCommentErrorPayload, _build_comment_error_payload(message))


def build_update_comment_success_payload(
    *, comment_id: object
) -> UpdateCommentSuccessPayload:
    """Updated comment id.

    Args:
        comment_id: Updated comment id (coerced to str).
    """
    return {"success": True, "comment_id": str(comment_id)}


def build_update_comment_error_payload(*, message: str) -> UpdateCommentErrorPayload:
    """update_comment failure envelope.

    Args:
        message: User-visible failure reason.
    """
    return cast(UpdateCommentErrorPayload, _build_comment_error_payload(message))


def build_delete_comment_success_payload() -> DeleteCommentSuccessPayload:
    """Minimal success body after delete_comment."""
    return {"success": True}


def build_delete_comment_error_payload(*, message: str) -> DeleteCommentErrorPayload:
    """delete_comment failure envelope.

    Args:
        message: User-visible failure reason.
    """
    return cast(DeleteCommentErrorPayload, _build_comment_error_payload(message))


def build_delete_card_success_payload(
    *, card_id: int, card_title: str, pipe_name: str
) -> DeleteCardSuccessPayload:
    """Confirmed card deletion.

    Args:
        card_id: Deleted card id.
        card_title: Card title for messaging.
        pipe_name: Pipe name for messaging.
    """
    return {
        "success": True,
        "card_id": card_id,
        "card_title": card_title,
        "pipe_name": pipe_name,
        "message": (
            f"Card '{card_title}' (ID: {card_id}) from pipe '{pipe_name}' "
            "has been permanently deleted."
        ),
    }


def build_delete_card_error_payload(*, message: str) -> DeleteCardErrorPayload:
    """delete_card failure envelope.

    Args:
        message: User-visible failure reason.
    """
    return {"success": False, "error": message}


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
    *, card_id: int, card_title: str, codes: list[str]
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
