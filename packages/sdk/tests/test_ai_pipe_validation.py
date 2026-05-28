"""Unit tests for AI pipe validation field-id collection."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from _shared.fixture_ids import (
    EXAMPLE_DESTINATION_PHASE_ID,
    EXAMPLE_FIELD_INTERNAL_ID,
    EXAMPLE_FIELD_INTERNAL_ID_ALT,
    EXAMPLE_FIELD_SLUG_BRIEFING,
    EXAMPLE_FIELD_SLUG_DEMAND,
    EXAMPLE_FIELD_SLUG_PHASE,
    EXAMPLE_PIPE_REPO_ID,
)

from pipefy_sdk.ai_pipe_validation import (
    add_field_identifiers,
    collect_field_ids_for_pipe,
    validate_behaviors_against_pipe,
)


@pytest.mark.unit
def test_add_field_identifiers_includes_slug_and_internal_id() -> None:
    field_ids: set[str] = set()
    add_field_identifiers(
        field_ids,
        {"id": EXAMPLE_FIELD_SLUG_BRIEFING, "internal_id": EXAMPLE_FIELD_INTERNAL_ID},
    )
    assert field_ids == {EXAMPLE_FIELD_SLUG_BRIEFING, EXAMPLE_FIELD_INTERNAL_ID}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_field_ids_for_pipe_fetches_phase_fields() -> None:
    client = AsyncMock()
    client.get_phase_fields = AsyncMock(
        side_effect=[
            {
                "fields": [
                    {
                        "id": EXAMPLE_FIELD_SLUG_PHASE,
                        "internal_id": EXAMPLE_DESTINATION_PHASE_ID,
                    }
                ]
            },
            {"fields": []},
        ]
    )
    pipe_info = {
        "start_form_fields": [
            {
                "id": EXAMPLE_FIELD_SLUG_DEMAND,
                "internal_id": EXAMPLE_FIELD_INTERNAL_ID_ALT,
            },
        ],
        "phases": [{"id": "100"}, {"id": "200"}],
    }

    field_ids = await collect_field_ids_for_pipe(client, pipe_info, timeout=5)

    assert EXAMPLE_FIELD_SLUG_DEMAND in field_ids
    assert EXAMPLE_FIELD_INTERNAL_ID_ALT in field_ids
    assert EXAMPLE_FIELD_SLUG_PHASE in field_ids
    assert EXAMPLE_DESTINATION_PHASE_ID in field_ids
    assert client.get_phase_fields.await_count == 2


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
                            "pipeId": EXAMPLE_PIPE_REPO_ID,
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
    pipe_field_ids = {EXAMPLE_FIELD_SLUG_BRIEFING, EXAMPLE_FIELD_INTERNAL_ID}

    problems, warnings = validate_behaviors_against_pipe(
        [behavior],
        pipe_id=EXAMPLE_PIPE_REPO_ID,
        pipe_field_ids=pipe_field_ids,
        pipe_phase_ids=set(),
        related_pipe_ids=set(),
    )

    assert problems == []
    assert warnings == []


@pytest.mark.unit
def test_validate_behaviors_rejects_numeric_field_id_when_set_has_slug_only() -> None:
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
                            "pipeId": EXAMPLE_PIPE_REPO_ID,
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
        pipe_id=EXAMPLE_PIPE_REPO_ID,
        pipe_field_ids={EXAMPLE_FIELD_SLUG_BRIEFING},
        pipe_phase_ids=set(),
        related_pipe_ids=set(),
    )

    assert warnings == []
    assert len(problems) == 1
    assert EXAMPLE_FIELD_INTERNAL_ID in problems[0]
