"""Unit tests for AiAutomationService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pipefy_mcp.models.ai_automation import (
    DEFAULT_CONDITION,
    CreateAiAutomationInput,
    UpdateAiAutomationInput,
)
from pipefy_mcp.services.pipefy.ai_automation_service import AiAutomationService
from pipefy_mcp.services.pipefy.internal_api_client import InternalApiClient


def _create_mock_internal_api_client(execute_return: dict | None = None) -> MagicMock:
    """Create a mock InternalApiClient with async execute_query."""
    mock = MagicMock(spec=InternalApiClient)
    mock.execute_query = AsyncMock(
        return_value=execute_return
        or {"createAutomation": {"automation": {"id": "123"}}}
    )
    return mock


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_calls_execute_query_with_correct_variables():
    """create_automation calls execute_query with createAutomation mutation and correct variables."""
    mock_client = _create_mock_internal_api_client(
        {"createAutomation": {"automation": {"id": "456"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="303",
        prompt="Summarize the card %{133}",
        field_ids=["133", "789"],
    )
    result = await service.create_automation(inp)

    mock_client.execute_query.assert_called_once()
    call_args = mock_client.execute_query.call_args
    query_str = call_args[0][0]
    variables = call_args[0][1]

    assert "createAutomation" in query_str or "create_automation" in query_str
    assert variables["action_id"] == "generate_with_ai"
    assert variables["event_id"] == "card_created"
    assert variables["event_repo_id"] == "303"
    assert variables["action_repo_id"] == "303"
    assert (
        variables["action_params"]["aiParams"]["value"] == "Summarize the card %{133}"
    )
    assert variables["action_params"]["aiParams"]["fieldIds"] == ["133", "789"]
    assert variables["action_params"]["aiParams"]["skillsIds"] == []
    assert result["automation_id"] == "456"
    assert "AI Automation created successfully" in result["message"]
    assert "456" in result["message"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_sends_custom_skills_ids():
    """create_automation forwards custom skills_ids in aiParams.skillsIds."""
    mock_client = _create_mock_internal_api_client(
        {"createAutomation": {"automation": {"id": "456"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = CreateAiAutomationInput(
        name="With Skills",
        event_id="card_created",
        pipe_id="303",
        prompt="Summarize %{1}",
        field_ids=["1"],
        skills_ids=["skill_a", "skill_b"],
    )
    await service.create_automation(inp)

    variables = mock_client.execute_query.call_args[0][1]
    assert variables["action_params"]["aiParams"]["skillsIds"] == [
        "skill_a",
        "skill_b",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_passes_event_params_when_provided():
    """create_automation includes event_params in variables when set."""
    mock_client = _create_mock_internal_api_client(
        {"createAutomation": {"automation": {"id": "456"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = CreateAiAutomationInput(
        name="Phase filter",
        event_id="card_moved",
        pipe_id="303",
        prompt="Summarize %{1}",
        field_ids=["1"],
        event_params={"to_phase_id": "phase-42"},
    )
    await service.create_automation(inp)

    variables = mock_client.execute_query.call_args[0][1]
    assert variables["event_params"] == {"to_phase_id": "phase-42"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_includes_default_condition_placeholder():
    """create_automation always sends condition (model default when caller omits it)."""
    mock_client = _create_mock_internal_api_client(
        {"createAutomation": {"automation": {"id": "456"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = CreateAiAutomationInput(
        name="No explicit condition",
        event_id="card_created",
        pipe_id="303",
        prompt="Summarize %{1}",
        field_ids=["1"],
    )
    await service.create_automation(inp)

    variables = mock_client.execute_query.call_args[0][1]
    assert "condition" in variables
    assert variables["condition"] == DEFAULT_CONDITION


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_forwards_custom_condition():
    """create_automation sends caller-provided condition in variables."""
    mock_client = _create_mock_internal_api_client(
        {"createAutomation": {"automation": {"id": "456"}}}
    )
    service = AiAutomationService(client=mock_client)

    custom = {
        "expressions": [
            {"structure_id": 1, "field_address": "f", "operation": "eq", "value": "v"}
        ],
        "expressions_structure": [[1]],
    }
    inp = CreateAiAutomationInput(
        name="Custom condition",
        event_id="card_created",
        pipe_id="303",
        prompt="Summarize %{1}",
        field_ids=["1"],
        condition=custom,
    )
    await service.create_automation(inp)

    variables = mock_client.execute_query.call_args[0][1]
    assert variables["condition"] == custom


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_sends_partial_condition_without_injected_defaults():
    """Partial ``condition`` omits unset keys (no ``expressions``, no ``expressions_structure``)."""
    mock_client = _create_mock_internal_api_client(
        {"createAutomation": {"automation": {"id": "456"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = CreateAiAutomationInput(
        name="Partial cond",
        event_id="card_created",
        pipe_id="303",
        prompt="Summarize %{1}",
        field_ids=["1"],
        condition={"foo": "bar"},
    )
    await service.create_automation(inp)

    variables = mock_client.execute_query.call_args[0][1]
    assert variables["condition"] == {"foo": "bar"}
    assert "expressions" not in variables["condition"]
    assert "expressions_structure" not in variables["condition"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_sends_partial_condition_expressions_structure_only():
    """Only user-provided condition keys appear in mutation variables."""
    mock_client = _create_mock_internal_api_client(
        {"createAutomation": {"automation": {"id": "456"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = CreateAiAutomationInput(
        name="Partial structure",
        event_id="card_created",
        pipe_id="303",
        prompt="Summarize %{1}",
        field_ids=["1"],
        condition={"expressions_structure": [[1]]},
    )
    await service.create_automation(inp)

    variables = mock_client.execute_query.call_args[0][1]
    assert variables["condition"] == {"expressions_structure": [[1]]}
    assert "expressions" not in variables["condition"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_omits_event_params_when_none():
    """create_automation does not include event_params key when None."""
    mock_client = _create_mock_internal_api_client(
        {"createAutomation": {"automation": {"id": "456"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = CreateAiAutomationInput(
        name="No params",
        event_id="card_created",
        pipe_id="303",
        prompt="Summarize %{1}",
        field_ids=["1"],
    )
    await service.create_automation(inp)

    variables = mock_client.execute_query.call_args[0][1]
    assert "event_params" not in variables


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_omits_condition_when_not_provided():
    """update_automation does not include condition in input when omitted."""
    mock_client = _create_mock_internal_api_client(
        {"updateAutomation": {"automation": {"id": "789"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = UpdateAiAutomationInput(automation_id="789", name="Only name")
    await service.update_automation(inp)

    variables = mock_client.execute_query.call_args[0][1]
    assert "condition" not in variables["input"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_passes_condition_when_provided():
    """update_automation includes condition in input dict when set."""
    mock_client = _create_mock_internal_api_client(
        {"updateAutomation": {"automation": {"id": "789"}}}
    )
    service = AiAutomationService(client=mock_client)

    cond = {
        "expressions": [
            {"structure_id": 0, "field_address": "", "operation": "", "value": ""}
        ],
        "expressions_structure": [[0]],
    }
    inp = UpdateAiAutomationInput(automation_id="789", condition=cond)
    await service.update_automation(inp)

    variables = mock_client.execute_query.call_args[0][1]
    assert variables["input"]["condition"] == cond


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_partial_condition_omits_unset_fields():
    """Update sends only keys the caller set on ``condition``."""
    mock_client = _create_mock_internal_api_client(
        {"updateAutomation": {"automation": {"id": "789"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = UpdateAiAutomationInput(
        automation_id="789",
        condition={"custom_key": "only_this"},
    )
    await service.update_automation(inp)

    variables = mock_client.execute_query.call_args[0][1]
    assert variables["input"]["condition"] == {"custom_key": "only_this"}
    assert "expressions" not in variables["input"]["condition"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_passes_event_params_when_provided():
    """update_automation includes event_params in input dict when set."""
    mock_client = _create_mock_internal_api_client(
        {"updateAutomation": {"automation": {"id": "789"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = UpdateAiAutomationInput(
        automation_id="789",
        event_params={"triggerFieldIds": ["field_1"]},
    )
    await service.update_automation(inp)

    variables = mock_client.execute_query.call_args[0][1]
    assert variables["input"]["event_params"] == {"triggerFieldIds": ["field_1"]}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_returns_success_format():
    """create_automation returns automation_id and message in success format."""
    mock_client = _create_mock_internal_api_client(
        {"createAutomation": {"automation": {"id": "999"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = CreateAiAutomationInput(
        name="Test",
        event_id="card_created",
        pipe_id="1",
        prompt="Do something with %{1}",
        field_ids=["1"],
    )
    result = await service.create_automation(inp)

    assert result == {
        "automation_id": "999",
        "message": "AI Automation created successfully. ID: 999",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_calls_execute_query_with_correct_variables():
    """update_automation calls execute_query with updateAutomation mutation and correct variables."""
    mock_client = _create_mock_internal_api_client(
        {"updateAutomation": {"automation": {"id": "789"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = UpdateAiAutomationInput(
        automation_id="789",
        name="Updated Name",
        active=False,
        prompt="New prompt %{133}",
        field_ids=["133"],
    )
    result = await service.update_automation(inp)

    mock_client.execute_query.assert_called_once()
    call_args = mock_client.execute_query.call_args
    query_str = call_args[0][0]
    variables = call_args[0][1]

    assert "updateAutomation" in query_str or "update_automation" in query_str
    assert variables["input"]["id"] == "789"
    assert variables["input"]["name"] == "Updated Name"
    assert variables["input"]["active"] is False
    assert (
        variables["input"]["action_params"]["aiParams"]["value"] == "New prompt %{133}"
    )
    assert variables["input"]["action_params"]["aiParams"]["fieldIds"] == ["133"]
    assert result["automation_id"] == "789"
    assert "AI Automation updated successfully" in result["message"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_sends_skills_ids_when_provided():
    """update_automation includes skillsIds in aiParams when skills_ids is set."""
    mock_client = _create_mock_internal_api_client(
        {"updateAutomation": {"automation": {"id": "789"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = UpdateAiAutomationInput(
        automation_id="789",
        skills_ids=["skill_x"],
    )
    await service.update_automation(inp)

    variables = mock_client.execute_query.call_args[0][1]
    assert variables["input"]["action_params"]["aiParams"]["skillsIds"] == ["skill_x"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_returns_success_format():
    """update_automation returns automation_id and message in success format."""
    mock_client = _create_mock_internal_api_client(
        {"updateAutomation": {"automation": {"id": "111"}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = UpdateAiAutomationInput(automation_id="111")
    result = await service.update_automation(inp)

    assert result == {
        "automation_id": "111",
        "message": "AI Automation updated successfully. ID: 111",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_propagates_execute_query_error():
    """create_automation propagates errors when execute_query raises."""
    mock_client = _create_mock_internal_api_client()
    mock_client.execute_query = AsyncMock(side_effect=ValueError("GraphQL error"))
    service = AiAutomationService(client=mock_client)

    inp = CreateAiAutomationInput(
        name="Test",
        event_id="card_created",
        pipe_id="1",
        prompt="Do something with %{1}",
        field_ids=["1"],
    )

    with pytest.raises(ValueError, match="GraphQL error"):
        await service.create_automation(inp)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_propagates_execute_query_error():
    """update_automation propagates errors when execute_query raises."""
    mock_client = _create_mock_internal_api_client()
    mock_client.execute_query = AsyncMock(side_effect=RuntimeError("Network error"))
    service = AiAutomationService(client=mock_client)

    inp = UpdateAiAutomationInput(automation_id="123")

    with pytest.raises(RuntimeError, match="Network error"):
        await service.update_automation(inp)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_missing_automation_id_returns_clear_error():
    """create_automation returns clear error when API response missing automation.id."""
    mock_client = _create_mock_internal_api_client({"createAutomation": {}})
    service = AiAutomationService(client=mock_client)

    inp = CreateAiAutomationInput(
        name="Test",
        event_id="card_created",
        pipe_id="1",
        prompt="Do something with %{1}",
        field_ids=["1"],
    )

    with pytest.raises(ValueError, match="automation.*id|unexpected.*payload"):
        await service.create_automation(inp)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_missing_automation_id_returns_clear_error():
    """update_automation returns clear error when API response missing automation.id."""
    mock_client = _create_mock_internal_api_client(
        {"updateAutomation": {"automation": {}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = UpdateAiAutomationInput(automation_id="123")

    with pytest.raises(ValueError, match="automation.*id|unexpected.*payload"):
        await service.update_automation(inp)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_raises_on_error_details():
    """create_automation raises ValueError when API returns error_details."""
    mock_client = _create_mock_internal_api_client(
        {
            "createAutomation": {
                "automation": None,
                "error_details": {
                    "object_name": "Automation",
                    "object_key": "base",
                    "messages": ["Pipe not found", "AI not enabled"],
                },
            }
        }
    )
    service = AiAutomationService(client=mock_client)
    inp = CreateAiAutomationInput(
        name="Test",
        event_id="card_created",
        pipe_id="1",
        prompt="Do something with %{1}",
        field_ids=["1"],
    )

    with pytest.raises(ValueError, match="API error.*Pipe not found.*AI not enabled"):
        await service.create_automation(inp)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_raises_on_error_details_as_list():
    """create_automation handles error_details when the API returns a list."""
    mock_client = _create_mock_internal_api_client(
        {
            "createAutomation": {
                "automation": None,
                "error_details": [
                    {
                        "object_name": "Automation",
                        "object_key": "base",
                        "messages": ["Pipe not found"],
                    },
                ],
            }
        }
    )
    service = AiAutomationService(client=mock_client)
    inp = CreateAiAutomationInput(
        name="Test",
        event_id="card_created",
        pipe_id="1",
        prompt="Do something with %{1}",
        field_ids=["1"],
    )

    with pytest.raises(ValueError, match="API error.*Pipe not found"):
        await service.create_automation(inp)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_raises_on_error_details():
    """update_automation raises ValueError when API returns error_details."""
    mock_client = _create_mock_internal_api_client(
        {
            "updateAutomation": {
                "automation": None,
                "error_details": {
                    "object_name": "Automation",
                    "object_key": "base",
                    "messages": ["Invalid field"],
                },
            }
        }
    )
    service = AiAutomationService(client=mock_client)
    inp = UpdateAiAutomationInput(automation_id="123")

    with pytest.raises(ValueError, match="API error.*Invalid field"):
        await service.update_automation(inp)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_raises_on_error_details_as_list():
    """update_automation handles error_details when the API returns a list."""
    mock_client = _create_mock_internal_api_client(
        {
            "updateAutomation": {
                "automation": None,
                "error_details": [
                    {
                        "object_name": "Automation",
                        "object_key": "base",
                        "messages": ["Invalid field"],
                    },
                ],
            }
        }
    )
    service = AiAutomationService(client=mock_client)
    inp = UpdateAiAutomationInput(automation_id="123")

    with pytest.raises(ValueError, match="API error.*Invalid field"):
        await service.update_automation(inp)
