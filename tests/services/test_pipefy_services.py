from unittest.mock import AsyncMock, MagicMock

import pytest
from gql import Client

from pipefy_mcp.services.pipefy.card_service import CardService
from pipefy_mcp.services.pipefy.pipe_service import PipeService


def _make_mock_client(mock_session: AsyncMock) -> MagicMock:
    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipe_service_get_pipe_passes_pipe_id_variable():
    pipe_id = 303181849

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"pipe": {"id": str(pipe_id)}})
    mock_client = _make_mock_client(mock_session)

    service = PipeService(client=mock_client)
    result = await service.get_pipe(pipe_id)

    mock_session.execute.assert_called_once()
    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"pipe_id": pipe_id}
    assert result == {"pipe": {"id": str(pipe_id)}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipe_service_get_start_form_fields_empty_returns_message():
    pipe_id = 303181849

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"pipe": {"start_form_fields": []}})
    mock_client = _make_mock_client(mock_session)

    service = PipeService(client=mock_client)
    result = await service.get_start_form_fields(pipe_id)

    assert result == {
        "message": "This pipe has no start form fields configured.",
        "start_form_fields": [],
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipe_service_get_start_form_fields_required_only_filters_and_returns_message_when_none():
    pipe_id = 303181849
    mock_fields = [
        {"id": "priority", "required": False},
        {"id": "notes", "required": False},
    ]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"pipe": {"start_form_fields": mock_fields}})
    mock_client = _make_mock_client(mock_session)

    service = PipeService(client=mock_client)
    result = await service.get_start_form_fields(pipe_id, required_only=True)

    assert result == {
        "message": "This pipe has no required fields in the start form.",
        "start_form_fields": [],
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipe_service_get_start_form_fields_required_only_returns_only_required():
    pipe_id = 303181849
    mock_fields = [
        {"id": "title", "required": True},
        {"id": "priority", "required": False},
        {"id": "due_date", "required": True},
    ]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"pipe": {"start_form_fields": mock_fields}})
    mock_client = _make_mock_client(mock_session)

    service = PipeService(client=mock_client)
    result = await service.get_start_form_fields(pipe_id, required_only=True)

    assert result == {"start_form_fields": [{"id": "title", "required": True}, {"id": "due_date", "required": True}]}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_card_service_create_card_converts_fields_and_sets_generated_by_ai():
    pipe_id = 303181849
    fields = {"title": "Teste-MCP"}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"createCard": {"card": {"id": "12345"}}})
    mock_client = _make_mock_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.create_card(pipe_id, fields)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables["pipe_id"] == pipe_id
    assert variables["fields"] == [
        {"field_id": "title", "field_value": "Teste-MCP", "generated_by_ai": True}
    ]
    assert result == {"createCard": {"card": {"id": "12345"}}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_card_service_get_cards_with_none_search_sends_empty_search():
    pipe_id = 303181849

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"cards": {"edges": []}})
    mock_client = _make_mock_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.get_cards(pipe_id, None)  # type: ignore[arg-type]

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"pipe_id": pipe_id, "search": {}}
    assert result == {"cards": {"edges": []}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_card_service_move_card_to_phase_variable_shape():
    card_id = 12345
    destination_phase_id = 678

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"moveCardToPhase": {"clientMutationId": None}})
    mock_client = _make_mock_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.move_card_to_phase(card_id, destination_phase_id)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"input": {"card_id": card_id, "destination_phase_id": destination_phase_id}}
    assert result == {"moveCardToPhase": {"clientMutationId": None}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_card_service_update_card_attribute_mode_uses_update_card_shape():
    card_id = 12345
    new_title = "Updated Card Title"

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"updateCard": {"card": {"id": "12345"}}})
    mock_client = _make_mock_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.update_card(card_id, title=new_title)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"input": {"id": card_id, "title": new_title}}
    assert result == {"updateCard": {"card": {"id": "12345"}}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_card_service_update_card_field_mode_uses_update_fields_values_shape_and_flags():
    card_id = 12345
    field_updates = [{"field_id": "field_1", "value": "Value 1"}]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"updateFieldsValues": {"success": True}})
    mock_client = _make_mock_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.update_card(card_id, field_updates=field_updates)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables["input"]["nodeId"] == card_id
    assert variables["input"]["values"] == [
        {"fieldId": "field_1", "value": "Value 1", "operation": "REPLACE", "generatedByAi": True}
    ]
    assert result == {"updateFieldsValues": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_card_service_create_card_with_empty_dict_sends_empty_list():
    """Test that create_card with empty dict sends fields as empty list to GraphQL."""
    pipe_id = 303181849
    fields = {}  # empty dict

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"createCard": {"card": {"id": "12345"}}})
    mock_client = _make_mock_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.create_card(pipe_id, fields)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables["pipe_id"] == pipe_id
    assert variables["fields"] == []  # empty dict should result in empty list
    assert result == {"createCard": {"card": {"id": "12345"}}}
