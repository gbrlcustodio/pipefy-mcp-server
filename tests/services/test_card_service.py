"""Unit tests for CardService.

Tests validate the card-related operations without requiring real API credentials.
"""

from unittest.mock import AsyncMock

import pytest

from pipefy_mcp.services.pipefy.card_service import CardService
from pipefy_mcp.services.pipefy.queries.card_queries import (
    DELETE_CARD_RELATION_MUTATION,
    FIND_CARDS_QUERY,
    GET_CARD_RELATIONS_QUERY,
    GET_CARDS_QUERY,
)
from pipefy_mcp.settings import PipefySettings


@pytest.fixture
def mock_settings() -> PipefySettings:
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings: PipefySettings, return_value: dict) -> CardService:
    service = CardService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_converts_fields_and_sets_generated_by_ai(mock_settings):
    """Test create_card converts dict fields to array format with generated_by_ai."""
    pipe_id = 303181849
    fields = {"title": "Teste-MCP"}

    service = _make_service(mock_settings, {"createCard": {"card": {"id": "12345"}}})
    result = await service.create_card(pipe_id, fields)

    variables = service.execute_query.call_args[0][1]
    assert variables["pipe_id"] == str(pipe_id), "Expected pipe_id in variables"
    assert variables["fields"] == [
        {"field_id": "title", "field_value": "Teste-MCP", "generated_by_ai": True}
    ], "Expected fields converted to array format"
    assert result == {"createCard": {"card": {"id": "12345"}}}, (
        "Expected createCard response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_with_empty_dict_sends_empty_list(mock_settings):
    """Test that create_card with empty dict sends fields as empty list to GraphQL."""
    pipe_id = 303181849
    fields = {}

    service = _make_service(mock_settings, {"createCard": {"card": {"id": "12345"}}})
    result = await service.create_card(pipe_id, fields)

    variables = service.execute_query.call_args[0][1]
    assert variables["pipe_id"] == str(pipe_id), "Expected pipe_id in variables"
    assert variables["fields"] == [], "Empty dict should result in empty list"
    assert result == {"createCard": {"card": {"id": "12345"}}}, (
        "Expected createCard response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_none_search_sends_empty_search(mock_settings):
    """Test get_cards sends empty search object when search is None."""
    pipe_id = 303181849

    service = _make_service(mock_settings, {"cards": {"edges": []}})
    result = await service.get_cards(pipe_id, None)

    variables = service.execute_query.call_args[0][1]
    assert variables == {
        "pipe_id": str(pipe_id),
        "search": {},
        "includeFields": False,
    }, "Expected empty search and includeFields=False"
    assert result == {"cards": {"edges": []}}, "Expected cards response"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_include_fields_true_passes_includeFields_variable(
    mock_settings,
):
    """Test get_cards uses GET_CARDS_QUERY with includeFields=True when include_fields=True."""
    pipe_id = 303181849

    service = _make_service(mock_settings, {"cards": {"edges": []}})
    await service.get_cards(pipe_id, search=None, include_fields=True)

    query_used = service.execute_query.call_args[0][0]
    variables = service.execute_query.call_args[0][1]
    assert query_used is GET_CARDS_QUERY
    assert variables["includeFields"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_include_fields_false_passes_includeFields_variable(
    mock_settings,
):
    """Test get_cards uses GET_CARDS_QUERY with includeFields=False when include_fields=False."""
    pipe_id = 303181849

    service = _make_service(mock_settings, {"cards": {"edges": []}})
    await service.get_cards(pipe_id, search=None, include_fields=False)

    query_used = service.execute_query.call_args[0][0]
    variables = service.execute_query.call_args[0][1]
    assert query_used is GET_CARDS_QUERY
    assert variables["includeFields"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_cards_sends_pipeId_search_and_includeFields(mock_settings):
    """Test find_cards uses FIND_CARDS_QUERY with pipeId, search.fieldId, search.fieldValue, includeFields."""
    pipe_id = 303181849
    field_id = "status"
    field_value = "In Progress"

    service = _make_service(mock_settings, {"findCards": {"edges": []}})
    await service.find_cards(pipe_id, field_id, field_value, include_fields=True)

    query_used = service.execute_query.call_args[0][0]
    variables = service.execute_query.call_args[0][1]
    assert query_used is FIND_CARDS_QUERY
    assert variables["pipeId"] == str(pipe_id)
    assert variables["search"] == {"fieldId": field_id, "fieldValue": field_value}
    assert variables["includeFields"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_cards_passes_first_and_after(mock_settings):
    pipe_id = 1
    field_id = "f"
    field_value = "v"
    service = _make_service(mock_settings, {"findCards": {"edges": []}})
    await service.find_cards(
        pipe_id,
        field_id,
        field_value,
        include_fields=False,
        first=20,
        after="c1",
    )
    variables = service.execute_query.call_args[0][1]
    assert variables["first"] == 20
    assert variables["after"] == "c1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_cards_returns_raw_findCards_response(mock_settings):
    """Test find_cards returns the raw findCards GraphQL response."""
    pipe_id = 1
    field_id = "field_1"
    field_value = "Value 1"
    expected = {"findCards": {"edges": [{"node": {"id": "1", "title": "Card"}}]}}

    service = _make_service(mock_settings, expected)
    result = await service.find_cards(
        pipe_id, field_id, field_value, include_fields=False
    )

    assert result == expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_passes_card_id_and_includeFields(mock_settings):
    """Test get_card passes card_id and includeFields in variable_values."""
    card_id = 12345

    service = _make_service(
        mock_settings, {"card": {"id": str(card_id), "title": "Test"}}
    )
    await service.get_card(card_id, include_fields=False)

    variables = service.execute_query.call_args[0][1]
    assert variables == {"card_id": str(card_id), "includeFields": False}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_accepts_alphanumeric_id(mock_settings):
    """Test get_card passes an alphanumeric ID through to GraphQL variables unchanged."""
    service = _make_service(
        mock_settings, {"card": {"id": "Yr5RUVCi", "title": "Test"}}
    )
    await service.get_card("Yr5RUVCi")

    variables = service.execute_query.call_args[0][1]
    assert variables == {"card_id": "Yr5RUVCi", "includeFields": False}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_with_include_fields_true_passes_includeFields(mock_settings):
    """Test get_card with include_fields=True passes includeFields=True to query."""
    card_id = 12345

    service = _make_service(
        mock_settings,
        {
            "card": {
                "id": str(card_id),
                "title": "Test",
                "fields": [{"name": "Field", "value": "x"}],
            }
        },
    )
    await service.get_card(card_id, include_fields=True)

    variables = service.execute_query.call_args[0][1]
    assert variables == {"card_id": str(card_id), "includeFields": True}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_move_card_to_phase_variable_shape(mock_settings):
    """Test move_card_to_phase sends correct input shape."""
    card_id = 12345
    destination_phase_id = 678

    service = _make_service(
        mock_settings, {"moveCardToPhase": {"clientMutationId": None}}
    )
    result = await service.move_card_to_phase(card_id, destination_phase_id)

    variables = service.execute_query.call_args[0][1]
    expected_input = {
        "card_id": str(card_id),
        "destination_phase_id": str(destination_phase_id),
    }
    assert variables == {"input": expected_input}, "Expected correct input shape"
    assert result == {"moveCardToPhase": {"clientMutationId": None}}, (
        "Expected mutation response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_card_attribute_mode_uses_update_card_shape(mock_settings):
    """Test update_card uses updateCard mutation when title is provided."""
    card_id = 12345
    new_title = "Updated Card Title"

    service = _make_service(mock_settings, {"updateCard": {"card": {"id": "12345"}}})
    result = await service.update_card(card_id, title=new_title)

    variables = service.execute_query.call_args[0][1]
    assert variables == {"input": {"id": str(card_id), "title": new_title}}, (
        "Expected updateCard input"
    )
    assert result == {"updateCard": {"card": {"id": "12345"}}}, (
        "Expected updateCard response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_card_with_due_date_includes_due_date_in_input(mock_settings):
    """Test that update_card with due_date correctly passes it to GraphQL input."""
    card_id = 12345
    due_date = "2025-12-31"

    service = _make_service(mock_settings, {"updateCard": {"card": {"id": "12345"}}})
    result = await service.update_card(card_id, due_date=due_date)

    variables = service.execute_query.call_args[0][1]
    expected_input = {"id": str(card_id), "due_date": due_date}
    assert variables == {"input": expected_input}, "Expected due_date in input"
    assert result == {"updateCard": {"card": {"id": "12345"}}}, (
        "Expected updateCard response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_card_field_mode_uses_update_fields_values_shape(mock_settings):
    """Test update_card uses updateFieldsValues mutation when field_updates is provided."""
    card_id = 12345
    field_updates = [{"field_id": "field_1", "value": "Value 1"}]

    service = _make_service(mock_settings, {"updateFieldsValues": {"success": True}})
    result = await service.update_card(card_id, field_updates=field_updates)

    variables = service.execute_query.call_args[0][1]
    assert variables["input"]["nodeId"] == str(card_id), "Expected nodeId in input"
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
async def test_create_comment_variable_shape_and_return_passthrough(mock_settings):
    """Test create_comment sends correct input shape and returns response unchanged."""
    card_id = 12345
    text = "This is a comment"

    service = _make_service(
        mock_settings, {"createComment": {"comment": {"id": "c_987"}}}
    )
    result = await service.create_comment(card_id=card_id, text=text)

    variables = service.execute_query.call_args[0][1]
    assert variables == {"input": {"card_id": str(card_id), "text": text}}, (
        "Expected correct input shape"
    )
    assert result == {"createComment": {"comment": {"id": "c_987"}}}, (
        "Expected createComment response passthrough"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_comment_variable_shape_and_return_structure(mock_settings):
    """Test update_comment sends correct input shape and returns response with comment id."""
    comment_id = 12345
    text = "Updated comment text"

    service = _make_service(
        mock_settings, {"updateComment": {"comment": {"id": "c_999"}}}
    )
    result = await service.update_comment(comment_id, text)

    variables = service.execute_query.call_args[0][1]
    assert variables == {"input": {"id": str(comment_id), "text": text}}, (
        "Expected correct input shape"
    )
    assert result == {"updateComment": {"comment": {"id": "c_999"}}}, (
        "Expected updateComment response with comment id"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_comment_variable_shape_and_success_return(mock_settings):
    """Test delete_comment sends correct input shape and returns success."""
    comment_id = 12345

    service = _make_service(mock_settings, {"deleteComment": {"success": True}})
    result = await service.delete_comment(comment_id)

    variables = service.execute_query.call_args[0][1]
    assert variables == {"input": {"id": str(comment_id)}}, (
        "Expected correct input shape"
    )
    assert result == {"deleteComment": {"success": True}}, (
        "Expected deleteComment success response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_card_success_scenario(mock_settings):
    """Test delete_card sends correct input and returns success response."""
    card_id = 12345

    service = _make_service(mock_settings, {"deleteCard": {"success": True}})
    result = await service.delete_card(card_id)

    variables = service.execute_query.call_args[0][1]
    assert variables == {"input": {"id": str(card_id)}}, "Expected correct input shape"
    assert result == {"deleteCard": {"success": True}}, "Expected deleteCard response"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_card_resource_not_found_error(mock_settings):
    """Test delete_card returns error response for RESOURCE_NOT_FOUND."""
    card_id = 99999

    service = _make_service(
        mock_settings,
        {"deleteCard": {"success": False, "errors": ["RESOURCE_NOT_FOUND"]}},
    )
    result = await service.delete_card(card_id)

    assert result == {
        "deleteCard": {"success": False, "errors": ["RESOURCE_NOT_FOUND"]}
    }, "Expected error response passthrough"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_card_permission_denied_error(mock_settings):
    """Test delete_card returns error response for PERMISSION_DENIED."""
    card_id = 12345

    service = _make_service(
        mock_settings,
        {"deleteCard": {"success": False, "errors": ["PERMISSION_DENIED"]}},
    )
    result = await service.delete_card(card_id)

    assert result == {
        "deleteCard": {"success": False, "errors": ["PERMISSION_DENIED"]}
    }, "Expected error response passthrough"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_relations_uses_query_and_cardId_variable(mock_settings):
    """Test get_card_relations calls GET_CARD_RELATIONS_QUERY with cardId."""
    card_id = 999
    expected = {
        "card": {
            "child_relations": [],
            "parent_relations": [{"name": "rel", "pipe": {"id": "1", "name": "P"}}],
        }
    }
    service = _make_service(mock_settings, expected)
    result = await service.get_card_relations(card_id)

    query_used = service.execute_query.call_args[0][0]
    variables = service.execute_query.call_args[0][1]
    assert query_used is GET_CARD_RELATIONS_QUERY
    assert variables == {"cardId": "999"}
    assert result == expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_card_relation_sends_top_level_graphql_variables(mock_settings):
    """Test delete_card_relation uses DELETE_CARD_RELATION_MUTATION with childId, parentId, sourceId."""
    service = _make_service(mock_settings, {"deleteCardRelation": {"success": True}})
    result = await service.delete_card_relation("c1", 2, "src-3")

    query_used = service.execute_query.call_args[0][0]
    variables = service.execute_query.call_args[0][1]
    assert query_used is DELETE_CARD_RELATION_MUTATION
    assert variables == {
        "childId": "c1",
        "parentId": "2",
        "sourceId": "src-3",
    }
    assert result == {"deleteCardRelation": {"success": True}}
