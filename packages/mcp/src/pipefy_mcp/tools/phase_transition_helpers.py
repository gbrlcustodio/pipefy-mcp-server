"""Helpers for validating Pipefy phase transitions (read-only API rules)."""

from __future__ import annotations

import logging
from typing import Any

from pipefy_sdk import PipefyClient
from pipefy_sdk.transition_hints import (
    TRANSITION_RULES_HINT,
    format_allowed_destinations_phrase,
)

from pipefy_mcp.core.tool_error_envelope import tool_error
from pipefy_mcp.tools.field_condition_planner import (
    enrich_required_field_move_message,
    extract_required_field_label_from_error,
    is_required_hidden_by_label,
    phase_fields_from_payload,
)

logger = logging.getLogger(__name__)


def _actions_from_field_conditions_payload(payload: object) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    phase = payload.get("phase")
    if not isinstance(phase, dict):
        return []
    rows = phase.get("fieldConditions")
    if not isinstance(rows, list):
        return []
    actions: list[Any] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_actions = row.get("actions")
        if not isinstance(row_actions, list):
            continue
        actions.extend(action for action in row_actions if isinstance(action, dict))
    return actions


async def _detect_required_hidden_for_label(
    client: PipefyClient,
    card_id: str | int,
    label: str,
) -> bool:
    """Best-effort: true when the labeled field is required and a hide target."""
    try:
        card_payload = await client.get_card(card_id, include_fields=False)
    except Exception:
        logger.debug(
            "Required-field move enrichment: get_card failed; skipping hide hint",
            exc_info=True,
        )
        return False
    card = card_payload.get("card") or {}
    current = card.get("current_phase") or {}
    cur_id = current.get("id")
    if cur_id is None:
        return False

    try:
        fields_payload = await client.get_phase_fields(cur_id)
    except Exception:
        logger.debug(
            "Required-field move enrichment: get_phase_fields failed "
            "(phase_id=%s); skipping hide hint",
            cur_id,
            exc_info=True,
        )
        return False

    try:
        conditions_payload = await client.get_field_conditions(cur_id)
    except Exception:
        logger.debug(
            "Required-field move enrichment: get_field_conditions failed "
            "(phase_id=%s); skipping hide hint",
            cur_id,
            exc_info=True,
        )
        return False

    return is_required_hidden_by_label(
        phase_fields_from_payload(fields_payload),
        _actions_from_field_conditions_payload(conditions_payload),
        label,
    )


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


async def try_enrich_required_field_move_failure(
    client: PipefyClient,
    card_id: str | int,
    api_error_message: str,
) -> dict[str, Any] | None:
    """Wrap a required-field move error as ``success: false``, with a hide hint when detected.

    Returns ``None`` when ``api_error_message`` does not match the required-field
    pattern (caller should re-raise the original exception).
    """
    label = extract_required_field_label_from_error(api_error_message)
    if label is None:
        return None

    hidden = await _detect_required_hidden_for_label(client, card_id, label)
    message = enrich_required_field_move_message(
        api_error_message,
        hidden_by_condition=hidden,
    )
    return tool_error(message)


__all__ = [
    "try_enrich_move_card_to_phase_failure",
    "try_enrich_required_field_move_failure",
]
