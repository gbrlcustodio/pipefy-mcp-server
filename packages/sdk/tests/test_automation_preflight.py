"""Unit tests for traditional automation pre-flight validators."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from pipefy_sdk import PipefyClient
from pipefy_sdk.automation_preflight import (
    AutomationPreflightError,
    collect_automation_move_transition_error_message,
    collect_field_map_field_id_error_message,
    collect_internal_field_ids_from_pipe_info,
    extract_field_map_destination_ids,
    find_invalid_field_map_field_id,
    find_non_numeric_field_map_field_id,
    validate_automation_field_map_field_ids,
    validate_traditional_automation_move_transition,
)


@pytest.fixture
def mock_client():
    client = MagicMock(PipefyClient)
    client.get_phase_allowed_move_targets = AsyncMock()
    client.get_pipe = AsyncMock()
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
async def test_validate_ignores_camel_to_phase_id_in_event_params(mock_client):
    """``toPhaseId`` (camel) is not the declared spelling, so it yields no src phase.

    A valid snake ``action_params.to_phase_id`` dest is present as a control: the
    check is skipped because the *event* src is camel-ignored, not because the dest
    is missing.
    """
    await validate_traditional_automation_move_transition(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input={
            "event_params": {"toPhaseId": "src"},
            "action_params": {"to_phase_id": "dest"},
        },
    )
    mock_client.get_phase_allowed_move_targets.assert_not_called()


@pytest.mark.anyio
async def test_validate_treats_malformed_event_params_as_absent(mock_client):
    """Preflight is advisory: an uncoercible event_params payload is a no-op, never a raise."""
    await validate_traditional_automation_move_transition(
        mock_client,
        trigger_id="card_moved",
        action_id="move_single_card",
        extra_input={"event_params": {"to_phase_id": ["not", "a", "scalar"]}},
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


# ---------------------------------------------------------------------------
# validate_ai_automation_prompt_sdk (overlap input/output field_ids)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_validate_ai_automation_prompt_null_pipe_does_not_raise(mock_client):
    from pipefy_sdk.ai_preflight import validate_ai_automation_prompt_sdk

    mock_client.get_pipe_with_preferences = AsyncMock(return_value={"pipe": None})
    mock_client.get_automation_events = AsyncMock(return_value=[])
    mock_client.get_ai_credit_usage = AsyncMock(
        return_value={"aiCreditUsageStats": {"active": True}}
    )

    out = await validate_ai_automation_prompt_sdk(
        mock_client,
        pipe_id="1",
        prompt="Summarize %{900000101}",
        field_ids=["900000101"],
    )

    assert out["success"] is True
    assert out["valid"] is False
    assert any("does not exist in pipe" in p for p in out["problems"])


@pytest.mark.anyio
async def test_validate_ai_automation_prompt_overlap_prompt_and_output(mock_client):
    from pipefy_sdk.ai_preflight import validate_ai_automation_prompt_sdk

    fid = "429358623"
    mock_client.get_pipe_with_preferences = AsyncMock(
        return_value={
            "pipe": {
                "phases": [
                    {
                        "fields": [
                            {
                                "internal_id": fid,
                                "id": "fslug",
                                "label": "F",
                                "editable": True,
                            },
                        ],
                    },
                ],
                "start_form_fields": [],
                "preferences": {"aiAgentsEnabled": True},
            },
        },
    )
    mock_client.get_automation_events = AsyncMock(return_value=[])
    mock_client.get_ai_credit_usage = AsyncMock(
        return_value={"aiCreditUsageStats": {"active": True}}
    )
    out = await validate_ai_automation_prompt_sdk(
        mock_client,
        pipe_id="1",
        prompt=f"Summarize %{{{fid}}}",
        field_ids=[fid],
    )
    assert out["success"] is True
    assert out["valid"] is False
    assert any("pick a different" in p.lower() for p in out["problems"])


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


# ---------------------------------------------------------------------------
# extract_field_map_destination_ids
# ---------------------------------------------------------------------------


def test_extract_field_map_ids_snake_case():
    ids = extract_field_map_destination_ids(
        {
            "action_params": {
                "field_map": [{"field_id": "429659044", "inputMode": "copy_from"}],
            },
        },
    )
    assert ids == ["429659044"]


def test_extract_field_map_ids_camel_case():
    ids = extract_field_map_destination_ids(
        {
            "actionParams": {
                "fieldMap": [{"fieldId": "111", "value": "x"}],
            },
        },
    )
    assert ids == ["111"]


def test_extract_field_map_ids_empty_when_missing():
    assert extract_field_map_destination_ids(None) == []
    assert extract_field_map_destination_ids({}) == []
    assert extract_field_map_destination_ids({"action_params": {}}) == []


def test_extract_field_map_skips_entries_without_field_id():
    ids = extract_field_map_destination_ids(
        {
            "action_params": {
                "field_map": [
                    {"inputMode": "copy_from", "value": "%{id}"},
                    {"fieldId": "42", "inputMode": "fixed_value", "value": "x"},
                ],
            },
        },
    )
    assert ids == ["42"]


def test_collect_internal_field_ids_from_pipe_info_pure():
    pipe_info = {
        "start_form_fields": [{"internal_id": "100"}],
        "phases": [
            {
                "fields": [{"internal_id": "200"}],
            },
            {
                "id": "phase-empty",
                "fields": [],
            },
        ],
    }
    assert collect_internal_field_ids_from_pipe_info(pipe_info) == {"100", "200"}


def test_find_non_numeric_field_map_field_id_pure():
    assert find_non_numeric_field_map_field_id(["9001", "42"]) is None
    assert find_non_numeric_field_map_field_id(["due_date"]) == "due_date"


def test_find_invalid_field_map_field_id_pure():
    known = {"9001", "42"}
    assert find_invalid_field_map_field_id(["9001"], known) is None
    assert find_invalid_field_map_field_id(["due_date"], known) == ("due_date", True)
    assert find_invalid_field_map_field_id(["999999"], known) == ("999999", False)


# ---------------------------------------------------------------------------
# validate_automation_field_map_field_ids
# ---------------------------------------------------------------------------


def _pipe_with_internal_field(internal_id: str) -> dict:
    return {
        "pipe": {
            "start_form_fields": [
                {"internal_id": internal_id, "id": "slug_field"},
            ],
            "phases": [],
        },
    }


@pytest.mark.anyio
async def test_validate_field_map_skips_without_field_map(mock_client):
    await validate_automation_field_map_field_ids(mock_client, "pipe-1", None)
    mock_client.get_pipe.assert_not_called()


@pytest.mark.anyio
async def test_validate_field_map_passes_for_known_internal_id(mock_client):
    mock_client.get_pipe.return_value = _pipe_with_internal_field("9001")
    await validate_automation_field_map_field_ids(
        mock_client,
        "pipe-1",
        {
            "action_params": {
                "field_map": [{"fieldId": "9001", "inputMode": "copy_from"}],
            },
        },
    )


@pytest.mark.anyio
async def test_validate_field_map_raises_for_unknown_internal_id(mock_client):
    mock_client.get_pipe.return_value = _pipe_with_internal_field("9001")
    with pytest.raises(AutomationPreflightError) as excinfo:
        await validate_automation_field_map_field_ids(
            mock_client,
            "pipe-1",
            {
                "action_params": {
                    "field_map": [{"fieldId": "999999", "inputMode": "copy_from"}],
                },
            },
        )
    msg = str(excinfo.value)
    assert "999999" in msg
    assert "get_start_form_fields" in msg
    assert "get_phase_fields" in msg


@pytest.mark.anyio
async def test_validate_field_map_raises_for_slug_field_id(mock_client):
    with pytest.raises(AutomationPreflightError) as excinfo:
        await validate_automation_field_map_field_ids(
            mock_client,
            "pipe-1",
            {
                "action_params": {
                    "field_map": [{"fieldId": "due_date", "inputMode": "copy_from"}],
                },
            },
        )
    assert "due_date" in str(excinfo.value)
    assert "slug" in str(excinfo.value).lower()
    mock_client.get_pipe.assert_not_called()


@pytest.mark.anyio
async def test_validate_field_map_accepts_camel_case_keys(mock_client):
    mock_client.get_pipe.return_value = _pipe_with_internal_field("42")
    await validate_automation_field_map_field_ids(
        mock_client,
        "pipe-1",
        {
            "actionParams": {
                "fieldMap": [
                    {"fieldId": "42", "inputMode": "fixed_value", "value": "x"}
                ],
            },
        },
    )


@pytest.mark.anyio
async def test_validate_field_map_swallows_get_pipe_error(mock_client):
    mock_client.get_pipe.side_effect = Exception("gql fail")
    await validate_automation_field_map_field_ids(
        mock_client,
        "pipe-1",
        {"action_params": {"field_map": [{"fieldId": "999999"}]}},
    )


def test_collect_field_map_field_id_error_message_includes_discovery():
    msg = collect_field_map_field_id_error_message(
        field_id="123",
        action_pipe_id="pipe-9",
    )
    assert "123" in msg
    assert "pipe-9" in msg
    assert "get_phase_fields" in msg
