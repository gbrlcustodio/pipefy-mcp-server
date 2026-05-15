"""Pre-flight validators for traditional automation creation.

These guards run before the API call so callers receive a clear, actionable
message instead of an opaque ``INTERNAL_SERVER_ERROR`` from Pipefy. The
:class:`AutomationPreflightError` exception is used so surfaces (MCP tools,
CLI commands) can distinguish preflight failures from transport errors.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pipefy_sdk.transition_hints import (
    TRANSITION_RULES_HINT,
    format_allowed_destinations_phrase,
)

if TYPE_CHECKING:
    from pipefy_sdk.client import PipefyClient

logger = logging.getLogger(__name__)

# Traditional automation action IDs that move the current card to another phase (same repo).
_AUTOMATION_MOVE_CARD_ACTION_IDS = frozenset({"move_single_card"})


class AutomationPreflightError(ValueError):
    """Raised when a traditional automation fails pre-flight validation.

    Surfaces should catch this and convert it to their native error envelope
    (MCP: ``build_automation_error_payload``; CLI: ``typer.BadParameter``).
    """


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


async def validate_traditional_automation_move_transition(
    client: PipefyClient,
    trigger_id: str,
    action_id: str,
    extra_input: Any,
) -> None:
    """Raise :class:`AutomationPreflightError` if a move-card automation has an impossible transition.

    Only runs when the trigger is ``card_moved`` with ``to_phase_id``, the action
    is a same-pipe move action, and ``extra_input`` exposes source/destination
    phase ids. No-op otherwise. ``get_phase_allowed_move_targets`` failures are
    logged and silently skipped — preflight should never block legitimate creates
    because of upstream flakiness.

    Args:
        client: Pipefy facade.
        trigger_id: Rule trigger (e.g. ``card_moved``).
        action_id: Rule action id from the catalog (e.g. ``move_single_card``).
        extra_input: Optional ``CreateAutomationInput``-style dict (event_params, action_params).
    """
    if str(trigger_id) != "card_moved":
        return
    aid = str(action_id)
    if aid not in _AUTOMATION_MOVE_CARD_ACTION_IDS:
        return
    extra = extra_input if isinstance(extra_input, dict) else {}
    ev = extra.get("event_params") or extra.get("eventParams") or {}
    src = ev.get("to_phase_id") or ev.get("toPhaseId")
    if not src:
        return
    src_s = str(src)
    act = extra.get("action_params") or extra.get("actionParams") or {}
    dest = act.get("to_phase_id") or act.get("toPhaseId")
    phase_nested = act.get("phase")
    if dest is None and isinstance(phase_nested, dict):
        dest = phase_nested.get("id")
    if not dest:
        return
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
        return
    ph = data.get("phase") or {}
    allowed = ph.get("cards_can_be_moved_to_phases") or []
    allowed_ids = {str(p.get("id")) for p in allowed if p.get("id") is not None}
    if dest_s in allowed_ids:
        return
    src_name = str(ph.get("name") or "")
    raise AutomationPreflightError(
        collect_automation_move_transition_error_message(
            allowed_phases=allowed,
            source_phase_name=src_name,
            source_phase_id=src_s,
            dest_phase_id=dest_s,
        )
    )


__all__ = [
    "AutomationPreflightError",
    "collect_automation_move_transition_error_message",
    "validate_traditional_automation_move_transition",
]
