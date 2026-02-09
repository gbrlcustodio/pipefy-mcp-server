import re
from typing import Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


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


class DeleteCommentSuccessPayload(TypedDict):
    success: Literal[True]


class DeleteCommentErrorPayload(TypedDict):
    success: Literal[False]
    error: str


class DeleteCardPreviewPayload(TypedDict):
    success: Literal[False]
    requires_confirmation: Literal[True]
    card_id: int
    card_title: str
    pipe_name: str
    message: str


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
    DeleteCardPreviewPayload | DeleteCardSuccessPayload | DeleteCardErrorPayload
)

# Message returned by find_cards tool when the API returns no matching cards.
FIND_CARDS_EMPTY_MESSAGE = "No cards found for this field/value."


class DeleteCardConfirmation(BaseModel):
    confirm: bool = Field(
        ...,
        description="Set to true to confirm deletion, or false to cancel.",
    )


def build_add_card_comment_success_payload(
    *, comment_id: object
) -> AddCardCommentSuccessPayload:
    """Build the public success payload for add_card_comment."""
    return {"success": True, "comment_id": str(comment_id)}


def _extract_error_strings(exc: BaseException) -> list[str]:
    """Best-effort extraction of error messages from gql/GraphQL exceptions."""
    messages: list[str] = []

    raw = str(exc)
    if raw:
        messages.append(raw)

    errors = getattr(exc, "errors", None)
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict):
                msg = item.get("message")
                if isinstance(msg, str) and msg:
                    messages.append(msg)
            elif isinstance(item, str) and item:
                messages.append(item)

    return messages


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
    messages = _extract_error_strings(exc)
    haystack = " ".join(messages).lower()
    markers = invalid_markers if invalid_markers is not None else _INVALID_INPUT_MARKERS
    if any(m in haystack for m in _NOT_FOUND_MARKERS):
        return not_found_msg
    if any(m in haystack for m in _PERMISSION_MARKERS):
        return permission_msg
    if any(m in haystack for m in markers):
        return invalid_msg
    return fallback_msg


def map_add_card_comment_error_to_message(exc: BaseException) -> str:
    """Map a GraphQL exception into a stable, friendly English message."""
    return _map_comment_like_error(
        exc,
        not_found_msg="Card not found. Please verify 'card_id' and access permissions.",
        permission_msg="You don't have permission to comment on this card.",
        invalid_msg="Invalid input. Please provide a valid 'card_id' and non-empty 'text'.",
        fallback_msg="Unexpected error while adding comment. Please try again.",
    )


def map_update_comment_error_to_message(exc: BaseException) -> str:
    """Map a GraphQL exception into a stable, friendly English message for update_comment."""
    return _map_comment_like_error(
        exc,
        not_found_msg="Comment not found. Please verify 'comment_id' and access permissions.",
        permission_msg="You don't have permission to update this comment.",
        invalid_msg="Invalid input. Please provide a valid 'comment_id' and non-empty 'text'.",
        fallback_msg="Unexpected error while updating comment. Please try again.",
    )


def map_delete_comment_error_to_message(exc: BaseException) -> str:
    """Map a GraphQL exception into a stable, friendly English message for delete_comment."""
    return _map_comment_like_error(
        exc,
        not_found_msg="Comment not found. Please verify 'comment_id' and access permissions.",
        permission_msg="You don't have permission to delete this comment.",
        invalid_msg="Invalid input. Please provide a valid 'comment_id'.",
        fallback_msg="Unexpected error while deleting comment. Please try again.",
        invalid_markers=_INVALID_INPUT_MARKERS_NO_BLANK,
    )


def build_add_card_comment_error_payload(*, message: str) -> AddCardCommentErrorPayload:
    """Build the public error payload for add_card_comment."""
    return {"success": False, "error": message}


def build_update_comment_success_payload(
    *, comment_id: object
) -> UpdateCommentSuccessPayload:
    """Build the public success payload for update_comment."""
    return {"success": True, "comment_id": str(comment_id)}


def build_update_comment_error_payload(*, message: str) -> UpdateCommentErrorPayload:
    """Build the public error payload for update_comment."""
    return {"success": False, "error": message}


def build_delete_comment_success_payload() -> DeleteCommentSuccessPayload:
    """Build the public success payload for delete_comment."""
    return {"success": True}


def build_delete_comment_error_payload(*, message: str) -> DeleteCommentErrorPayload:
    """Build the public error payload for delete_comment."""
    return {"success": False, "error": message}


def build_delete_card_preview_payload(
    *, card_id: int, card_title: str, pipe_name: str
) -> DeleteCardPreviewPayload:
    """Build the preview payload for delete_card."""
    return {
        "success": False,
        "requires_confirmation": True,
        "card_id": card_id,
        "card_title": card_title,
        "pipe_name": pipe_name,
        "message": (
            "⚠️ You are about to permanently delete card "
            f"'{card_title}' (ID: {card_id}) from pipe '{pipe_name}'. "
            "This action is irreversible. Set 'confirm=True' to proceed."
        ),
    }


def build_delete_card_success_payload(
    *, card_id: int, card_title: str, pipe_name: str
) -> DeleteCardSuccessPayload:
    """Build the success payload for delete_card."""
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
    """Build the error payload for delete_card."""
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


def _extract_graphql_error_codes(exc: BaseException) -> list[str]:
    """Extract GraphQL `extensions.code` values from gql/GraphQL exceptions."""
    codes: list[str] = []

    errors = getattr(exc, "errors", None)
    if isinstance(errors, list):
        for item in errors:
            if not isinstance(item, dict):
                continue
            extensions = item.get("extensions")
            if not isinstance(extensions, dict):
                continue
            code = extensions.get("code")
            if isinstance(code, str) and code:
                codes.append(code)

    # Best-effort parse from exception string when extensions are missing
    raw = str(exc)
    if raw:
        for match in re.findall(r"""['"]code['"]\s*[:=]\s*['"]([A-Z_]+)['"]""", raw):
            codes.append(match)

    # De-dup while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            unique.append(code)
    return unique


def _extract_graphql_correlation_id(exc: BaseException) -> str | None:
    """Best-effort extraction of correlation_id from GraphQL exception strings."""
    raw = str(exc)
    if not raw:
        return None

    match = re.search(r"""['"]correlation_id['"]\s*[:=]\s*['"]([^'"]+)['"]""", raw)
    if match:
        return match.group(1)
    return None


def _with_debug_suffix(
    message: str, *, debug: bool, codes: list[str], correlation_id: str | None
) -> str:
    """Append debug context to a single error string without changing payload shape."""
    if not debug:
        return message

    parts: list[str] = []
    if codes:
        parts.append(f"codes={','.join(codes)}")
    if correlation_id:
        parts.append(f"correlation_id={correlation_id}")

    if not parts:
        return message
    return f"{message} (debug: {'; '.join(parts)})"


def map_delete_card_error_to_message(
    *, card_id: int, card_title: str, codes: list[str]
) -> str:
    """Map GraphQL error codes to PRD-compliant friendly messages for delete_card."""
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
