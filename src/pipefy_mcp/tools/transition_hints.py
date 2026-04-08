"""Shared copy for phase transition validation (UI rules vs GraphQL read-only)."""

from __future__ import annotations

TRANSITION_RULES_HINT = (
    "Phase transition rules are configured in the Pipefy UI "
    "(Pipe settings → Phase → Connections) and are not editable via API. "
    "Use get_phase_allowed_move_targets on the source phase to list valid destinations "
    "(GraphQL field phase.cards_can_be_moved_to_phases)."
)


def format_allowed_destinations_phrase(allowed_phases: list[dict]) -> str:
    """Human-readable list of phase names and IDs for error messages.

    Args:
        allowed_phases: Items with ``id`` and optional ``name`` (GraphQL Phase rows).
    """
    if not allowed_phases:
        return "(none configured)"
    parts: list[str] = []
    for p in allowed_phases:
        pid = p.get("id")
        name = p.get("name") or ""
        if name and pid is not None:
            parts.append(f"{name} ({pid})")
        elif pid is not None:
            parts.append(str(pid))
    return ", ".join(parts) if parts else "(none configured)"
