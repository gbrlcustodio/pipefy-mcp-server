from __future__ import annotations

import asyncio
from typing import Any, Literal, cast

from pipefy_sdk import PipefyClient
from typing_extensions import NotRequired, TypedDict

from pipefy_mcp.core.tool_error_envelope import ToolErrorDetail, tool_error
from pipefy_mcp.tools.graphql_error_helpers import (
    handle_tool_graphql_error,
)
from pipefy_mcp.tools.validation_helpers import UUID_RE, format_json_preview


class DeletePipePreviewPayload(TypedDict):
    success: Literal[False]
    requires_confirmation: Literal[True]
    pipe_id: str | int
    message: str
    pipe_summary: str


class DeletePipeSuccessPayload(TypedDict):
    success: Literal[True]
    pipe_id: str | int
    message: str


class DeletePipeErrorPayload(TypedDict):
    success: Literal[False]
    error: ToolErrorDetail


DeletePipePayload = (
    DeletePipePreviewPayload | DeletePipeSuccessPayload | DeletePipeErrorPayload
)


class PipeMutationSuccessPayload(TypedDict):
    """Pipe create/update/clone tool success shape."""

    success: Literal[True]
    message: str
    result: dict[str, Any]


class FieldConditionMutationSuccessPayload(TypedDict):
    """Field condition create/update success shape."""

    success: Literal[True]
    condition_id: str
    action: str
    message: str
    verified: NotRequired[bool]
    warning: NotRequired[str]


class FieldConditionDeleteSuccessPayload(TypedDict):
    success: Literal[True]
    message: str


class FieldConditionDeleteFailurePayload(TypedDict):
    success: Literal[False]
    message: str


FieldConditionDeletePayload = (
    FieldConditionDeleteSuccessPayload | FieldConditionDeleteFailurePayload
)


def handle_pipe_config_tool_graphql_error(
    exc: BaseException,
    fallback_msg: str,
    *,
    debug: bool = False,
    resource_kind: str | None = None,
    resource_id: str | None = None,
    invalid_args_hint: str | None = None,
) -> dict[str, Any]:
    """Delegate to :func:`handle_tool_graphql_error` with enrichment opt-ins."""
    return handle_tool_graphql_error(
        exc,
        fallback_msg,
        debug=debug,
        resource_kind=resource_kind,
        resource_id=resource_id,
        invalid_args_hint=invalid_args_hint,
    )


def build_pipe_mutation_success_payload(
    *, label: str, data: dict[str, Any]
) -> PipeMutationSuccessPayload:
    """``success``, ``message`` (``label``), and raw GraphQL ``result`` dict.

    Args:
        label: Short summary shown as ``message``.
        data: Full mutation response subtree (not a JSON string).
    """
    return cast(
        PipeMutationSuccessPayload,
        {"success": True, "message": label, "result": data},
    )


def build_pipe_tool_error_payload(
    *, message: str, code: str | None = None
) -> dict[str, Any]:
    """``success: False`` with ``error`` text.

    Args:
        message: User-visible failure reason.
        code: Optional machine-readable error code. Pass
            ``"INVALID_ARGUMENTS"`` for pre-API argument-shape failures so
            the envelope matches the shape of arg-coercion errors
            emitted by :class:`pipefy_mcp.tools.validation_envelope.PipefyValidationTool`.
    """
    return tool_error(message, code=code)


def build_field_condition_success_payload(
    condition_id: str,
    action: str,
    *,
    verified: bool | None = None,
    warning: str | None = None,
) -> FieldConditionMutationSuccessPayload:
    """Field condition mutation envelope with canned ``message``.

    Args:
        condition_id: ID returned by the API.
        action: ``created`` or ``updated`` (echoed to clients).
        verified: When True, post-create read-back confirmed the rule on the
            requested phase.
        warning: Optional note (e.g. verify reads unavailable).
    """
    payload: FieldConditionMutationSuccessPayload = {
        "success": True,
        "condition_id": condition_id,
        "action": action,
        "message": f"Field condition {action} (ID: {condition_id}).",
    }
    if verified is not None:
        payload["verified"] = verified
    if warning is not None:
        payload["warning"] = warning
    return payload


def build_field_condition_delete_payload(
    success: bool,
) -> FieldConditionDeletePayload:
    """Post-delete API response as MCP-friendly dict.

    Args:
        success: Value of ``deleteFieldCondition.success``.
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
    pipe_id: str | int,
    pipe_name: str,
    pipe_data: dict[str, Any],
) -> DeletePipePreviewPayload:
    """Two-step delete: preview before ``confirm=True``.

    Args:
        pipe_id: Target pipe id.
        pipe_name: Display name for messaging.
        pipe_data: Subset serialized into ``pipe_summary``.
    """
    return {
        "success": False,
        "requires_confirmation": True,
        "pipe_id": pipe_id,
        "pipe_summary": format_json_preview(
            {
                "id": pipe_data.get("id"),
                "name": pipe_name,
                "phases": pipe_data.get("phases"),
            }
        ),
        "message": (
            "Warning: You are about to permanently delete pipe "
            f"'{pipe_name}' (ID: {pipe_id}). "
            "This cannot be undone. Confirm with the user, then call again with confirm=True."
        ),
    }


def build_delete_pipe_success_payload(
    *, pipe_id: str | int
) -> DeletePipeSuccessPayload:
    """Confirmed pipe deletion.

    Args:
        pipe_id: Deleted pipe id.
    """
    return {
        "success": True,
        "pipe_id": pipe_id,
        "message": f"Pipe {pipe_id} was permanently deleted.",
    }


def build_delete_pipe_error_payload(*, message: str) -> DeletePipeErrorPayload:
    """Failed delete_pipe attempt.

    Args:
        message: User-visible failure reason.
    """
    return cast(DeletePipeErrorPayload, tool_error(message))


def map_delete_pipe_error_to_message(
    *, pipe_id: str | int, pipe_name: str, codes: list[str]
) -> str:
    """Heuristic user string from GraphQL ``extensions.code`` for delete_pipe."""
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


_MAX_CONDITION_TREE_DEPTH = 16


def _condition_tree_references_targets(
    obj: Any, targets: set[str], depth: int = 0
) -> bool:
    """Return True if any node in the condition subtree references one of the targets."""
    if not targets:
        return False
    if depth > _MAX_CONDITION_TREE_DEPTH:
        return False
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in ("field_address", "phaseFieldId") and val is not None:
                if str(val).strip() in targets:
                    return True
            if _condition_tree_references_targets(val, targets, depth + 1):
                return True
        return False
    if isinstance(obj, list):
        return any(
            _condition_tree_references_targets(item, targets, depth + 1) for item in obj
        )
    return False


async def find_phase_field_dependents(
    client: PipefyClient,
    *,
    phase_id: str,
    field_internal_id: str | None,
    field_uuid: str | None,
    field_slug: str | None,
) -> list[dict[str, Any]]:
    """Return field conditions on ``phase_id`` that reference the field in actions or conditions."""
    try:
        payload = await client.get_field_conditions(phase_id)
    except Exception:  # noqa: BLE001
        return []
    phase = (payload or {}).get("phase") or {}
    conditions = phase.get("fieldConditions") or []
    targets = {str(t) for t in (field_internal_id, field_uuid, field_slug) if t}
    out: list[dict[str, Any]] = []
    for cond in conditions:
        if not isinstance(cond, dict):
            continue
        actions = cond.get("actions") or []
        matched = False
        for action in actions:
            if not isinstance(action, dict):
                continue
            raw_pf = action.get("phaseFieldId")
            if raw_pf is not None and str(raw_pf) in targets:
                matched = True
                break
        if not matched and _condition_tree_references_targets(
            cond.get("condition"), targets
        ):
            matched = True
        if matched:
            out.append(
                {
                    "id": cond.get("id"),
                    "name": cond.get("name"),
                    "action_count": len(actions) if isinstance(actions, list) else 0,
                }
            )
    return out


async def resolve_phase_field_identifiers(
    client: PipefyClient,
    phase_id: str,
    field_id: str,
) -> dict[str, Any]:
    """Map a phase field token to internal_id / uuid / slug when present."""
    try:
        payload = await client.get_phase_fields(phase_id)
    except Exception:  # noqa: BLE001
        return {}
    fields = (payload or {}).get("fields") or []
    needle = str(field_id).strip()
    for field in fields:
        if not isinstance(field, dict):
            continue
        internal = field.get("internal_id")
        uuid_val = field.get("uuid")
        slug = field.get("id")
        candidates = {
            str(x)
            for x in (internal, uuid_val, slug)
            if x is not None and str(x).strip()
        }
        if needle in candidates:
            out: dict[str, Any] = {}
            if internal is not None:
                out["internal_id"] = str(internal)
            if uuid_val is not None:
                out["uuid"] = str(uuid_val)
            if slug is not None:
                out["slug"] = str(slug)
            return out
    return {}


def _field_conditions_list_from_get_payload(payload: object) -> list[dict[str, Any]]:
    """Unwrap field conditions from ``get_field_conditions`` (GraphQL ``phase.fieldConditions``)."""
    if not isinstance(payload, dict):
        return []
    raw_phase = payload.get("phase")
    if isinstance(raw_phase, dict):
        rows = raw_phase.get("fieldConditions")
        if isinstance(rows, list):
            return [c for c in rows if isinstance(c, dict)]
    return []


def _automation_mentions_phase(automation: dict[str, Any], phase_id: str) -> bool:
    """True when any trigger/action parameter references the given phase id."""
    key = str(phase_id)
    event_params = automation.get("event_params")
    if isinstance(event_params, dict):
        for attr in (
            "fromPhaseId",
            "inPhaseId",
            "to_phase_id",
        ):
            v = event_params.get(attr)
            if v is not None and str(v) == key:
                return True
        ep = event_params.get("phase")
        if isinstance(ep, dict) and str(ep.get("id") or "") == key:
            return True
    action_params = automation.get("action_params")
    if isinstance(action_params, dict):
        to_ph = action_params.get("to_phase_id")
        if to_ph is not None and str(to_ph) == key:
            return True
        ap = action_params.get("phase")
        if isinstance(ap, dict) and str(ap.get("id") or "") == key:
            return True
    return False


def _filter_automations_by_phase(
    full_automations: list[dict[str, Any]],
    phase_id: str,
) -> list[dict[str, Any]]:
    """Keep automations whose event/action configuration references ``phase_id``."""
    out: list[dict[str, Any]] = []
    for row in full_automations:
        if _automation_mentions_phase(row, str(phase_id)):
            out.append(
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                }
            )
    return out


def _build_phase_dependents_hint(deps: dict[str, Any]) -> str:
    """Human-readable count summary of phase dependents for destructive preview."""
    cards = deps.get("cards_count")
    field_count = deps.get("phase_fields_count")
    conditions = deps.get("field_conditions")
    automations = deps.get("automations")
    n_cond = len(conditions) if isinstance(conditions, list) else 0
    n_auto = len(automations) if isinstance(automations, list) else 0

    phrases: list[str] = []
    if isinstance(cards, int):
        phrases.append(f"{cards} card(s)")
    if isinstance(field_count, int):
        phrases.append(f"{field_count} phase field(s)")
    if n_cond:
        phrases.append(
            f"{n_cond} field condition(s)" if n_cond != 1 else "1 field condition"
        )
    if n_auto:
        phrases.append(f"{n_auto} automation(s)" if n_auto != 1 else "1 automation")

    if not phrases:
        return "Deleting this phase is irreversible."

    if len(phrases) == 1:
        body = phrases[0]
    elif len(phrases) == 2:
        body = f"{phrases[0]} and {phrases[1]}"
    else:
        body = ", ".join(phrases[:-1]) + f" and {phrases[-1]}"
    return f"Deleting this phase will remove {body}. This action is irreversible."


async def _automations_referencing_phase(
    client: PipefyClient, pipe_id: str, phase_id: str
) -> list[dict[str, Any]]:
    """List automations in ``pipe_id`` whose config references ``phase_id`` (summary rows).

    Returns a filtered summary list. Exceptions propagate to the outer gather.
    Inner per-automation detail fetches are allowed to fail individually.
    """
    rows = await client.get_automations(pipe_id=str(pipe_id))
    if not rows:
        return []
    ids = [str(r.get("id")) for r in rows if isinstance(r, dict) and r.get("id")]
    if not ids:
        return []
    full_list = await asyncio.gather(
        *[client.get_automation(i) for i in ids],
        return_exceptions=True,
    )
    full_rows: list[dict[str, Any]] = [
        item for item in full_list if isinstance(item, dict) and item
    ]
    return _filter_automations_by_phase(full_rows, str(phase_id))


async def resolve_phase_dependents(
    client: PipefyClient, *, pipe_id: str, phase_id: str
) -> dict[str, Any] | None:
    """Plan-dependent facts for delete-phase preview: conditions, automations, counts, hint.

    Sub-lookups run in parallel via :func:`asyncio.gather` with
    ``return_exceptions=True``. If a sub-lookup fails, its key is omitted. When
    every lookup is empty or failed, returns ``None`` (the guard then emits
    the preview without a ``dependents`` key).

    The card count uses :meth:`PipefyClient.get_phase_cards_count` — the native
    ``Phase.cards_count`` scalar. Pipefy's ``CardSearch`` input does not expose
    a phase filter, so the historical ``cards(search: {inbox_phase_id})`` path
    would not actually restrict cards to the phase.
    """
    p_id = str(pipe_id).strip()
    ph_id = str(phase_id).strip()
    if not p_id or not ph_id:
        return None

    results = await asyncio.gather(
        client.get_field_conditions(ph_id),
        _automations_referencing_phase(client, p_id, ph_id),
        client.get_phase_cards_count(ph_id),
        client.get_phase_fields(ph_id),
        return_exceptions=True,
    )
    labels = (
        "field_conditions",
        "automations",
        "cards_count",
        "phase_fields",
    )
    rmap = dict(zip(labels, results, strict=True))
    out: dict[str, Any] = {}

    fc = rmap["field_conditions"]
    if not isinstance(fc, BaseException):
        conds = _field_conditions_list_from_get_payload(fc)
        if conds:
            out["field_conditions"] = [
                {"id": c.get("id"), "name": c.get("name")} for c in conds
            ]
    aut = rmap["automations"]
    if not isinstance(aut, BaseException) and aut:
        out["automations"] = aut
    cc = rmap["cards_count"]
    if not isinstance(cc, BaseException) and isinstance(cc, int):
        out["cards_count"] = cc

    pf = rmap["phase_fields"]
    if not isinstance(pf, BaseException):
        fields = (pf or {}).get("fields") or []
        if isinstance(fields, list):
            out["phase_fields_count"] = len([f for f in fields if isinstance(f, dict)])

    if not out:
        return None
    out["hint"] = _build_phase_dependents_hint(out)
    return out


def normalize_phase_allowed_move_targets(
    raw: dict[str, Any],
) -> dict[str, Any] | None:
    phase = (raw or {}).get("phase")
    if not isinstance(phase, dict):
        return None
    phase_id = phase.get("id")
    if phase_id is None:
        return None
    allowed_raw = phase.get("cards_can_be_moved_to_phases") or []
    allowed_phases: list[dict[str, str]] = []
    if isinstance(allowed_raw, list):
        for item in allowed_raw:
            if not isinstance(item, dict):
                continue
            dest_id = item.get("id")
            if dest_id is None:
                continue
            allowed_phases.append(
                {
                    "id": str(dest_id),
                    "name": str(item.get("name") or ""),
                }
            )
    return {
        "phase_id": str(phase_id),
        "phase_name": str(phase.get("name") or ""),
        "allowed_phases": allowed_phases,
    }


def normalize_phase_cards_list(raw: dict[str, Any]) -> dict[str, Any] | None:
    phase = (raw or {}).get("phase")
    if not isinstance(phase, dict) or phase.get("id") is None:
        return None
    return phase


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
    "find_phase_field_dependents",
    "handle_pipe_config_tool_graphql_error",
    "map_delete_pipe_error_to_message",
    "normalize_phase_allowed_move_targets",
    "normalize_phase_cards_list",
    "resolve_phase_dependents",
    "resolve_phase_field_identifiers",
]
