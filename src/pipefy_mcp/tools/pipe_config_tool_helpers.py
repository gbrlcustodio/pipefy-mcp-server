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
from pipefy_mcp.tools.validation_helpers import UUID_RE


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


class FieldConditionMutationSuccessPayload(TypedDict):
    """Structured success response for create/update field condition tools."""

    success: Literal[True]
    condition_id: str
    action: str
    message: str


class FieldConditionDeleteSuccessPayload(TypedDict):
    success: Literal[True]
    message: str


class FieldConditionDeleteFailurePayload(TypedDict):
    success: Literal[False]
    message: str


FieldConditionDeletePayload = (
    FieldConditionDeleteSuccessPayload | FieldConditionDeleteFailurePayload
)


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


def build_field_condition_success_payload(
    condition_id: str, action: str
) -> FieldConditionMutationSuccessPayload:
    """Build a success payload for create_field_condition / update_field_condition.

    Args:
        condition_id: Field condition ID returned by the API.
        action: ``'created'`` or ``'updated'`` (passed through for clients).
    """
    return {
        "success": True,
        "condition_id": condition_id,
        "action": action,
        "message": f"Field condition {action} (ID: {condition_id}).",
    }


def build_field_condition_delete_payload(
    success: bool,
) -> FieldConditionDeletePayload:
    """Build a payload for delete_field_condition after the API responds.

    Args:
        success: Whether ``deleteFieldCondition`` reported success.
    """
    if success:
        return {
            "success": True,
            "message": "Field condition was permanently deleted.",
        }
    return {
        "success": False,
        "message": "Field condition could not be deleted.",
    }


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


def field_condition_phase_field_id_looks_like_slug(value: object) -> bool:
    """True when ``value`` is probably a phase field slug (``id``) instead of ``internal_id``."""
    if isinstance(value, int):
        return False
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    if UUID_RE.fullmatch(s):
        return False
    if s.isdigit():
        return False
    return any(c.isalpha() for c in s)


def normalize_field_condition_actions(
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Shallow-copy each action and map legacy ``hidden`` → ``hide``."""
    normalized: list[dict[str, Any]] = []
    for item in actions:
        row = dict(item)
        aid = row.get("actionId")
        if isinstance(aid, str) and aid.strip().lower() == "hidden":
            row["actionId"] = "hide"
        normalized.append(row)
    return normalized


def strip_expression_ids_for_create(condition: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``condition`` with ``id`` removed and nested ints coerced.

    Output keys mirror the input ``condition`` (typically ``expressions``,
    ``expressions_structure``, plus any other ``ConditionInput`` fields present).

    ``ConditionExpressionInput.id`` is a persisted primary key — sending arbitrary
    client tokens on create causes ``RECORD_NOT_FOUND``. ``structure_id`` is coerced
    to ``int`` for consistency (GraphQL ``ID`` scalar).
    """
    expressions = condition.get("expressions")

    def _coerce_int(value: Any) -> Any:
        try:
            return int(value)
        except (ValueError, TypeError):
            return value

    if not isinstance(expressions, list):
        return condition
    cleaned: list[dict[str, Any]] = []
    for expr in expressions:
        row = {k: v for k, v in expr.items() if k != "id"}
        sid = row.get("structure_id")
        if sid is not None:
            try:
                row["structure_id"] = int(sid)
            except (ValueError, TypeError):
                pass
        cleaned.append(row)
    es = condition.get("expressions_structure")
    if isinstance(es, list):
        coerced_ints: list[list[Any]] = []
        for group in es:
            if isinstance(group, list):
                coerced_ints.append([_coerce_int(v) for v in group])
            else:
                coerced_ints.append([_coerce_int(group)])
        return {
            **condition,
            "expressions": cleaned,
            "expressions_structure": coerced_ints,
        }
    return {**condition, "expressions": cleaned}


def field_condition_actions_error_message(
    actions: list[dict[str, Any]],
) -> str | None:
    """Return an error string when ``actions`` fails validation, else ``None``."""
    if not isinstance(actions, list) or not actions:
        return "Invalid 'actions': provide a non-empty list of action objects."
    if not all(isinstance(item, dict) for item in actions):
        return "Invalid 'actions': each item must be an object/dict."
    for index, item in enumerate(actions):
        raw_id = item.get("phaseFieldId")
        if raw_id is None:
            continue
        if field_condition_phase_field_id_looks_like_slug(raw_id):
            return (
                f"Invalid actions[{index}] 'phaseFieldId': value looks like a field "
                "slug (the `id` from get_phase_fields), but Pipefy expects "
                "`internal_id` from get_phase_fields for field-condition actions. "
                "See README (Field condition tools)."
            )
    return None


__all__ = [
    "DeletePipeErrorPayload",
    "DeletePipePayload",
    "DeletePipePreviewPayload",
    "DeletePipeSuccessPayload",
    "FieldConditionDeleteFailurePayload",
    "FieldConditionDeletePayload",
    "FieldConditionDeleteSuccessPayload",
    "FieldConditionMutationSuccessPayload",
    "PipeMutationSuccessPayload",
    "build_delete_pipe_error_payload",
    "build_delete_pipe_preview_payload",
    "build_delete_pipe_success_payload",
    "build_field_condition_delete_payload",
    "build_field_condition_success_payload",
    "build_pipe_mutation_success_payload",
    "build_pipe_tool_error_payload",
    "field_condition_actions_error_message",
    "field_condition_phase_field_id_looks_like_slug",
    "handle_pipe_config_tool_graphql_error",
    "map_delete_pipe_error_to_message",
    "normalize_field_condition_actions",
    "strip_expression_ids_for_create",
]
