"""Unit tests for AI pipe validation field-id collection."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from _shared.fixture_ids import (
    EXAMPLE_FIELD_INTERNAL_ID,
    EXAMPLE_FIELD_INTERNAL_ID_2,
    EXAMPLE_FIELD_INTERNAL_ID_4,
    EXAMPLE_FIELD_SLUG,
    EXAMPLE_FIELD_SLUG_2,
    EXAMPLE_FIELD_SLUG_3,
    EXAMPLE_PHASE_ID,
    EXAMPLE_PIPE_ID,
)

from pipefy_sdk.ai_pipe_validation import (
    add_field_identifiers,
    collect_field_ids_for_pipe,
    fetch_pipe_validation_context,
    validate_behaviors_against_pipe,
)


@pytest.mark.unit
def test_add_field_identifiers_includes_slug_and_internal_id() -> None:
    field_ids: set[str] = set()
    add_field_identifiers(
        field_ids,
        {"id": EXAMPLE_FIELD_SLUG, "internal_id": EXAMPLE_FIELD_INTERNAL_ID},
    )
    assert field_ids == {EXAMPLE_FIELD_SLUG, EXAMPLE_FIELD_INTERNAL_ID}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_field_ids_for_pipe_fetches_phase_fields() -> None:
    client = AsyncMock()
    client.get_phase_fields = AsyncMock(
        side_effect=[
            {
                "fields": [
                    {
                        "id": EXAMPLE_FIELD_SLUG_3,
                        "internal_id": EXAMPLE_FIELD_INTERNAL_ID_4,
                    }
                ]
            },
            {"fields": []},
        ]
    )
    pipe_info = {
        "start_form_fields": [
            {
                "id": EXAMPLE_FIELD_SLUG_2,
                "internal_id": EXAMPLE_FIELD_INTERNAL_ID_2,
            },
        ],
        "phases": [{"id": "100"}, {"id": "200"}],
    }

    field_ids, failed_phase_ids = await collect_field_ids_for_pipe(
        client, pipe_info, timeout=5
    )

    assert EXAMPLE_FIELD_SLUG_2 in field_ids
    assert EXAMPLE_FIELD_INTERNAL_ID_2 in field_ids
    assert EXAMPLE_FIELD_SLUG_3 in field_ids
    assert EXAMPLE_FIELD_INTERNAL_ID_4 in field_ids
    assert failed_phase_ids == []
    assert client.get_phase_fields.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_field_ids_for_pipe_reports_failed_phases() -> None:
    client = AsyncMock()
    client.get_phase_fields = AsyncMock(side_effect=RuntimeError("upstream"))
    pipe_info = {"start_form_fields": [], "phases": [{"id": "100"}]}

    field_ids, failed_phase_ids = await collect_field_ids_for_pipe(
        client, pipe_info, timeout=5
    )

    assert field_ids == set()
    assert failed_phase_ids == ["100"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_pipe_validation_context_surfaces_phase_fetch_warning() -> None:
    client = AsyncMock()
    client.get_pipe = AsyncMock(
        return_value={"pipe": {"phases": [{"id": "100"}], "start_form_fields": []}}
    )
    client.get_pipe_relations = AsyncMock(return_value={"children": [], "parents": []})
    client.get_phase_fields = AsyncMock(side_effect=RuntimeError("timeout"))

    (
        field_ids,
        phase_ids,
        related_pipe_ids,
        fetch_warnings,
    ) = await fetch_pipe_validation_context(client, EXAMPLE_PIPE_ID, timeout=5)

    assert field_ids == set()
    assert phase_ids == {"100"}
    assert related_pipe_ids == set()
    assert len(fetch_warnings) == 1
    assert "100" in fetch_warnings[0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_pipe_validation_context_excludes_start_form_phase() -> None:
    # get_pipe returns the enriched shape: workflow phases carry cards_count and
    # the start form is a separate ``start_form_phase`` key, never in ``phases``.
    # phase_ids must reflect only workflow phases (the start form is not a valid
    # move target), so a behavior validated here is checked against the same set
    # the public ``phases`` field already exposed before enrichment.
    client = AsyncMock()
    client.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "startFormPhaseId": "100",
                "start_form_phase": {
                    "id": "100",
                    "name": "Start form",
                    "cards_count": 0,
                },
                "phases": [
                    {"id": "200", "name": "Doing", "cards_count": 2},
                    {"id": "300", "name": "Done", "cards_count": 5},
                ],
                "start_form_fields": [],
            }
        }
    )
    client.get_pipe_relations = AsyncMock(return_value={"children": [], "parents": []})
    client.get_phase_fields = AsyncMock(return_value={"fields": []})

    _, phase_ids, _, _ = await fetch_pipe_validation_context(
        client, EXAMPLE_PIPE_ID, timeout=5
    )

    assert phase_ids == {"200", "300"}
    assert "100" not in phase_ids


@pytest.mark.unit
def test_validate_behaviors_accepts_internal_id_when_in_pipe_field_set() -> None:
    behavior = {
        "name": "Update briefing",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "Fill summary",
                "actionsAttributes": [
                    {
                        "name": "act",
                        "actionType": "update_card",
                        "metadata": {
                            "pipeId": EXAMPLE_PIPE_ID,
                            "fieldsAttributes": [
                                {
                                    "fieldId": EXAMPLE_FIELD_INTERNAL_ID,
                                    "inputMode": "fill_with_ai",
                                    "value": "",
                                }
                            ],
                        },
                    }
                ],
            }
        },
    }
    pipe_field_ids = {EXAMPLE_FIELD_SLUG, EXAMPLE_FIELD_INTERNAL_ID}

    problems, warnings = validate_behaviors_against_pipe(
        [behavior],
        pipe_id=EXAMPLE_PIPE_ID,
        pipe_field_ids=pipe_field_ids,
        pipe_phase_ids=set(),
        related_pipe_ids=set(),
    )

    assert problems == []
    assert warnings == []


@pytest.mark.unit
def test_validate_behaviors_rejects_non_member_field_id() -> None:
    behavior = {
        "name": "Update briefing",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "Fill summary",
                "actionsAttributes": [
                    {
                        "name": "act",
                        "actionType": "update_card",
                        "metadata": {
                            "pipeId": EXAMPLE_PIPE_ID,
                            "fieldsAttributes": [
                                {
                                    "fieldId": EXAMPLE_FIELD_INTERNAL_ID,
                                    "inputMode": "fill_with_ai",
                                    "value": "",
                                }
                            ],
                        },
                    }
                ],
            }
        },
    }

    problems, warnings = validate_behaviors_against_pipe(
        [behavior],
        pipe_id=EXAMPLE_PIPE_ID,
        pipe_field_ids={EXAMPLE_FIELD_SLUG},
        pipe_phase_ids=set(),
        related_pipe_ids=set(),
    )

    assert warnings == []
    assert len(problems) == 1
    assert EXAMPLE_FIELD_INTERNAL_ID in problems[0]


@pytest.mark.unit
def test_validate_behaviors_rejects_unknown_move_card_destination_phase() -> None:
    behavior = {
        "name": "Move to review",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "Move",
                "actionsAttributes": [
                    {
                        "name": "move",
                        "actionType": "move_card",
                        "metadata": {"destinationPhaseId": EXAMPLE_PHASE_ID},
                    }
                ],
            }
        },
    }

    problems, warnings = validate_behaviors_against_pipe(
        [behavior],
        pipe_id=EXAMPLE_PIPE_ID,
        pipe_field_ids=set(),
        pipe_phase_ids={"other-phase"},
        related_pipe_ids=set(),
    )

    assert warnings == []
    assert len(problems) == 1
    assert EXAMPLE_PHASE_ID in problems[0]


@pytest.mark.unit
def test_validate_behaviors_flags_unknown_field_id_when_field_set_empty() -> None:
    behavior = {
        "name": "Update briefing",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "Fill summary",
                "actionsAttributes": [
                    {
                        "name": "act",
                        "actionType": "update_card",
                        "metadata": {
                            "pipeId": EXAMPLE_PIPE_ID,
                            "fieldsAttributes": [
                                {
                                    "fieldId": EXAMPLE_FIELD_INTERNAL_ID,
                                    "inputMode": "fill_with_ai",
                                    "value": "",
                                }
                            ],
                        },
                    }
                ],
            }
        },
    }

    problems, _warnings = validate_behaviors_against_pipe(
        [behavior],
        pipe_id=EXAMPLE_PIPE_ID,
        pipe_field_ids=set(),
        pipe_phase_ids=set(),
        related_pipe_ids=set(),
    )

    assert len(problems) == 1
    assert EXAMPLE_FIELD_INTERNAL_ID in problems[0]
