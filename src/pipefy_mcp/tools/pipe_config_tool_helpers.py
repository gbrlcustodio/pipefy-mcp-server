from __future__ import annotations

import asyncio
from typing import Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.graphql_error_helpers import (
    handle_tool_graphql_error,
)
from pipefy_mcp.tools.tool_error_envelope import ToolErrorDetail, tool_error
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
    condition_id: str, action: str
) -> FieldConditionMutationSuccessPayload:
    """Field condition mutation envelope with canned ``message``.

    Args:
        condition_id: ID returned by the API.
        action: ``created`` or ``updated`` (echoed to clients).
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


async def find_phase_field_dependents(
    client: PipefyClient,
    *,
    phase_id: str,
    field_internal_id: str | None,
    field_uuid: str | None,
    field_slug: str | None,
) -> list[dict[str, Any]]:
    """Return field conditions on ``phase_id`` whose actions reference the field."""
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
        for action in actions:
            if not isinstance(action, dict):
                continue
            raw_pf = action.get("phaseFieldId")
            if raw_pf is not None and str(raw_pf) in targets:
                out.append(
                    {
                        "id": cond.get("id"),
                        "name": cond.get("name"),
                        "action_count": len(actions),
                    }
                )
                break
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
    "normalize_field_condition_actions",
    "resolve_phase_dependents",
    "resolve_phase_field_identifiers",
    "strip_expression_ids_for_create",
]
