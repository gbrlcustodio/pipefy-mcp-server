"""Helpers for validating Pipefy phase transitions (read-only API rules)."""

from __future__ import annotations

import logging
from typing import Any

from pipefy_sdk import PipefyClient
from pipefy_sdk.ai_phase_transition_validation import (
    collect_ai_behavior_move_transition_problems,
)
from pipefy_sdk.transition_hints import (
    TRANSITION_RULES_HINT,
    format_allowed_destinations_phrase,
)

from pipefy_mcp.tools.tool_error_envelope import tool_error

logger = logging.getLogger(__name__)

# Traditional automation action IDs that move the current card to another phase (same repo).
_AUTOMATION_MOVE_CARD_ACTION_IDS = frozenset({"move_single_card"})


async def try_enrich_move_card_to_phase_failure(
    client: PipefyClient,
    card_id: str | int,
    destination_phase_id: str | int,
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
        logger.debug(
            "Move-card error enrichment: get_card failed; skipping enriched message",
            exc_info=True,
        )
        return None
    card = card_payload.get("card") or {}
    current = card.get("current_phase") or {}
    cur_id = current.get("id")
    cur_name = str(current.get("name") or "")
    if cur_id is None:
        return None
    try:
        phase_payload = await client.get_phase_allowed_move_targets(cur_id)
    except Exception:
        logger.debug(
            "Move-card error enrichment: get_phase_allowed_move_targets failed; "
            "skipping enriched message (phase_id=%s)",
            cur_id,
            exc_info=True,
        )
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
    out: dict[str, Any] = tool_error(msg)
    out["valid_destinations"] = allowed
    out["current_phase"] = {"id": str(cur_id), "name": cur_name or None}
    return out


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
        data = await client.get_phase_allowed_move_targets(src_s)
    except Exception:  # noqa: BLE001
        logger.debug(
            "Traditional automation move-transition validation: "
            "get_phase_allowed_move_targets failed; skipping validation "
            "(phase_id=%s)",
            src_s,
            exc_info=True,
        )
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
