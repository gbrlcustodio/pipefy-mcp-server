"""Tests for resolve_field_slugs_to_numeric (slug → numeric fieldId resolution)."""

import copy
from unittest.mock import AsyncMock

import pytest

from pipefy_mcp.tools.ai_tool_helpers import (
    build_field_slug_map,
    resolve_field_slugs_to_numeric,
)


def _behavior_with_fields(pipe_id, field_ids, action_type="update_card"):
    """Build a minimal behavior dict with fieldsAttributes targeting pipe_id."""
    return {
        "name": "Test behavior",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "test",
                "actionsAttributes": [
                    {
                        "name": "action",
                        "actionType": action_type,
                        "metadata": {
                            "pipeId": pipe_id,
                            "fieldsAttributes": [
                                {
                                    "fieldId": fid,
                                    "inputMode": "fill_with_ai",
                                    "value": "",
                                }
                                for fid in field_ids
                            ],
                        },
                    },
                ],
            }
        },
    }


# --- build_field_slug_map tests ---


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_field_slug_map_from_start_form_and_phases():
    client = AsyncMock()
    client.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "phases": [{"id": "100"}, {"id": "200"}],
                "start_form_fields": [
                    {"id": "company_name", "internal_id": "427911700"},
                    {"id": "email", "internal_id": "427911701"},
                ],
            }
        }
    )
    client.get_phase_fields = AsyncMock(
        side_effect=[
            {
                "phase_id": "100",
                "fields": [
                    {"id": "summary_field", "internal_id": "427911728"},
                    {"id": "427911729", "internal_id": "427911729"},
                ],
            },
            {
                "phase_id": "200",
                "fields": [
                    {"id": "approval_status", "internal_id": "427911750"},
                ],
            },
        ]
    )

    slug_map = await build_field_slug_map(client, 306996636)

    assert slug_map == {
        "company_name": "427911700",
        "email": "427911701",
        "summary_field": "427911728",
        "approval_status": "427911750",
    }
    # numeric-id field "427911729" is NOT in the map (already numeric)
    assert "427911729" not in slug_map


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_field_slug_map_skips_failed_phase():
    client = AsyncMock()
    client.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "phases": [{"id": "100"}, {"id": "200"}],
                "start_form_fields": [],
            }
        }
    )
    client.get_phase_fields = AsyncMock(
        side_effect=[
            Exception("timeout"),
            {"phase_id": "200", "fields": [{"id": "slug_a", "internal_id": "999"}]},
        ]
    )

    slug_map = await build_field_slug_map(client, 1)

    assert slug_map == {"slug_a": "999"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_field_slug_map_empty_pipe():
    client = AsyncMock()
    client.get_pipe = AsyncMock(
        return_value={"pipe": {"phases": [], "start_form_fields": []}}
    )

    slug_map = await build_field_slug_map(client, 1)

    assert slug_map == {}


# --- resolve_field_slugs_to_numeric tests ---


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_replaces_slug_with_numeric_id():
    client = AsyncMock()
    client.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "phases": [{"id": "100"}],
                "start_form_fields": [
                    {"id": "resumo_de_briefing_ia", "internal_id": "427911728"},
                ],
            }
        }
    )
    client.get_phase_fields = AsyncMock(return_value={"phase_id": "100", "fields": []})

    behaviors = [_behavior_with_fields("306996636", ["resumo_de_briefing_ia"])]
    resolved = await resolve_field_slugs_to_numeric(client, behaviors)

    fa = resolved[0]["actionParams"]["aiBehaviorParams"]["actionsAttributes"][0][
        "metadata"
    ]["fieldsAttributes"]
    assert fa[0]["fieldId"] == "427911728"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_leaves_numeric_ids_untouched():
    client = AsyncMock()

    behaviors = [_behavior_with_fields("100", ["427911728", "427911729"])]
    resolved = await resolve_field_slugs_to_numeric(client, behaviors)

    # No API calls because all fieldIds are already numeric
    client.get_pipe.assert_not_called()
    fa = resolved[0]["actionParams"]["aiBehaviorParams"]["actionsAttributes"][0][
        "metadata"
    ]["fieldsAttributes"]
    assert fa[0]["fieldId"] == "427911728"
    assert fa[1]["fieldId"] == "427911729"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_does_not_mutate_original():
    client = AsyncMock()
    client.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "phases": [],
                "start_form_fields": [
                    {"id": "slug_x", "internal_id": "999"},
                ],
            }
        }
    )

    behaviors = [_behavior_with_fields("1", ["slug_x"])]
    original = copy.deepcopy(behaviors)
    resolved = await resolve_field_slugs_to_numeric(client, behaviors)

    assert behaviors == original
    assert (
        resolved[0]["actionParams"]["aiBehaviorParams"]["actionsAttributes"][0][
            "metadata"
        ]["fieldsAttributes"][0]["fieldId"]
        == "999"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_leaves_unresolvable_slugs_as_is():
    client = AsyncMock()
    client.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "phases": [],
                "start_form_fields": [
                    {"id": "known_slug", "internal_id": "111"},
                ],
            }
        }
    )

    behaviors = [_behavior_with_fields("1", ["known_slug", "unknown_slug"])]
    resolved = await resolve_field_slugs_to_numeric(client, behaviors)

    fa = resolved[0]["actionParams"]["aiBehaviorParams"]["actionsAttributes"][0][
        "metadata"
    ]["fieldsAttributes"]
    assert fa[0]["fieldId"] == "111"
    assert fa[1]["fieldId"] == "unknown_slug"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_handles_multiple_pipes():
    client = AsyncMock()

    async def mock_get_pipe(pipe_id):
        if pipe_id == 100:
            return {
                "pipe": {
                    "phases": [],
                    "start_form_fields": [
                        {"id": "field_a", "internal_id": "1001"},
                    ],
                }
            }
        return {
            "pipe": {
                "phases": [],
                "start_form_fields": [
                    {"id": "field_b", "internal_id": "2001"},
                ],
            }
        }

    client.get_pipe = AsyncMock(side_effect=mock_get_pipe)

    behaviors = [
        _behavior_with_fields("100", ["field_a"]),
        _behavior_with_fields("200", ["field_b"]),
    ]
    resolved = await resolve_field_slugs_to_numeric(client, behaviors)

    fa0 = resolved[0]["actionParams"]["aiBehaviorParams"]["actionsAttributes"][0][
        "metadata"
    ]["fieldsAttributes"]
    fa1 = resolved[1]["actionParams"]["aiBehaviorParams"]["actionsAttributes"][0][
        "metadata"
    ]["fieldsAttributes"]
    assert fa0[0]["fieldId"] == "1001"
    assert fa1[0]["fieldId"] == "2001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_survives_api_failure():
    client = AsyncMock()
    client.get_pipe = AsyncMock(side_effect=Exception("API down"))

    behaviors = [_behavior_with_fields("1", ["some_slug"])]
    resolved = await resolve_field_slugs_to_numeric(client, behaviors)

    # Falls back gracefully — slug left as-is
    fa = resolved[0]["actionParams"]["aiBehaviorParams"]["actionsAttributes"][0][
        "metadata"
    ]["fieldsAttributes"]
    assert fa[0]["fieldId"] == "some_slug"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_handles_snake_case_keys():
    client = AsyncMock()
    client.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "phases": [],
                "start_form_fields": [
                    {"id": "my_slug", "internal_id": "555"},
                ],
            }
        }
    )

    behaviors = [
        {
            "name": "test",
            "event_id": "card_created",
            "action_params": {
                "ai_behavior_params": {
                    "instruction": "test",
                    "actions_attributes": [
                        {
                            "name": "act",
                            "actionType": "update_card",
                            "metadata": {
                                "pipeId": "1",
                                "fieldsAttributes": [
                                    {
                                        "fieldId": "my_slug",
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
    ]
    resolved = await resolve_field_slugs_to_numeric(client, behaviors)

    fa = resolved[0]["action_params"]["ai_behavior_params"]["actions_attributes"][0][
        "metadata"
    ]["fieldsAttributes"]
    assert fa[0]["fieldId"] == "555"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_skips_behaviors_without_pipe_id():
    client = AsyncMock()

    behaviors = [
        {
            "name": "move only",
            "event_id": "card_created",
            "actionParams": {
                "aiBehaviorParams": {
                    "instruction": "test",
                    "actionsAttributes": [
                        {
                            "name": "move",
                            "actionType": "move_card",
                            "metadata": {"destinationPhaseId": "100"},
                        }
                    ],
                }
            },
        }
    ]
    resolved = await resolve_field_slugs_to_numeric(client, behaviors)

    # No API calls, behaviors returned as-is
    client.get_pipe.assert_not_called()
    assert resolved == behaviors
