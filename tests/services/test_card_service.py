"""Unit tests for CardService.

Tests validate the card-related operations without requiring real API credentials.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from gql import Client

from pipefy_mcp.services.pipefy.card_service import CardService
from pipefy_mcp.services.pipefy.queries.card_queries import (
    GET_CARDS_QUERY,
    GET_CARDS_WITH_FIELDS_QUERY,
)


def _create_mock_gql_client(mock_session: AsyncMock) -> MagicMock:
    """Create a mock gql.Client with async context manager support."""
    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_converts_fields_and_sets_generated_by_ai():
    """Test create_card converts dict fields to array format with generated_by_ai."""
    pipe_id = 303181849
    fields = {"title": "Teste-MCP"}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"createCard": {"card": {"id": "12345"}}}
    )
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.create_card(pipe_id, fields)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables["pipe_id"] == pipe_id, "Expected pipe_id in variables"
    assert variables["fields"] == [
        {"field_id": "title", "field_value": "Teste-MCP", "generated_by_ai": True}
    ], "Expected fields converted to array format"
    assert result == {"createCard": {"card": {"id": "12345"}}}, (
        "Expected createCard response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_with_empty_dict_sends_empty_list():
    """Test that create_card with empty dict sends fields as empty list to GraphQL."""
    pipe_id = 303181849
    fields = {}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"createCard": {"card": {"id": "12345"}}}
    )
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.create_card(pipe_id, fields)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables["pipe_id"] == pipe_id, "Expected pipe_id in variables"
    assert variables["fields"] == [], "Empty dict should result in empty list"
    assert result == {"createCard": {"card": {"id": "12345"}}}, (
        "Expected createCard response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_none_search_sends_empty_search():
    """Test get_cards sends empty search object when search is None."""
    pipe_id = 303181849

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"cards": {"edges": []}})
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.get_cards(pipe_id, None)  # type: ignore[arg-type]

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"pipe_id": pipe_id, "search": {}}, (
        "Expected empty search object"
    )
    assert result == {"cards": {"edges": []}}, "Expected cards response"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_include_fields_true_uses_get_cards_with_fields_query():
    """Test get_cards uses GET_CARDS_WITH_FIELDS_QUERY when include_fields=True."""
    pipe_id = 303181849

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"cards": {"edges": []}})
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    await service.get_cards(pipe_id, search=None, include_fields=True)

    query_used = mock_session.execute.call_args[0][0]
    assert query_used is GET_CARDS_WITH_FIELDS_QUERY, (
        "Expected GET_CARDS_WITH_FIELDS_QUERY when include_fields=True"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_include_fields_false_uses_get_cards_query():
    """Test get_cards uses GET_CARDS_QUERY when include_fields=False."""
    pipe_id = 303181849

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"cards": {"edges": []}})
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    await service.get_cards(pipe_id, search=None, include_fields=False)

    query_used = mock_session.execute.call_args[0][0]
    assert query_used is GET_CARDS_QUERY, (
        "Expected GET_CARDS_QUERY when include_fields=False"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_move_card_to_phase_variable_shape():
    """Test move_card_to_phase sends correct input shape."""
    card_id = 12345
    destination_phase_id = 678

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"moveCardToPhase": {"clientMutationId": None}}
    )
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.move_card_to_phase(card_id, destination_phase_id)

    variables = mock_session.execute.call_args[1]["variable_values"]
    expected_input = {"card_id": card_id, "destination_phase_id": destination_phase_id}
    assert variables == {"input": expected_input}, "Expected correct input shape"
    assert result == {"moveCardToPhase": {"clientMutationId": None}}, (
        "Expected mutation response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_card_attribute_mode_uses_update_card_shape():
    """Test update_card uses updateCard mutation when title is provided."""
    card_id = 12345
    new_title = "Updated Card Title"

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"updateCard": {"card": {"id": "12345"}}}
    )
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.update_card(card_id, title=new_title)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"input": {"id": card_id, "title": new_title}}, (
        "Expected updateCard input"
    )
    assert result == {"updateCard": {"card": {"id": "12345"}}}, (
        "Expected updateCard response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_card_with_due_date_includes_due_date_in_input():
    """Test that update_card with due_date correctly passes it to GraphQL input."""
    card_id = 12345
    due_date = "2025-12-31"

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"updateCard": {"card": {"id": "12345"}}}
    )
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.update_card(card_id, due_date=due_date)

    variables = mock_session.execute.call_args[1]["variable_values"]
    expected_input = {"id": card_id, "due_date": due_date}
    assert variables == {"input": expected_input}, "Expected due_date in input"
    assert result == {"updateCard": {"card": {"id": "12345"}}}, (
        "Expected updateCard response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_card_field_mode_uses_update_fields_values_shape():
    """Test update_card uses updateFieldsValues mutation when field_updates is provided."""
    card_id = 12345
    field_updates = [{"field_id": "field_1", "value": "Value 1"}]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"updateFieldsValues": {"success": True}}
    )
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.update_card(card_id, field_updates=field_updates)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables["input"]["nodeId"] == card_id, "Expected nodeId in input"
    expected_values = [
        {
            "fieldId": "field_1",
            "value": "Value 1",
            "operation": "REPLACE",
            "generatedByAi": True,
        }
    ]
    assert variables["input"]["values"] == expected_values, (
        "Expected formatted field values"
    )
    assert result == {"updateFieldsValues": {"success": True}}, (
        "Expected mutation response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_comment_variable_shape_and_return_passthrough():
    """Test create_comment sends correct input shape and returns response unchanged."""
    card_id = 12345
    text = "This is a comment"

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"createComment": {"comment": {"id": "c_987"}}}
    )
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.create_comment(card_id=card_id, text=text)  # type: ignore[attr-defined]

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"input": {"card_id": card_id, "text": text}}, (
        "Expected correct input shape"
    )
    assert result == {"createComment": {"comment": {"id": "c_987"}}}, (
        "Expected createComment response passthrough"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_card_success_scenario():
    """Test delete_card sends correct input and returns success response."""
    card_id = 12345

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"deleteCard": {"success": True}})
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.delete_card(card_id)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"input": {"id": card_id}}, "Expected correct input shape"
    assert result == {"deleteCard": {"success": True}}, "Expected deleteCard response"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_card_resource_not_found_error():
    """Test delete_card returns error response for RESOURCE_NOT_FOUND."""
    card_id = 99999

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={
            "deleteCard": {"success": False, "errors": ["RESOURCE_NOT_FOUND"]}
        }
    )
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.delete_card(card_id)

    assert result == {
        "deleteCard": {"success": False, "errors": ["RESOURCE_NOT_FOUND"]}
    }, "Expected error response passthrough"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_card_permission_denied_error():
    """Test delete_card returns error response for PERMISSION_DENIED."""
    card_id = 12345

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"deleteCard": {"success": False, "errors": ["PERMISSION_DENIED"]}}
    )
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.delete_card(card_id)

    assert result == {
        "deleteCard": {"success": False, "errors": ["PERMISSION_DENIED"]}
    }, "Expected error response passthrough"
