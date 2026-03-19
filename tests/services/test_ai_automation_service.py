"""Unit tests for AiAutomationService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pipefy_mcp.models.ai_automation import (
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
        or {"data": {"createAutomation": {"automation": {"id": "123"}}}}
    )
    return mock


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_calls_execute_query_with_correct_variables():
    """create_automation calls execute_query with createAutomation mutation and correct variables."""
    mock_client = _create_mock_internal_api_client(
        {"data": {"createAutomation": {"automation": {"id": "456"}}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = CreateAiAutomationInput(
        name="My Automation",
        event_id="card_created",
        pipe_id="303",
        prompt="Summarize the card",
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
    assert variables["action_params"]["aiParams"]["value"] == "Summarize the card"
    assert variables["action_params"]["aiParams"]["fieldIds"] == ["133", "789"]
    assert result["automation_id"] == "456"
    assert "AI Automation created successfully" in result["message"]
    assert "456" in result["message"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_returns_success_format():
    """create_automation returns automation_id and message in success format."""
    mock_client = _create_mock_internal_api_client(
        {"data": {"createAutomation": {"automation": {"id": "999"}}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = CreateAiAutomationInput(
        name="Test",
        event_id="card_created",
        pipe_id="1",
        prompt="Do something",
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
        {"data": {"updateAutomation": {"automation": {"id": "789"}}}}
    )
    service = AiAutomationService(client=mock_client)

    inp = UpdateAiAutomationInput(
        automation_id="789",
        name="Updated Name",
        active=False,
        prompt="New prompt",
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
    assert variables["input"]["action_params"]["aiParams"]["value"] == "New prompt"
    assert variables["input"]["action_params"]["aiParams"]["fieldIds"] == ["133"]
    assert result["automation_id"] == "789"
    assert "AI Automation updated successfully" in result["message"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_returns_success_format():
    """update_automation returns automation_id and message in success format."""
    mock_client = _create_mock_internal_api_client(
        {"data": {"updateAutomation": {"automation": {"id": "111"}}}}
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
        prompt="Do something",
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
    mock_client = _create_mock_internal_api_client({"data": {}})
    service = AiAutomationService(client=mock_client)

    inp = CreateAiAutomationInput(
        name="Test",
        event_id="card_created",
        pipe_id="1",
        prompt="Do something",
        field_ids=["1"],
    )

    with pytest.raises(ValueError, match="automation.*id|unexpected.*payload"):
        await service.create_automation(inp)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_missing_automation_id_returns_clear_error():
    """update_automation returns clear error when API response missing automation.id."""
    mock_client = _create_mock_internal_api_client(
        {"data": {"updateAutomation": {"automation": {}}}}
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
            "data": {
                "createAutomation": {
                    "automation": None,
                    "error_details": {
                        "object_name": "Automation",
                        "object_key": "base",
                        "messages": ["Pipe not found", "AI not enabled"],
                    },
                }
            }
        }
    )
    service = AiAutomationService(client=mock_client)
    inp = CreateAiAutomationInput(
        name="Test",
        event_id="card_created",
        pipe_id="1",
        prompt="Do something",
        field_ids=["1"],
    )

    with pytest.raises(ValueError, match="API error.*Pipe not found.*AI not enabled"):
        await service.create_automation(inp)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_raises_on_error_details():
    """update_automation raises ValueError when API returns error_details."""
    mock_client = _create_mock_internal_api_client(
        {
            "data": {
                "updateAutomation": {
                    "automation": None,
                    "error_details": {
                        "object_name": "Automation",
                        "object_key": "base",
                        "messages": ["Invalid field"],
                    },
                }
            }
        }
    )
    service = AiAutomationService(client=mock_client)
    inp = UpdateAiAutomationInput(automation_id="123")

    with pytest.raises(ValueError, match="API error.*Invalid field"):
        await service.update_automation(inp)
