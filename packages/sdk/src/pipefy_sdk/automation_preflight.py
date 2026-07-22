"""Pre-flight validators for traditional automation creation.

These guards run before the API call so callers receive a clear, actionable
message instead of an opaque ``INTERNAL_SERVER_ERROR`` from Pipefy. The
:class:`AutomationPreflightError` exception is used so surfaces (MCP tools,
CLI commands) can distinguish preflight failures from transport errors.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from pipefy_sdk.models import AutomationEventParamsInput
from pipefy_sdk.transition_hints import (
    TRANSITION_RULES_HINT,
    format_allowed_destinations_phrase,
)

if TYPE_CHECKING:
    from pipefy_sdk.client import PipefyClient

logger = logging.getLogger(__name__)

# Traditional automation action IDs that move the current card to another phase (same repo).
_AUTOMATION_MOVE_CARD_ACTION_IDS = frozenset({"move_single_card"})

_DIGITS_ONLY_RE = re.compile(r"^\d+$")


def _parse_event_params(raw: Any) -> AutomationEventParamsInput | None:
    """Parse a trigger ``event_params`` sub-dict, or ``None`` for missing/malformed input.

    Preflight is advisory and must never turn odd input into a spurious create failure,
    so a payload that fails ``AutomationEventParamsInput`` coercion is treated as absent
    (no-op preflight) rather than raised.
    """
    if not isinstance(raw, dict):
        return None
    try:
        return AutomationEventParamsInput.model_validate(raw)
    except ValidationError:
        return None


class AutomationPreflightError(ValueError):
    """Raised when a traditional automation fails pre-flight validation.

    Surfaces should catch this and convert it to their native error envelope
    (MCP: ``build_automation_error_payload``; CLI: map the message to the CLI's
    usual error path). Subclasses ``ValueError`` so callers that already treat
    domain guard failures as value errors keep working.
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
    extra_input: dict[str, Any] | None,
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
        extra_input: Optional ``CreateAutomationInput``-style dict (``event_params`` /
            ``action_params`` keys in snake_case or camelCase). Non-dict values are
            treated as empty (no-op preflight).
    """
    if str(trigger_id) != "card_moved":
        return
    aid = str(action_id)
    if aid not in _AUTOMATION_MOVE_CARD_ACTION_IDS:
        return
    extra = extra_input if isinstance(extra_input, dict) else {}
    ev = _parse_event_params(extra.get("event_params"))
    src = ev.to_phase_id if ev else None
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


def extract_field_map_destination_ids(
    extra_input: dict[str, Any] | None,
) -> list[str]:
    """Return ``field_map`` destination ``fieldId`` values from ``CreateAutomationInput``-style dicts."""
    if not isinstance(extra_input, dict):
        return []
    act = extra_input.get("action_params") or extra_input.get("actionParams") or {}
    if not isinstance(act, dict):
        return []
    field_map = act.get("field_map") or act.get("fieldMap")
    if not field_map:
        return []
    ids: list[str] = []
    for entry in field_map:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("fieldId") or entry.get("field_id")
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            ids.append(text)
    return ids


def collect_internal_field_ids_from_pipe_info(pipe_info: dict[str, Any]) -> set[str]:
    """Collect numeric ``internal_id`` values from embedded start-form and phase fields."""
    internal_ids: set[str] = set()
    for field in pipe_info.get("start_form_fields") or []:
        if not isinstance(field, dict):
            continue
        iid = field.get("internal_id")
        if iid is not None:
            internal_ids.add(str(iid))
    for phase in pipe_info.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        for field in phase.get("fields") or []:
            if not isinstance(field, dict):
                continue
            iid = field.get("internal_id")
            if iid is not None:
                internal_ids.add(str(iid))
    return internal_ids


def collect_field_map_field_id_error_message(
    *,
    field_id: str,
    action_pipe_id: str,
    non_numeric_slug: bool = False,
) -> str:
    """Build blocking error text for invalid ``field_map`` ``fieldId`` values."""
    discovery = (
        "Discover numeric internal_id values with get_start_form_fields(pipe_id) "
        "or get_phase_fields(phase_id)."
    )
    if non_numeric_slug:
        return (
            f'field_map fieldId "{field_id}" must be the numeric internal_id on pipe '
            f"{action_pipe_id}, not the field slug used by update_card_field. {discovery}"
        )
    return (
        f'field_map fieldId "{field_id}" was not found on pipe {action_pipe_id}. '
        f"{discovery}"
    )


def find_non_numeric_field_map_field_id(destination_ids: list[str]) -> str | None:
    """Return the first slug-shaped ``fieldId``, or ``None`` when all are numeric."""
    for field_id in destination_ids:
        if not _DIGITS_ONLY_RE.match(field_id):
            return field_id
    return None


def find_invalid_field_map_field_id(
    destination_ids: list[str],
    known_internal_ids: set[str],
) -> tuple[str, bool] | None:
    """Return ``(field_id, non_numeric_slug)`` for the first invalid id, or ``None``."""
    for field_id in destination_ids:
        if not _DIGITS_ONLY_RE.match(field_id):
            return (field_id, True)
        if field_id not in known_internal_ids:
            return (field_id, False)
    return None


async def _load_action_pipe_internal_field_ids(
    client: PipefyClient,
    action_pipe_id: str,
) -> set[str] | None:
    try:
        pipe_data = await client.get_pipe(action_pipe_id)
    except Exception:  # noqa: BLE001
        logger.debug(
            "Traditional automation field_map validation: get_pipe failed; "
            "skipping validation (pipe_id=%s)",
            action_pipe_id,
            exc_info=True,
        )
        return None
    pipe_info = pipe_data.get("pipe") or {}
    if not isinstance(pipe_info, dict):
        return set()
    return collect_internal_field_ids_from_pipe_info(pipe_info)


async def validate_automation_field_map_field_ids(
    client: PipefyClient,
    action_pipe_id: str,
    extra_input: dict[str, Any] | None,
) -> None:
    """Raise :class:`AutomationPreflightError` when ``field_map`` references unknown destination fields.

    Only runs when ``extra_input`` includes ``action_params.field_map`` (or camelCase
    equivalents). Compares each ``fieldId`` to numeric ``internal_id`` values on
    ``action_pipe_id`` (the action repo pipe). Upstream field-load failures are logged
    and skipped so preflight does not block creates on transient API errors.

    Args:
        client: Pipefy facade.
        action_pipe_id: Pipe where the action executes (``action_repo_id`` or event pipe).
        extra_input: Optional ``CreateAutomationInput``-style dict.
    """
    destination_ids = extract_field_map_destination_ids(extra_input)
    if not destination_ids:
        return
    slug_field_id = find_non_numeric_field_map_field_id(destination_ids)
    if slug_field_id is not None:
        raise AutomationPreflightError(
            collect_field_map_field_id_error_message(
                field_id=slug_field_id,
                action_pipe_id=action_pipe_id,
                non_numeric_slug=True,
            )
        )
    known_internal_ids = await _load_action_pipe_internal_field_ids(
        client, action_pipe_id
    )
    if known_internal_ids is None:
        return
    invalid = find_invalid_field_map_field_id(destination_ids, known_internal_ids)
    if invalid is None:
        return
    field_id, non_numeric_slug = invalid
    raise AutomationPreflightError(
        collect_field_map_field_id_error_message(
            field_id=field_id,
            action_pipe_id=action_pipe_id,
            non_numeric_slug=non_numeric_slug,
        )
    )


__all__ = [
    "AutomationPreflightError",
    "collect_automation_move_transition_error_message",
    "collect_field_map_field_id_error_message",
    "collect_internal_field_ids_from_pipe_info",
    "extract_field_map_destination_ids",
    "find_invalid_field_map_field_id",
    "find_non_numeric_field_map_field_id",
    "validate_automation_field_map_field_ids",
    "validate_traditional_automation_move_transition",
]
