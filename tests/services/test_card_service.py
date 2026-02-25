"""Unit tests for CardService.

Tests validate the card-related operations without requiring real API credentials.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from gql import Client

from pipefy_mcp.services.pipefy.card_service import CardService
from pipefy_mcp.services.pipefy.queries.card_queries import (
    FIND_CARDS_QUERY,
    GET_CARDS_QUERY,
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
    result = await service.get_cards(pipe_id, None)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {
        "pipe_id": pipe_id,
        "search": {},
        "includeFields": False,
    }, "Expected empty search and includeFields=False"
    assert result == {"cards": {"edges": []}}, "Expected cards response"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_include_fields_true_passes_includeFields_variable():
    """Test get_cards uses GET_CARDS_QUERY with includeFields=True when include_fields=True."""
    pipe_id = 303181849

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"cards": {"edges": []}})
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    await service.get_cards(pipe_id, search=None, include_fields=True)

    query_used = mock_session.execute.call_args[0][0]
    variables = mock_session.execute.call_args[1]["variable_values"]
    assert query_used is GET_CARDS_QUERY
    assert variables["includeFields"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_include_fields_false_passes_includeFields_variable():
    """Test get_cards uses GET_CARDS_QUERY with includeFields=False when include_fields=False."""
    pipe_id = 303181849

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"cards": {"edges": []}})
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    await service.get_cards(pipe_id, search=None, include_fields=False)

    query_used = mock_session.execute.call_args[0][0]
    variables = mock_session.execute.call_args[1]["variable_values"]
    assert query_used is GET_CARDS_QUERY
    assert variables["includeFields"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_cards_sends_pipeId_search_and_includeFields():
    """Test find_cards uses FIND_CARDS_QUERY with pipeId, search.fieldId, search.fieldValue, includeFields."""
    pipe_id = 303181849
    field_id = "status"
    field_value = "In Progress"

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"findCards": {"edges": []}})
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    await service.find_cards(pipe_id, field_id, field_value, include_fields=True)

    query_used = mock_session.execute.call_args[0][0]
    variables = mock_session.execute.call_args[1]["variable_values"]
    assert query_used is FIND_CARDS_QUERY
    assert variables["pipeId"] == pipe_id
    assert variables["search"] == {"fieldId": field_id, "fieldValue": field_value}
    assert variables["includeFields"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_cards_returns_raw_findCards_response():
    """Test find_cards returns the raw findCards GraphQL response."""
    pipe_id = 1
    field_id = "field_1"
    field_value = "Value 1"
    expected = {"findCards": {"edges": [{"node": {"id": "1", "title": "Card"}}]}}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=expected)
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.find_cards(
        pipe_id, field_id, field_value, include_fields=False
    )

    assert result == expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_passes_card_id_and_includeFields():
    """Test get_card passes card_id and includeFields in variable_values."""
    card_id = 12345

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"card": {"id": str(card_id), "title": "Test"}}
    )
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    await service.get_card(card_id, include_fields=False)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"card_id": card_id, "includeFields": False}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_with_include_fields_true_passes_includeFields():
    """Test get_card with include_fields=True passes includeFields=True to query."""
    card_id = 12345

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={
            "card": {
                "id": str(card_id),
                "title": "Test",
                "fields": [{"name": "Field", "value": "x"}],
            }
        }
    )
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    await service.get_card(card_id, include_fields=True)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"card_id": card_id, "includeFields": True}


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
    result = await service.create_comment(card_id=card_id, text=text)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"input": {"card_id": card_id, "text": text}}, (
        "Expected correct input shape"
    )
    assert result == {"createComment": {"comment": {"id": "c_987"}}}, (
        "Expected createComment response passthrough"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_comment_variable_shape_and_return_structure():
    """Test update_comment sends correct input shape and returns response with comment id."""
    comment_id = 12345
    text = "Updated comment text"

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"updateComment": {"comment": {"id": "c_999"}}}
    )
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.update_comment(comment_id, text)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"input": {"id": comment_id, "text": text}}, (
        "Expected correct input shape"
    )
    assert result == {"updateComment": {"comment": {"id": "c_999"}}}, (
        "Expected updateComment response with comment id"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_comment_variable_shape_and_success_return():
    """Test delete_comment sends correct input shape and returns success."""
    comment_id = 12345

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"deleteComment": {"success": True}})
    mock_client = _create_mock_gql_client(mock_session)

    service = CardService(client=mock_client)
    result = await service.delete_comment(comment_id)

    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"input": {"id": comment_id}}, "Expected correct input shape"
    assert result == {"deleteComment": {"success": True}}, (
        "Expected deleteComment success response"
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
