"""Unit tests for AutomationService AI-automation methods (public ``/graphql`` path).

``generate_with_ai`` create/update go through the same public ``createAutomation``
/ ``updateAutomation`` mutations as traditional rules, with no internal API or
service-account credentials. These tests assert the ``aiParams`` envelope and the
``AutomationServiceResult`` return shape.
"""

from unittest.mock import AsyncMock

import pytest
from pipefy_auth import StaticBearerAuth

from pipefy_sdk.models.ai_automation import (
    DEFAULT_CONDITION,
    CreateAiAutomationInput,
    UpdateAiAutomationInput,
)
from pipefy_sdk.services.automation_service import AutomationService
from pipefy_sdk.settings import PipefySettings

_TEST_AUTH = StaticBearerAuth("test-bearer-token")


@pytest.fixture
def mock_settings():
    return PipefySettings(base_url="https://api.pipefy.com")


def _make_service(mock_settings, return_value: dict) -> AutomationService:
    service = AutomationService(settings=mock_settings, auth=_TEST_AUTH)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


def _create_input(**overrides) -> CreateAiAutomationInput:
    defaults = {
        "name": "My Automation",
        "event_id": "card_created",
        "pipe_id": "303",
        "prompt": "Summarize the card %{133}",
        "field_ids": ["133", "789"],
    }
    defaults.update(overrides)
    return CreateAiAutomationInput(**defaults)


# ---------------------------------------------------------------------------
# create_ai_automation
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_sends_public_create_automation_with_ai_params(mock_settings):
    service = _make_service(
        mock_settings, {"createAutomation": {"automation": {"id": "456"}}}
    )

    result = await service.create_ai_automation(_create_input())

    service.execute_query.assert_awaited_once()
    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["action_id"] == "generate_with_ai"
    assert inp["event_id"] == "card_created"
    assert inp["event_repo_id"] == "303"
    assert inp["action_repo_id"] == "303"
    assert inp["action_params"]["aiParams"]["value"] == "Summarize the card %{133}"
    assert inp["action_params"]["aiParams"]["fieldIds"] == ["133", "789"]
    assert inp["action_params"]["aiParams"]["skillsIds"] == []
    assert result == {
        "automation_id": "456",
        "message": "AI Automation created successfully. ID: 456",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_uses_explicit_action_repo_when_set(mock_settings):
    service = _make_service(
        mock_settings, {"createAutomation": {"automation": {"id": "456"}}}
    )

    await service.create_ai_automation(_create_input(action_repo_id="999"))

    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["event_repo_id"] == "303"
    assert inp["action_repo_id"] == "999"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_forwards_custom_skills_ids(mock_settings):
    service = _make_service(
        mock_settings, {"createAutomation": {"automation": {"id": "456"}}}
    )

    await service.create_ai_automation(_create_input(skills_ids=["skill_a", "skill_b"]))

    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["action_params"]["aiParams"]["skillsIds"] == ["skill_a", "skill_b"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_includes_default_condition_when_omitted(mock_settings):
    service = _make_service(
        mock_settings, {"createAutomation": {"automation": {"id": "456"}}}
    )

    await service.create_ai_automation(_create_input())

    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["condition"] == DEFAULT_CONDITION


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_forwards_custom_condition(mock_settings):
    service = _make_service(
        mock_settings, {"createAutomation": {"automation": {"id": "456"}}}
    )
    custom = {
        "expressions": [
            {"structure_id": 1, "field_address": "f", "operation": "eq", "value": "v"}
        ],
        "expressions_structure": [[1]],
    }

    await service.create_ai_automation(_create_input(condition=custom))

    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["condition"] == custom


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_partial_condition_omits_unset_fields(mock_settings):
    service = _make_service(
        mock_settings, {"createAutomation": {"automation": {"id": "456"}}}
    )

    await service.create_ai_automation(_create_input(condition={"foo": "bar"}))

    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["condition"] == {"foo": "bar"}
    assert "expressions" not in inp["condition"]
    assert "expressions_structure" not in inp["condition"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_passes_event_params_when_provided(mock_settings):
    service = _make_service(
        mock_settings, {"createAutomation": {"automation": {"id": "456"}}}
    )

    await service.create_ai_automation(
        _create_input(event_id="card_moved", event_params={"to_phase_id": "phase-42"})
    )

    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["event_params"] == {"to_phase_id": "phase-42"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_omits_event_params_when_none(mock_settings):
    service = _make_service(
        mock_settings, {"createAutomation": {"automation": {"id": "456"}}}
    )

    await service.create_ai_automation(_create_input())

    inp = service.execute_query.call_args[0][1]["input"]
    assert "event_params" not in inp


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_missing_automation_id_raises(mock_settings):
    service = _make_service(mock_settings, {"createAutomation": {}})

    with pytest.raises(ValueError, match="automation.*id|Unexpected.*payload"):
        await service.create_ai_automation(_create_input())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_raises_on_error_details(mock_settings):
    service = _make_service(
        mock_settings,
        {
            "createAutomation": {
                "automation": None,
                "error_details": [
                    {
                        "object_name": "Automation",
                        "object_key": "base",
                        "messages": ["Pipe not found", "AI not enabled"],
                    }
                ],
            }
        },
    )

    with pytest.raises(ValueError, match="Pipe not found.*AI not enabled"):
        await service.create_ai_automation(_create_input())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_propagates_execute_query_error(mock_settings):
    service = _make_service(mock_settings, {})
    service.execute_query = AsyncMock(side_effect=ValueError("GraphQL error"))

    with pytest.raises(ValueError, match="GraphQL error"):
        await service.create_ai_automation(_create_input())


# ---------------------------------------------------------------------------
# update_ai_automation
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_sends_public_update_automation_with_ai_params(mock_settings):
    service = _make_service(
        mock_settings, {"updateAutomation": {"automation": {"id": "789"}}}
    )

    result = await service.update_ai_automation(
        UpdateAiAutomationInput(
            automation_id="789",
            name="Updated Name",
            active=False,
            prompt="New prompt %{133}",
            field_ids=["133"],
        )
    )

    service.execute_query.assert_awaited_once()
    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["id"] == "789"
    assert inp["name"] == "Updated Name"
    assert inp["active"] is False
    assert inp["action_params"]["aiParams"]["value"] == "New prompt %{133}"
    assert inp["action_params"]["aiParams"]["fieldIds"] == ["133"]
    assert result == {
        "automation_id": "789",
        "message": "AI Automation updated successfully. ID: 789",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_omits_condition_when_not_provided(mock_settings):
    service = _make_service(
        mock_settings, {"updateAutomation": {"automation": {"id": "789"}}}
    )

    await service.update_ai_automation(
        UpdateAiAutomationInput(automation_id="789", name="Only name")
    )

    inp = service.execute_query.call_args[0][1]["input"]
    assert "condition" not in inp
    assert "action_params" not in inp


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_passes_condition_when_provided(mock_settings):
    service = _make_service(
        mock_settings, {"updateAutomation": {"automation": {"id": "789"}}}
    )
    cond = {
        "expressions": [
            {"structure_id": 0, "field_address": "", "operation": "", "value": ""}
        ],
        "expressions_structure": [[0]],
    }

    await service.update_ai_automation(
        UpdateAiAutomationInput(automation_id="789", condition=cond)
    )

    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["condition"] == cond


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_sends_skills_ids_when_provided(mock_settings):
    service = _make_service(
        mock_settings, {"updateAutomation": {"automation": {"id": "789"}}}
    )

    await service.update_ai_automation(
        UpdateAiAutomationInput(automation_id="789", skills_ids=["skill_x"])
    )

    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["action_params"]["aiParams"]["skillsIds"] == ["skill_x"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_passes_event_params_when_provided(mock_settings):
    service = _make_service(
        mock_settings, {"updateAutomation": {"automation": {"id": "789"}}}
    )

    await service.update_ai_automation(
        UpdateAiAutomationInput(
            automation_id="789", event_params={"triggerFieldIds": ["field_1"]}
        )
    )

    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["event_params"] == {"triggerFieldIds": ["field_1"]}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_missing_automation_id_raises(mock_settings):
    service = _make_service(mock_settings, {"updateAutomation": {"automation": {}}})

    with pytest.raises(ValueError, match="automation.*id|Unexpected.*payload"):
        await service.update_ai_automation(UpdateAiAutomationInput(automation_id="123"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_raises_on_error_details(mock_settings):
    service = _make_service(
        mock_settings,
        {
            "updateAutomation": {
                "automation": None,
                "error_details": [
                    {
                        "object_name": "Automation",
                        "object_key": "base",
                        "messages": ["Invalid field"],
                    }
                ],
            }
        },
    )

    with pytest.raises(ValueError, match="Invalid field"):
        await service.update_ai_automation(UpdateAiAutomationInput(automation_id="123"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_propagates_execute_query_error(mock_settings):
    service = _make_service(mock_settings, {})
    service.execute_query = AsyncMock(side_effect=RuntimeError("Network error"))

    with pytest.raises(RuntimeError, match="Network error"):
        await service.update_ai_automation(UpdateAiAutomationInput(automation_id="123"))
