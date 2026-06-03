from __future__ import annotations


def enrich_pipe_get_pipe_inventory(
    pipe: dict,
    *,
    start_form_phase_row: dict | None = None,
) -> dict:
    """Add ``start_form_phase`` and per-phase ``cards_count`` to a ``get_pipe`` pipe row.

    The start-form phase is removed from ``phases`` when ``startFormPhaseId`` is set so
    agents can iterate workflow phases without duplicating the start form.

    Args:
        pipe: Raw ``pipe`` object from ``GET_PIPE_QUERY``.
        start_form_phase_row: Optional ``phase`` row when the start form is absent from
            ``pipe["phases"]`` (typically from ``GET_PHASE_CARDS_COUNT_QUERY``).

    Returns:
        A shallow copy of ``pipe`` with enriched ``phases`` and optional
        ``start_form_phase``.

    Raises:
        ValueError: A workflow phase or the start form is missing ``cards_count``.
    """
    out = dict(pipe)
    phases_raw = list(out.get("phases") or [])
    start_id = out.get("startFormPhaseId")
    start_id_str = str(start_id) if start_id is not None else None

    start_from_phases: dict | None = None
    workflow_phases: list = []
    for phase in phases_raw:
        if not isinstance(phase, dict):
            workflow_phases.append(phase)
            continue
        phase_id = phase.get("id")
        if (
            start_id_str is not None
            and phase_id is not None
            and str(phase_id) == start_id_str
        ):
            start_from_phases = phase
            continue
        workflow_phases.append(_phase_with_required_cards_count(phase))

    if "phases" in pipe:
        out["phases"] = workflow_phases

    if start_id_str is None:
        return out

    start_source = start_from_phases or start_form_phase_row
    if start_source is None:
        raise ValueError(
            f"start form phase {start_id_str!r} missing from pipe phases and "
            "could not be loaded"
        )
    out["start_form_phase"] = _start_form_phase_summary(start_source)
    return out


def _phase_with_required_cards_count(phase: dict) -> dict:
    phase_out = dict(phase)
    count = phase_out.get("cards_count")
    if count is None:
        raise ValueError(
            f"phase {phase_out.get('id')!r} cards_count missing from response"
        )
    phase_out["cards_count"] = int(count)
    return phase_out


def _start_form_phase_summary(phase: dict) -> dict[str, str | int]:
    phase_id = phase.get("id")
    if phase_id is None:
        raise ValueError("start form phase id missing from response")
    count = phase.get("cards_count")
    if count is None:
        raise ValueError("start form phase cards_count missing from response")
    return {
        "id": str(phase_id),
        "name": str(phase.get("name") or ""),
        "cards_count": int(count),
    }
