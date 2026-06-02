"""Facade-level tests: ``create_automation`` preflight before AutomationService."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pipefy_sdk import PipefyClient
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
