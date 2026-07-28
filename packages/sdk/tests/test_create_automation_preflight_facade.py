"""Facade-level tests: ``create_automation`` preflight before AutomationService."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pipefy_sdk import AutomationConditionInput, PipefyClient
from pipefy_sdk.automation_preflight import AutomationPreflightError


@pytest.fixture
def facade_client() -> PipefyClient:
    client = PipefyClient.__new__(PipefyClient)
    client._automation_service = AsyncMock()
    client._automation_service.create_automation = AsyncMock(
        return_value={"createAutomation": {"automation": {"id": "1"}}}
    )
    client.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "start_form_fields": [{"internal_id": "9001"}],
                "phases": [],
            },
        },
    )
    client.get_phase_fields = AsyncMock(return_value={"fields": []})
    client.get_phase_allowed_move_targets = AsyncMock(
        return_value={"phase": {"cards_can_be_moved_to_phases": []}},
    )
    return client


@pytest.mark.anyio
async def test_create_automation_raises_on_invalid_field_map_before_service(
    facade_client: PipefyClient,
):
    with pytest.raises(AutomationPreflightError) as excinfo:
        await facade_client.create_automation(
            "pipe-1",
            "Rule",
            "card_created",
            "update_card_field",
            extra_input={
                "action_params": {
                    "field_map": [{"fieldId": "999999", "inputMode": "copy_from"}],
                },
            },
        )
    assert "999999" in str(excinfo.value)
    facade_client._automation_service.create_automation.assert_not_called()


@pytest.mark.anyio
async def test_create_automation_field_map_preflight_uses_action_repo_id(
    facade_client: PipefyClient,
):
    facade_client.get_pipe.return_value = {
        "pipe": {
            "start_form_fields": [{"internal_id": "42"}],
            "phases": [],
        },
    }
    await facade_client.create_automation(
        "pipe-1",
        "Rule",
        "card_created",
        "update_card_field",
        action_repo_id="dest-pipe",
        extra_input={
            "action_params": {
                "field_map": [{"fieldId": "42", "inputMode": "copy_from"}],
            },
        },
    )
    facade_client.get_pipe.assert_awaited_once_with("dest-pipe")
    facade_client._automation_service.create_automation.assert_awaited_once()


@pytest.mark.anyio
async def test_create_automation_serializes_typed_condition_to_service(
    facade_client: PipefyClient,
):
    """A typed ``condition`` reaches the service as its serialized wire dict."""
    await facade_client.create_automation(
        "pipe-1",
        "Rule",
        "card_created",
        "send_a_task",
        condition=AutomationConditionInput.model_validate(
            {
                "expressions": [{"field_address": "9001", "operation": "present"}],
                "expressions_structure": [[0]],
            }
        ),
    )
    _, kwargs = facade_client._automation_service.create_automation.call_args
    assert kwargs["condition"] == {
        "expressions": [{"field_address": "9001", "operation": "present"}],
        "expressions_structure": [[0]],
    }


@pytest.mark.anyio
async def test_create_automation_explicit_condition_wins_over_extra_input(
    facade_client: PipefyClient,
):
    """An explicit ``condition`` overrides a ``condition`` nested in ``extra_input``."""
    await facade_client.create_automation(
        "pipe-1",
        "Rule",
        "card_created",
        "send_a_task",
        condition=AutomationConditionInput.model_validate(
            {"expressions": [{"field_address": "9001", "operation": "blank"}]}
        ),
        extra_input={"condition": {"expressions": [{"field_address": "STALE"}]}},
    )
    _, kwargs = facade_client._automation_service.create_automation.call_args
    assert kwargs["condition"] == {
        "expressions": [{"field_address": "9001", "operation": "blank"}]
    }


@pytest.mark.anyio
async def test_update_automation_serializes_typed_condition_to_service(
    facade_client: PipefyClient,
):
    """``update_automation`` serializes a typed ``condition`` for the service."""
    facade_client._automation_service.update_automation = AsyncMock(
        return_value={"updateAutomation": {"automation": {"id": "7"}}}
    )
    await facade_client.update_automation(
        "auto-7",
        condition=AutomationConditionInput.model_validate(
            {
                "expressions": [
                    {"field_address": "9001", "operation": "equals", "value": "x"}
                ]
            }
        ),
    )
    _, kwargs = facade_client._automation_service.update_automation.call_args
    assert kwargs["condition"] == {
        "expressions": [{"field_address": "9001", "operation": "equals", "value": "x"}]
    }
