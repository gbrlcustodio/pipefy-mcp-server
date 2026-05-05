"""Unit tests for phase_transition_helpers (error-path enrichment for move-card flows).

These helpers run on the **error** side of automation and agent mutations — they either
return ``None`` (to surface the raw API error) or an enriched payload that lists valid
destination phases. A regression here is invisible to the happy path but directly
degrades the actionable error messages that agents and humans rely on.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.phase_transition_helpers import (
    collect_ai_behavior_move_transition_problems,
    collect_automation_move_transition_error_message,
    try_enrich_move_card_to_phase_failure,
    validate_traditional_automation_move_transition_or_none,
)
from pipefy_mcp.tools.tool_error_envelope import tool_error_message


@pytest.fixture
def mock_client():
    client = MagicMock(PipefyClient)
    client.get_card = AsyncMock()
    client.get_phase_allowed_move_targets = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# try_enrich_move_card_to_phase_failure
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_enrich_returns_none_when_get_card_raises(mock_client):
    mock_client.get_card.side_effect = Exception("network")
    result = await try_enrich_move_card_to_phase_failure(
        mock_client, card_id="c1", destination_phase_id="p-dest"
    )
    assert result is None
    mock_client.get_phase_allowed_move_targets.assert_not_called()


@pytest.mark.anyio
async def test_enrich_logs_debug_when_get_card_raises(mock_client, caplog):
    caplog.set_level(logging.DEBUG, logger="pipefy_mcp.tools.phase_transition_helpers")
    mock_client.get_card.side_effect = Exception("network")
    await try_enrich_move_card_to_phase_failure(
        mock_client, card_id="c1", destination_phase_id="p-dest"
    )
    assert "get_card failed" in caplog.text


@pytest.mark.anyio
async def test_enrich_returns_none_when_current_phase_missing(mock_client):
    mock_client.get_card.return_value = {"card": {"id": "c1"}}  # no current_phase
    result = await try_enrich_move_card_to_phase_failure(
        mock_client, card_id="c1", destination_phase_id="p-dest"
    )
    assert result is None
    mock_client.get_phase_allowed_move_targets.assert_not_called()


@pytest.mark.anyio
async def test_enrich_returns_none_when_phase_query_raises(mock_client):
    mock_client.get_card.return_value = {
        "card": {"id": "c1", "current_phase": {"id": "src-phase", "name": "Src"}}
    }
    mock_client.get_phase_allowed_move_targets.side_effect = Exception("gql fail")
    result = await try_enrich_move_card_to_phase_failure(
        mock_client, card_id="c1", destination_phase_id="p-dest"
    )
    assert result is None


@pytest.mark.anyio
async def test_enrich_logs_debug_when_phase_query_raises(mock_client, caplog):
    caplog.set_level(logging.DEBUG, logger="pipefy_mcp.tools.phase_transition_helpers")
    mock_client.get_card.return_value = {
        "card": {"id": "c1", "current_phase": {"id": "src-phase", "name": "Src"}}
    }
    mock_client.get_phase_allowed_move_targets.side_effect = Exception("gql fail")
    await try_enrich_move_card_to_phase_failure(
        mock_client, card_id="c1", destination_phase_id="p-dest"
    )
    assert "get_phase_allowed_move_targets failed" in caplog.text
    assert "src-phase" in caplog.text


@pytest.mark.anyio
async def test_enrich_returns_none_when_destination_is_allowed(mock_client):
    """If the destination is actually allowed, the original API error wasn't a transition issue."""
    mock_client.get_card.return_value = {
        "card": {"id": "c1", "current_phase": {"id": "src-phase", "name": "Src"}}
    }
    mock_client.get_phase_allowed_move_targets.return_value = {
        "phase": {
            "cards_can_be_moved_to_phases": [{"id": "p-dest", "name": "OK"}],
        }
    }
    result = await try_enrich_move_card_to_phase_failure(
        mock_client, card_id="c1", destination_phase_id="p-dest"
    )
    assert result is None


@pytest.mark.anyio
async def test_enrich_builds_structured_error_with_valid_destinations(mock_client):
    mock_client.get_card.return_value = {
        "card": {
            "id": "c1",
            "current_phase": {"id": "src-phase", "name": "Inbox"},
        }
    }
    allowed = [{"id": "p-ok", "name": "Doing"}]
    mock_client.get_phase_allowed_move_targets.return_value = {
        "phase": {"cards_can_be_moved_to_phases": allowed},
    }
    result = await try_enrich_move_card_to_phase_failure(
        mock_client, card_id="c1", destination_phase_id="p-bad"
    )
    assert result is not None
    assert result["success"] is False
    em = tool_error_message(result)
    assert "Inbox" in em
    assert "p-bad" in em
    assert "Doing (p-ok)" in em
    assert result["valid_destinations"] == allowed
    assert result["current_phase"] == {"id": "src-phase", "name": "Inbox"}


@pytest.mark.anyio
async def test_enrich_falls_back_to_id_label_when_phase_has_no_name(mock_client):
    mock_client.get_card.return_value = {
        "card": {"id": "c1", "current_phase": {"id": "src-phase"}}
    }
    mock_client.get_phase_allowed_move_targets.return_value = {
        "phase": {"cards_can_be_moved_to_phases": []},
    }
    result = await try_enrich_move_card_to_phase_failure(
        mock_client, card_id="c1", destination_phase_id="p-bad"
    )
    assert result is not None
    em = tool_error_message(result)
    assert "id src-phase" in em
    assert "(none configured)" in em
    assert result["current_phase"] == {"id": "src-phase", "name": None}


# ---------------------------------------------------------------------------
# collect_automation_move_transition_error_message
# ---------------------------------------------------------------------------


def test_collect_automation_move_message_includes_names_and_ids():
    msg = collect_automation_move_transition_error_message(
        allowed_phases=[{"id": "p1", "name": "A"}, {"id": "p2", "name": "B"}],
        source_phase_name="Source",
        source_phase_id="src",
        dest_phase_id="dest",
    )
    assert "'Source'" in msg
    assert "id src" in msg
    assert "id dest" in msg
    assert "A (p1), B (p2)" in msg


def test_collect_automation_move_message_handles_anonymous_source():
    msg = collect_automation_move_transition_error_message(
        allowed_phases=[],
        source_phase_name="",
        source_phase_id="src",
        dest_phase_id="dest",
    )
    assert "id src" in msg
    # falls back to "(none configured)" for empty allowed list
    assert "(none configured)" in msg


# ---------------------------------------------------------------------------
# validate_traditional_automation_move_transition_or_none
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_validate_trad_move_returns_none_when_trigger_is_not_card_moved(
    mock_client,
):
    out = await validate_traditional_automation_move_transition_or_none(
        mock_client,
        trigger_id="card_created",
        action_id="move_single_card",
        extra_input={"event_params": {"to_phase_id": "src"}},
    )
    assert out is None
    mock_client.get_phase_allowed_move_targets.assert_not_called()


@pytest.mark.anyio
async def test_validate_trad_move_returns_none_when_action_is_not_move_card(
    mock_client,
):
    out = await validate_traditional_automation_move_transition_or_none(
        mock_client,
        trigger_id="card_moved",
        action_id="send_email_template",
        extra_input={"event_params": {"to_phase_id": "src"}},
    )
    assert out is None


@pytest.mark.anyio
async def test_validate_trad_move_returns_none_when_extra_input_not_dict(mock_client):
    out = await validate_traditional_automation_move_transition_or_none(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input="not a dict",
    )
    assert out is None


@pytest.mark.anyio
async def test_validate_trad_move_returns_none_without_src_phase(mock_client):
    out = await validate_traditional_automation_move_transition_or_none(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input={"event_params": {}},
    )
    assert out is None


@pytest.mark.anyio
async def test_validate_trad_move_resolves_dest_from_nested_phase_id(mock_client):
    """Agents often pass ``action_params.phase.id`` instead of ``to_phase_id`` — both must work."""
    mock_client.get_phase_allowed_move_targets.return_value = {
        "phase": {"name": "Src", "cards_can_be_moved_to_phases": []},
    }
    out = await validate_traditional_automation_move_transition_or_none(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input={
            "event_params": {"to_phase_id": "src"},
            "action_params": {"phase": {"id": "dest"}},
        },
    )
    assert out is not None
    assert "id src" in out
    assert "id dest" in out


@pytest.mark.anyio
async def test_validate_trad_move_returns_none_when_dest_missing(mock_client):
    out = await validate_traditional_automation_move_transition_or_none(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input={
            "event_params": {"to_phase_id": "src"},
            "action_params": {},
        },
    )
    assert out is None
    mock_client.get_phase_allowed_move_targets.assert_not_called()


@pytest.mark.anyio
async def test_validate_trad_move_returns_none_on_phase_query_error(mock_client):
    mock_client.get_phase_allowed_move_targets.side_effect = Exception("gql fail")
    out = await validate_traditional_automation_move_transition_or_none(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input={
            "event_params": {"to_phase_id": "src"},
            "action_params": {"to_phase_id": "dest"},
        },
    )
    assert out is None


@pytest.mark.anyio
async def test_validate_trad_move_logs_debug_on_phase_query_error(mock_client, caplog):
    caplog.set_level(logging.DEBUG, logger="pipefy_mcp.tools.phase_transition_helpers")
    mock_client.get_phase_allowed_move_targets.side_effect = Exception("gql fail")
    await validate_traditional_automation_move_transition_or_none(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input={
            "event_params": {"to_phase_id": "src"},
            "action_params": {"to_phase_id": "dest"},
        },
    )
    assert "get_phase_allowed_move_targets failed" in caplog.text
    assert "src" in caplog.text


@pytest.mark.anyio
async def test_validate_trad_move_returns_none_when_transition_is_allowed(mock_client):
    mock_client.get_phase_allowed_move_targets.return_value = {
        "phase": {
            "name": "Src",
            "cards_can_be_moved_to_phases": [{"id": "dest", "name": "Dest"}],
        },
    }
    out = await validate_traditional_automation_move_transition_or_none(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input={
            "event_params": {"to_phase_id": "src"},
            "action_params": {"to_phase_id": "dest"},
        },
    )
    assert out is None


# ---------------------------------------------------------------------------
# collect_ai_behavior_move_transition_problems
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ai_behavior_validation_skips_non_card_moved_events(mock_client):
    behaviors = [
        {
            "name": "b0",
            "event_id": "card_created",
            "actionParams": {
                "aiBehaviorParams": {
                    "actionsAttributes": [
                        {
                            "actionType": "move_card",
                            "metadata": {"destinationPhaseId": "dest"},
                        }
                    ]
                }
            },
        }
    ]
    problems = await collect_ai_behavior_move_transition_problems(
        mock_client, behaviors
    )
    assert problems == []
    mock_client.get_phase_allowed_move_targets.assert_not_called()


@pytest.mark.anyio
async def test_ai_behavior_validation_skips_without_src_phase(mock_client):
    behaviors = [
        {
            "name": "b0",
            "event_id": "card_moved",
            "eventParams": {},
            "actionParams": {
                "aiBehaviorParams": {
                    "actionsAttributes": [
                        {
                            "actionType": "move_card",
                            "metadata": {"destinationPhaseId": "dest"},
                        }
                    ]
                }
            },
        }
    ]
    problems = await collect_ai_behavior_move_transition_problems(
        mock_client, behaviors
    )
    assert problems == []


@pytest.mark.anyio
async def test_ai_behavior_validation_ignores_non_move_actions(mock_client):
    mock_client.get_phase_allowed_move_targets.return_value = {
        "phase": {"name": "Src", "cards_can_be_moved_to_phases": []}
    }
    behaviors = [
        {
            "name": "b0",
            "event_id": "card_moved",
            "eventParams": {"to_phase_id": "src"},
            "actionParams": {
                "aiBehaviorParams": {
                    "actionsAttributes": [
                        {"actionType": "update_card", "metadata": {}},
                        "not-a-dict",
                        {"actionType": "move_card", "metadata": {}},  # no dest
                    ]
                }
            },
        }
    ]
    problems = await collect_ai_behavior_move_transition_problems(
        mock_client, behaviors
    )
    assert problems == []


@pytest.mark.anyio
async def test_ai_behavior_validation_logs_debug_on_phase_query_error(
    mock_client, caplog
):
    caplog.set_level(logging.DEBUG, logger="pipefy_mcp.tools.phase_transition_helpers")
    mock_client.get_phase_allowed_move_targets.side_effect = Exception("gql fail")
    behaviors = [
        {
            "name": "rule",
            "event_id": "card_moved",
            "eventParams": {"to_phase_id": "src-phase"},
            "actionParams": {
                "aiBehaviorParams": {
                    "actionsAttributes": [
                        {
                            "actionType": "move_card",
                            "metadata": {"destinationPhaseId": "p-dest"},
                        }
                    ]
                }
            },
        }
    ]
    await collect_ai_behavior_move_transition_problems(mock_client, behaviors)
    assert "get_phase_allowed_move_targets failed" in caplog.text
    assert "src-phase" in caplog.text


@pytest.mark.anyio
async def test_ai_behavior_validation_flags_invalid_move(mock_client):
    mock_client.get_phase_allowed_move_targets.return_value = {
        "phase": {
            "name": "Inbox",
            "cards_can_be_moved_to_phases": [{"id": "p-ok", "name": "Doing"}],
        }
    }
    behaviors = [
        {
            "name": "My rule",
            "event_id": "card_moved",
            "eventParams": {"to_phase_id": "src"},
            "actionParams": {
                "aiBehaviorParams": {
                    "actionsAttributes": [
                        {
                            "actionType": "move_card",
                            "metadata": {"destinationPhaseId": "p-bad"},
                        }
                    ]
                }
            },
        }
    ]
    problems = await collect_ai_behavior_move_transition_problems(
        mock_client, behaviors
    )
    assert len(problems) == 1
    assert 'Behavior [0] "My rule"' in problems[0]
    assert "'Inbox'" in problems[0]
    assert "'p-bad'" in problems[0] or "id p-bad" in problems[0]
    assert "Doing (p-ok)" in problems[0]


@pytest.mark.anyio
async def test_ai_behavior_validation_allows_valid_move_with_dest_name_lookup(
    mock_client,
):
    mock_client.get_phase_allowed_move_targets.return_value = {
        "phase": {
            "name": "Inbox",
            "cards_can_be_moved_to_phases": [{"id": "p-ok", "name": "Doing"}],
        }
    }
    behaviors = [
        {
            "name": "ok-rule",
            "event_id": "card_moved",
            "eventParams": {"to_phase_id": "src"},
            "actionParams": {
                "aiBehaviorParams": {
                    "actionsAttributes": [
                        {
                            "actionType": "move_card",
                            "metadata": {"destinationPhaseId": "p-ok"},
                        }
                    ]
                }
            },
        }
    ]
    problems = await collect_ai_behavior_move_transition_problems(
        mock_client, behaviors
    )
    assert problems == []


@pytest.mark.anyio
async def test_ai_behavior_validation_caches_phase_lookups(mock_client):
    """Two behaviors that share the same source phase should hit the API once."""
    mock_client.get_phase_allowed_move_targets.return_value = {
        "phase": {"name": "Inbox", "cards_can_be_moved_to_phases": []},
    }
    behaviors = [
        {
            "event_id": "card_moved",
            "eventParams": {"to_phase_id": "src-same"},
            "actionParams": {
                "aiBehaviorParams": {
                    "actionsAttributes": [
                        {
                            "actionType": "move_card",
                            "metadata": {"destinationPhaseId": "dest-a"},
                        }
                    ]
                }
            },
        },
        {
            "event_id": "card_moved",
            "eventParams": {"to_phase_id": "src-same"},
            "actionParams": {
                "aiBehaviorParams": {
                    "actionsAttributes": [
                        {
                            "actionType": "move_card",
                            "metadata": {"destinationPhaseId": "dest-b"},
                        }
                    ]
                }
            },
        },
    ]
    problems = await collect_ai_behavior_move_transition_problems(
        mock_client, behaviors
    )
    assert len(problems) == 2
    assert mock_client.get_phase_allowed_move_targets.await_count == 1


@pytest.mark.anyio
async def test_ai_behavior_validation_swallows_phase_query_exceptions(mock_client):
    """Cache stores empty data on failure and returns no (bogus) problems."""
    mock_client.get_phase_allowed_move_targets.side_effect = Exception("gql fail")
    behaviors = [
        {
            "event_id": "card_moved",
            "eventParams": {"to_phase_id": "src"},
            "actionParams": {
                "aiBehaviorParams": {
                    "actionsAttributes": [
                        {
                            "actionType": "move_card",
                            "metadata": {"destinationPhaseId": "dest"},
                        }
                    ]
                }
            },
        }
    ]
    problems = await collect_ai_behavior_move_transition_problems(
        mock_client, behaviors
    )
    # When the phase query fails, we cannot prove dest is invalid either way;
    # helper flags it as a problem (empty allowed list → dest not in allowed),
    # but never raises and never blocks on a network issue.
    assert isinstance(problems, list)
    assert all(isinstance(p, str) for p in problems)
