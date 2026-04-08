"""Helpers for validating Pipefy phase transitions (read-only API rules)."""

from __future__ import annotations

from typing import Any

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.transition_hints import (
    TRANSITION_RULES_HINT,
    format_allowed_destinations_phrase,
)

# Traditional automation action IDs that move the current card to another phase (same repo).
_AUTOMATION_MOVE_CARD_ACTION_IDS = frozenset({"move_single_card"})


async def try_enrich_move_card_to_phase_failure(
    client: PipefyClient,
    card_id: int,
    destination_phase_id: int,
) -> dict[str, Any] | None:
    """If the card cannot move to ``destination_phase_id`` from its current phase, build an error payload.

    Used after ``moveCardToPhase`` fails: extra GraphQL calls only on the error path.
    Returns ``None`` when enrichment is not possible or the destination is already allowed
    (caller should surface the original API error).

    Args:
        client: Pipefy facade.
        card_id: Card that was being moved.
        destination_phase_id: Requested destination phase ID.

    Returns:
        Dict with ``success: False``, ``error``, ``valid_destinations``, ``current_phase``; or ``None``.
    """
    try:
        card_payload = await client.get_card(card_id, include_fields=False)
    except Exception:
        return None
    card = card_payload.get("card") or {}
    current = card.get("current_phase") or {}
    cur_id = current.get("id")
    cur_name = str(current.get("name") or "")
    if cur_id is None:
        return None
    try:
        phase_payload = await client.get_phase_allowed_move_targets(int(cur_id))
    except Exception:
        return None
    phase = phase_payload.get("phase") or {}
    allowed = phase.get("cards_can_be_moved_to_phases") or []
    dest_str = str(destination_phase_id)
    allowed_ids = {str(p.get("id")) for p in allowed if p.get("id") is not None}
    if dest_str in allowed_ids:
        return None

    valid_label = format_allowed_destinations_phrase(allowed)
    from_label = f"'{cur_name}'" if cur_name else f"id {cur_id}"
    msg = (
        f"Cannot move card from phase {from_label} (id {cur_id}) to destination phase "
        f"id {destination_phase_id}. Valid destinations from that phase: {valid_label}. "
        f"{TRANSITION_RULES_HINT}"
    )
    return {
        "success": False,
        "error": msg,
        "valid_destinations": allowed,
        "current_phase": {"id": str(cur_id), "name": cur_name or None},
    }


async def collect_ai_behavior_move_transition_problems(
    client: PipefyClient,
    behaviors: list[dict[str, Any]],
) -> list[str]:
    """Append-style validation: ``move_card`` when trigger is ``card_moved`` with ``to_phase_id``.

    The card is in ``eventParams.to_phase_id`` when the behavior runs; the move action's
    ``destinationPhaseId`` must appear in that phase's ``cards_can_be_moved_to_phases``.

    Args:
        client: Pipefy facade.
        behaviors: Raw behavior dicts (camelCase or snake_case keys).

    Returns:
        Human-readable problem strings (empty if none).
    """
    problems: list[str] = []
    cache: dict[str, tuple[str, list[dict]]] = {}

    async def phase_context(phase_id_str: str) -> tuple[str, list[dict]]:
        if phase_id_str not in cache:
            try:
                data = await client.get_phase_allowed_move_targets(int(phase_id_str))
            except Exception:
                cache[phase_id_str] = ("", [])
            else:
                ph = data.get("phase") or {}
                cache[phase_id_str] = (
                    str(ph.get("name") or ""),
                    ph.get("cards_can_be_moved_to_phases") or [],
                )
        return cache[phase_id_str]

    for i, b in enumerate(behaviors):
        event_id = str(b.get("event_id") or b.get("eventId") or "")
        if event_id != "card_moved":
            continue
        ep = b.get("eventParams") or b.get("event_params") or {}
        src = ep.get("to_phase_id") or ep.get("toPhaseId")
        if not src:
            continue
        src_s = str(src)
        bname = b.get("name", f"<behavior {i}>")
        prefix = f'Behavior [{i}] "{bname}"'

        ap = b.get("actionParams") or b.get("action_params") or {}
        abp = ap.get("aiBehaviorParams") or ap.get("ai_behavior_params") or {}
        attrs = abp.get("actionsAttributes") or abp.get("actions_attributes") or []
        for j, action in enumerate(attrs):
            if not isinstance(action, dict):
                continue
            if action.get("actionType") != "move_card":
                continue
            meta = action.get("metadata") or {}
            dest = meta.get("destinationPhaseId")
            if not dest:
                continue
            dest_s = str(dest)
            src_name, allowed = await phase_context(src_s)
            allowed_ids = {str(p.get("id")) for p in allowed if p.get("id") is not None}
            if dest_s in allowed_ids:
                continue
            dest_name = ""
            for p in allowed:
                if str(p.get("id")) == dest_s:
                    dest_name = str(p.get("name") or "")
                    break
            src_label = f"'{src_name}'" if src_name else f"id {src_s}"
            dest_label = f"'{dest_name}'" if dest_name else f"id {dest_s}"
            valid_label = format_allowed_destinations_phrase(allowed)
            problems.append(
                f"{prefix}, action [{j}] (move_card): phase {src_label} cannot move cards "
                f"to {dest_label}. Valid destinations: {valid_label}. {TRANSITION_RULES_HINT}"
            )

    return problems


def collect_automation_move_transition_error_message(
    *,
    allowed_phases: list[dict],
    source_phase_name: str,
    source_phase_id: str,
    dest_phase_id: str,
) -> str:
    """Build blocking error text for traditional automation move rules.

    Args:
        allowed_phases: ``cards_can_be_moved_to_phases`` from the source phase.
        source_phase_name: Name of source phase (may be empty).
        source_phase_id: Source phase id string.
        dest_phase_id: Requested destination phase id string.

    Returns:
        Single message suitable for ``build_automation_error_payload``.
    """
    src_l = f"'{source_phase_name}'" if source_phase_name else f"id {source_phase_id}"
    valid_label = format_allowed_destinations_phrase(allowed_phases)
    return (
        f"This automation would move a card from phase {src_l} (id {source_phase_id}) "
        f"to phase id {dest_phase_id}, which is not an allowed transition. "
        f"Valid destinations from that phase: {valid_label}. {TRANSITION_RULES_HINT}"
    )


async def validate_traditional_automation_move_transition_or_none(
    client: PipefyClient,
    trigger_id: str,
    action_id: str,
    extra_input: Any,
) -> str | None:
    """Return an error message when a move-card automation has an impossible transition; else ``None``.

    Only runs when the trigger is ``card_moved`` with ``to_phase_id``, the action is a same-pipe
    move action, and ``extra_input`` exposes source/destination phase ids.

    Args:
        client: Pipefy facade.
        trigger_id: Rule trigger (e.g. ``card_moved``).
        action_id: Rule action id from the catalog (e.g. ``move_single_card``).
        extra_input: Optional ``CreateAutomationInput``-style dict (event_params, action_params).
    """
    if str(trigger_id) != "card_moved":
        return None
    aid = str(action_id)
    if aid not in _AUTOMATION_MOVE_CARD_ACTION_IDS:
        return None
    extra = extra_input if isinstance(extra_input, dict) else {}
    ev = extra.get("event_params") or extra.get("eventParams") or {}
    src = ev.get("to_phase_id") or ev.get("toPhaseId")
    if not src:
        return None
    src_s = str(src)
    act = extra.get("action_params") or extra.get("actionParams") or {}
    dest = act.get("to_phase_id") or act.get("toPhaseId")
    phase_nested = act.get("phase")
    if dest is None and isinstance(phase_nested, dict):
        dest = phase_nested.get("id")
    if not dest:
        return None
    dest_s = str(dest)
    try:
        data = await client.get_phase_allowed_move_targets(int(src_s))
    except Exception:
        return None
    ph = data.get("phase") or {}
    allowed = ph.get("cards_can_be_moved_to_phases") or []
    allowed_ids = {str(p.get("id")) for p in allowed if p.get("id") is not None}
    if dest_s in allowed_ids:
        return None
    src_name = str(ph.get("name") or "")
    return collect_automation_move_transition_error_message(
        allowed_phases=allowed,
        source_phase_name=src_name,
        source_phase_id=src_s,
        dest_phase_id=dest_s,
    )


__all__ = [
    "collect_ai_behavior_move_transition_problems",
    "collect_automation_move_transition_error_message",
    "try_enrich_move_card_to_phase_failure",
    "validate_traditional_automation_move_transition_or_none",
]
