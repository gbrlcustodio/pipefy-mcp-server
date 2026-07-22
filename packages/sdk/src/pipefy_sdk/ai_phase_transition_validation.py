"""AI agent behavior validation against phase transition rules."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from pipefy_sdk.client import PipefyClient
from pipefy_sdk.models import BehaviorPayload
from pipefy_sdk.transition_hints import (
    TRANSITION_RULES_HINT,
    format_allowed_destinations_phrase,
)

logger = logging.getLogger(__name__)


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
                data = await client.get_phase_allowed_move_targets(phase_id_str)
            except Exception:  # noqa: BLE001
                logger.debug(
                    "AI behavior transition validation: "
                    "get_phase_allowed_move_targets failed; "
                    "skipping validation for phase_id=%s",
                    phase_id_str,
                    exc_info=True,
                )
                cache[phase_id_str] = ("", [])
            else:
                ph = data.get("phase") or {}
                cache[phase_id_str] = (
                    str(ph.get("name") or ""),
                    ph.get("cards_can_be_moved_to_phases") or [],
                )
        return cache[phase_id_str]

    for i, b in enumerate(behaviors):
        try:
            payload = BehaviorPayload.model_validate(b)
        except ValidationError:
            continue
        event_id = str(payload.event_id or "")
        if event_id != "card_moved":
            continue
        ep = payload.event_params
        src = ep.to_phase_id if ep else None
        if not src:
            continue
        src_s = str(src)
        bname = payload.name or f"<behavior {i}>"
        prefix = f'Behavior [{i}] "{bname}"'

        abp = (
            payload.action_params.ai_behavior_params if payload.action_params else None
        )
        attrs = (abp.actions_attributes if abp else None) or []
        for j, action in enumerate(attrs):
            if action.action_type != "move_card":
                continue
            meta = action.metadata if isinstance(action.metadata, dict) else {}
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


__all__ = ["collect_ai_behavior_move_transition_problems"]
