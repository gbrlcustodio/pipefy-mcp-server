"""Unit tests for traditional automation pre-flight validators."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from pipefy_sdk import PipefyClient
from pipefy_sdk.automation_preflight import (
    AutomationPreflightError,
    collect_automation_move_transition_error_message,
    validate_traditional_automation_move_transition,
)


@pytest.fixture
def mock_client():
    client = MagicMock(PipefyClient)
    client.get_phase_allowed_move_targets = AsyncMock()
    return client


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
    assert "(none configured)" in msg


# ---------------------------------------------------------------------------
# validate_traditional_automation_move_transition (no-op cases)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_validate_skips_non_card_moved_trigger(mock_client):
    await validate_traditional_automation_move_transition(
        mock_client,
        trigger_id="card_created",
        action_id="move_single_card",
        extra_input={"event_params": {"to_phase_id": "src"}},
    )
    mock_client.get_phase_allowed_move_targets.assert_not_called()


@pytest.mark.anyio
async def test_validate_skips_non_move_card_action(mock_client):
    await validate_traditional_automation_move_transition(
        mock_client,
        trigger_id="card_moved",
        action_id="send_email_template",
        extra_input={"event_params": {"to_phase_id": "src"}},
    )
    mock_client.get_phase_allowed_move_targets.assert_not_called()


@pytest.mark.anyio
async def test_validate_skips_non_dict_extra_input(mock_client):
    await validate_traditional_automation_move_transition(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input="not a dict",
    )
    mock_client.get_phase_allowed_move_targets.assert_not_called()


@pytest.mark.anyio
async def test_validate_skips_without_src_phase(mock_client):
    await validate_traditional_automation_move_transition(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input={"event_params": {}},
    )
    mock_client.get_phase_allowed_move_targets.assert_not_called()


@pytest.mark.anyio
async def test_validate_skips_when_dest_missing(mock_client):
    await validate_traditional_automation_move_transition(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input={
            "event_params": {"to_phase_id": "src"},
            "action_params": {},
        },
    )
    mock_client.get_phase_allowed_move_targets.assert_not_called()


@pytest.mark.anyio
async def test_validate_swallows_phase_query_error(mock_client):
    """Upstream flakiness must not block legitimate creates — preflight is best-effort."""
    mock_client.get_phase_allowed_move_targets.side_effect = Exception("gql fail")
    await validate_traditional_automation_move_transition(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input={
            "event_params": {"to_phase_id": "src"},
            "action_params": {"to_phase_id": "dest"},
        },
    )


@pytest.mark.anyio
async def test_validate_logs_debug_on_phase_query_error(mock_client, caplog):
    caplog.set_level(logging.DEBUG, logger="pipefy_sdk.automation_preflight")
    mock_client.get_phase_allowed_move_targets.side_effect = Exception("gql fail")
    await validate_traditional_automation_move_transition(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input={
            "event_params": {"to_phase_id": "src"},
            "action_params": {"to_phase_id": "dest"},
        },
    )
    assert "get_phase_allowed_move_targets failed" in caplog.text


@pytest.mark.anyio
async def test_validate_passes_when_transition_is_allowed(mock_client):
    mock_client.get_phase_allowed_move_targets.return_value = {
        "phase": {
            "name": "Src",
            "cards_can_be_moved_to_phases": [{"id": "dest", "name": "Dest"}],
        },
    }
    await validate_traditional_automation_move_transition(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input={
            "event_params": {"to_phase_id": "src"},
            "action_params": {"to_phase_id": "dest"},
        },
    )


# ---------------------------------------------------------------------------
# validate_traditional_automation_move_transition (raising cases)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_validate_raises_when_transition_not_allowed(mock_client):
    mock_client.get_phase_allowed_move_targets.return_value = {
        "phase": {
            "name": "Src",
            "cards_can_be_moved_to_phases": [{"id": "other", "name": "Other"}],
        },
    }
    with pytest.raises(AutomationPreflightError) as excinfo:
        await validate_traditional_automation_move_transition(
            mock_client,
            trigger_id="card_moved",
            action_id="move_single_card",
            extra_input={
                "event_params": {"to_phase_id": "src"},
                "action_params": {"to_phase_id": "dest"},
            },
        )
    assert "id src" in str(excinfo.value)
    assert "id dest" in str(excinfo.value)
    assert "Other (other)" in str(excinfo.value)


@pytest.mark.anyio
async def test_validate_resolves_dest_from_nested_phase_id(mock_client):
    """Agents often pass ``action_params.phase.id`` instead of ``to_phase_id`` — both must work."""
    mock_client.get_phase_allowed_move_targets.return_value = {
        "phase": {"name": "Src", "cards_can_be_moved_to_phases": []},
    }
    with pytest.raises(AutomationPreflightError) as excinfo:
        await validate_traditional_automation_move_transition(
            mock_client,
            trigger_id="card_moved",
            action_id="move_single_card",
            extra_input={
                "event_params": {"to_phase_id": "src"},
                "action_params": {"phase": {"id": "dest"}},
            },
        )
    assert "id src" in str(excinfo.value)
    assert "id dest" in str(excinfo.value)
