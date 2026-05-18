"""Helpers for validating Pipefy phase transitions (read-only API rules)."""

from __future__ import annotations

import logging
from typing import Any

from pipefy_sdk import PipefyClient
from pipefy_sdk.transition_hints import (
    TRANSITION_RULES_HINT,
    format_allowed_destinations_phrase,
)

from pipefy_mcp.tools.tool_error_envelope import tool_error

logger = logging.getLogger(__name__)


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


__all__ = [
    "try_enrich_move_card_to_phase_failure",
]
