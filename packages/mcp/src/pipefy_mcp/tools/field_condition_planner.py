"""Pure planners for field-condition create/update honesty checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

ConditionPersistenceStatus = Literal["verified", "missing", "wrong_phase"]

_HIDE_ACTION_IDS = frozenset({"hide", "hidden"})

_REQUIRED_FIELD_LABEL_RE = re.compile(r'Field "([^"]+)" is required')

_REQUIRED_HIDDEN_MOVE_HINT = (
    " This field may be hidden by a field condition while still required; "
    "clear required or remove the hide action before moving, or fill the "
    "field if it is visible."
)


@dataclass(frozen=True)
class ConditionPersistenceResult:
    """Verdict from post-create read-back of a field condition."""

    status: ConditionPersistenceStatus
    actual_phase_id: str | None = None


def evaluate_condition_persistence(
    requested_phase_id: str | int,
    condition_id: str | int,
    fetched: dict[str, Any] | None,
    listed_ids: list[str | int] | None,
) -> ConditionPersistenceResult:
    """Decide whether a created condition exists on the requested phase.

    Prefer ``fetched`` (single-condition read with ``phase.id``). When that is
    absent, or when ``fetched`` has no usable ``phase.id`` (null/missing phase),
    fall back to whether ``condition_id`` appears in ``listed_ids`` from the
    phase's condition list. Hard ``wrong_phase`` only when ``phase.id`` is
    present and differs from the requested phase.

    Args:
        requested_phase_id: Phase the caller asked to own the rule.
        condition_id: Id returned by the create mutation.
        fetched: ``fieldCondition`` object from get-by-id, or ``None`` when
            unavailable.
        listed_ids: Condition ids from ``get_field_conditions`` on the requested
            phase, or ``None`` when that list was not obtained.
    """
    requested = str(requested_phase_id)
    cid = str(condition_id)

    if fetched is not None:
        phase = fetched.get("phase")
        actual = None
        if isinstance(phase, dict) and phase.get("id") is not None:
            actual = str(phase["id"])
        if actual is not None:
            if actual == requested:
                return ConditionPersistenceResult(status="verified")
            return ConditionPersistenceResult(
                status="wrong_phase", actual_phase_id=actual
            )
        # Incomplete fetch (phase missing or phase.id null): consult listed_ids.

    listed = {str(item) for item in (listed_ids or [])}
    if cid in listed:
        return ConditionPersistenceResult(status="verified")
    return ConditionPersistenceResult(status="missing")


def phase_fields_from_payload(payload: object) -> list[Any]:
    """Unwrap field defs from ``get_phase_fields`` (``{"fields": [...]}``)."""
    if not isinstance(payload, dict):
        return []
    fields = payload.get("fields")
    return fields if isinstance(fields, list) else []


def find_required_hidden_fields(
    field_definitions: list[Any] | None,
    actions: list[Any] | None,
) -> list[str]:
    """Return field ids that are required and targeted by a hide action.

    Treats ``actionId`` values ``hide`` and legacy ``hidden`` the same (the SDK
    maps ``hidden`` → ``hide`` after this lint runs). Matches each action's
    ``phaseFieldId`` against ``internal_id``, ``id``, and ``uuid`` on field
    definitions (any of those is a valid ``phaseFieldId``). Non-dict entries
    are ignored. Results are deduplicated in first-seen action order.

    The toolkit rejects this combination even when the Pipefy API would accept it.
    """
    required_tokens: set[str] = set()
    for field in field_definitions or []:
        if not isinstance(field, dict):
            continue
        if not field.get("required"):
            continue
        for key in ("internal_id", "id", "uuid"):
            value = field.get(key)
            if value is not None and str(value).strip() != "":
                required_tokens.add(str(value))

    conflicts: list[str] = []
    seen: set[str] = set()
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        if not _action_id_is_hide(action.get("actionId")):
            continue
        phase_field_id = action.get("phaseFieldId")
        if phase_field_id is None:
            continue
        token = str(phase_field_id)
        if token in required_tokens and token not in seen:
            seen.add(token)
            conflicts.append(token)
    return conflicts


def _action_id_is_hide(action_id: object) -> bool:
    """True when ``actionId`` is canonical ``hide`` or the legacy ``hidden`` alias.

    Matches SDK ``normalize_field_condition_actions``: ``strip().lower()`` so
    whitespace/case variants of ``hidden`` are caught before the API call.
    """
    if not isinstance(action_id, str):
        return False
    return action_id.strip().lower() in _HIDE_ACTION_IDS


def extract_required_field_label_from_error(message: str) -> str | None:
    """Return the field label from a Pipefy required-field error, or ``None``.

    Matches ASCII patterns such as ``Field "LABEL" is required`` (label text
    inside the quotes is returned as-is).
    """
    match = _REQUIRED_FIELD_LABEL_RE.search(message)
    if match is None:
        return None
    label = match.group(1)
    return label if label else None


def is_required_hidden_by_label(
    field_definitions: list[Any] | None,
    actions: list[Any] | None,
    label: str,
) -> bool:
    """True when ``label`` names a required field targeted by a ``hide`` action."""
    conflicts = set(find_required_hidden_fields(field_definitions, actions))
    if not conflicts:
        return False
    for field in field_definitions or []:
        if not isinstance(field, dict):
            continue
        if field.get("label") != label:
            continue
        if not field.get("required"):
            continue
        for key in ("internal_id", "id"):
            value = field.get(key)
            if value is not None and str(value) in conflicts:
                return True
    return False


def enrich_required_field_move_message(
    api_message: str,
    *,
    hidden_by_condition: bool,
) -> str:
    """Return ``api_message``, optionally appending a required+hidden move hint."""
    if not hidden_by_condition:
        return api_message
    return f"{api_message.rstrip()}{_REQUIRED_HIDDEN_MOVE_HINT}"
