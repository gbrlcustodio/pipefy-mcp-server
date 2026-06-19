"""Pure helpers for phase inventory read error mapping."""

from __future__ import annotations

_GET_PHASE_NOT_FOUND_MARKERS = (
    "phase.cards_count missing from response",
    "phase id missing from response",
)


def get_phase_not_found_message(phase_id: str | int) -> str:
    return f"Phase {phase_id} not found or access denied."


def is_get_phase_not_found_error(exc: BaseException) -> bool:
    return isinstance(exc, ValueError) and any(
        marker in str(exc) for marker in _GET_PHASE_NOT_FOUND_MARKERS
    )
