"""Unit tests for CardService.

Tests validate the card-related operations without requiring real API credentials.
"""

import pytest
from _shared.mock_clients import mock_executor

from pipefy_sdk.queries.card_queries import (
    CREATE_CARD_MUTATION,
    FIND_CARDS_QUERY,
    GET_CARD_RELATIONS_QUERY,
    GET_CARDS_QUERY,
)
from pipefy_sdk.services.card_service import CardService


def _make_service(return_value: dict):
    executor = mock_executor(return_value)
    return CardService(executor=executor), executor


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_converts_fields_and_sets_generated_by_ai():
    """Test create_card converts dict fields to array format with generated_by_ai."""
    pipe_id = 303181849
    fields = {"title": "Teste-MCP"}

    service, executor = _make_service({"createCard": {"card": {"id": "12345"}}})
    result = await service.create_card(pipe_id, fields)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {
        "input": {
            "pipe_id": str(pipe_id),
            "fields_attributes": [
                {
                    "field_id": "title",
                    "field_value": "Teste-MCP",
                    "generated_by_ai": True,
                }
            ],
        }
    }
    assert result == {"createCard": {"card": {"id": "12345"}}}, (
        "Expected createCard response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_with_phase_id_sends_create_card_input():
    """create_card with phase_id uses CreateCardInput with phase_id and fields_attributes."""
    pipe_id = 303181849
    phase_id = 987654321
    fields = {"title": "Orphan phase card"}

    service, executor = _make_service({"createCard": {"card": {"id": "12345"}}})
    await service.create_card(pipe_id, fields, phase_id=phase_id)

    query_used = executor.execute_query.call_args[0][0]
    variables = executor.execute_query.call_args[0][1]
    assert query_used is CREATE_CARD_MUTATION
    assert "CreateCardInput" in CREATE_CARD_MUTATION.document.loc.source.body
    assert variables == {
        "input": {
            "pipe_id": str(pipe_id),
            "phase_id": str(phase_id),
            "fields_attributes": [
                {
                    "field_id": "title",
                    "field_value": "Orphan phase card",
                    "generated_by_ai": True,
                }
            ],
        }
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_with_phase_id_and_title_sends_create_card_input():
    """create_card passes optional title on CreateCardInput when provided."""
    pipe_id = 303181849
    phase_id = 987654321
    card_title = "Seed card title"

    service, executor = _make_service({"createCard": {"card": {"id": "12345"}}})
    await service.create_card(pipe_id, {}, phase_id=phase_id, title=card_title)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {
        "input": {
            "pipe_id": str(pipe_id),
            "phase_id": str(phase_id),
            "title": card_title,
            "fields_attributes": [],
        }
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_without_phase_id_uses_create_card_input():
    """create_card without phase_id still uses CreateCardInput (no phase_id key)."""
    pipe_id = 303181849
    fields = {"title": "Start form card"}

    service, executor = _make_service({"createCard": {"card": {"id": "12345"}}})
    await service.create_card(pipe_id, fields)

    query_used = executor.execute_query.call_args[0][0]
    variables = executor.execute_query.call_args[0][1]
    assert query_used is CREATE_CARD_MUTATION
    assert "CreateCardInput" in CREATE_CARD_MUTATION.document.loc.source.body
    assert variables == {
        "input": {
            "pipe_id": str(pipe_id),
            "fields_attributes": [
                {
                    "field_id": "title",
                    "field_value": "Start form card",
                    "generated_by_ai": True,
                }
            ],
        }
    }
    assert "phase_id" not in variables["input"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_with_title_only_sends_create_card_input():
    """create_card passes title on CreateCardInput without phase_id (MCP happy path)."""
    pipe_id = 303181849
    card_title = "Start form title"

    service, executor = _make_service({"createCard": {"card": {"id": "12345"}}})
    await service.create_card(pipe_id, {}, title=card_title)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {
        "input": {
            "pipe_id": str(pipe_id),
            "title": card_title,
            "fields_attributes": [],
        }
    }
    assert "phase_id" not in variables["input"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_with_empty_dict_sends_empty_list():
    """Test that create_card with empty dict sends fields as empty list to GraphQL."""
    pipe_id = 303181849
    fields = {}

    service, executor = _make_service({"createCard": {"card": {"id": "12345"}}})
    result = await service.create_card(pipe_id, fields)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {
        "input": {
            "pipe_id": str(pipe_id),
            "fields_attributes": [],
        }
    }
    assert result == {"createCard": {"card": {"id": "12345"}}}, (
        "Expected createCard response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_none_search_sends_empty_search():
    """Test get_cards sends empty search object when search is None."""
    pipe_id = 303181849

    service, executor = _make_service({"cards": {"edges": []}})
    result = await service.get_cards(pipe_id, None)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {
        "pipe_id": str(pipe_id),
        "search": {},
        "includeFields": False,
    }, "Expected empty search and includeFields=False"
    assert result == {"cards": {"edges": []}}, "Expected cards response"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_include_fields_true_passes_includeFields_variable():
    """Test get_cards uses GET_CARDS_QUERY with includeFields=True when include_fields=True."""
    pipe_id = 303181849

    service, executor = _make_service({"cards": {"edges": []}})
    await service.get_cards(pipe_id, search=None, include_fields=True)

    query_used = executor.execute_query.call_args[0][0]
    variables = executor.execute_query.call_args[0][1]
    assert query_used is GET_CARDS_QUERY
    assert variables["includeFields"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_include_fields_false_passes_includeFields_variable():
    """Test get_cards uses GET_CARDS_QUERY with includeFields=False when include_fields=False."""
    pipe_id = 303181849

    service, executor = _make_service({"cards": {"edges": []}})
    await service.get_cards(pipe_id, search=None, include_fields=False)

    query_used = executor.execute_query.call_args[0][0]
    variables = executor.execute_query.call_args[0][1]
    assert query_used is GET_CARDS_QUERY
    assert variables["includeFields"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_cards_sends_pipeId_search_and_includeFields():
    """Test find_cards uses FIND_CARDS_QUERY with pipeId, search.fieldId, search.fieldValue, includeFields."""
    pipe_id = 303181849
    field_id = "status"
    field_value = "In Progress"

    service, executor = _make_service({"findCards": {"edges": []}})
    await service.find_cards(pipe_id, field_id, field_value, include_fields=True)

    query_used = executor.execute_query.call_args[0][0]
    variables = executor.execute_query.call_args[0][1]
    assert query_used is FIND_CARDS_QUERY
    assert variables["pipeId"] == str(pipe_id)
    assert variables["search"] == {"fieldId": field_id, "fieldValue": field_value}
    assert variables["includeFields"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_cards_passes_first_and_after():
    pipe_id = 1
    field_id = "f"
    field_value = "v"
    service, executor = _make_service({"findCards": {"edges": []}})
    await service.find_cards(
        pipe_id,
        field_id,
        field_value,
        include_fields=False,
        first=20,
        after="c1",
    )
    variables = executor.execute_query.call_args[0][1]
    assert variables["first"] == 20
    assert variables["after"] == "c1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_cards_returns_raw_findCards_response():
    """Test find_cards returns the raw findCards GraphQL response."""
    pipe_id = 1
    field_id = "field_1"
    field_value = "Value 1"
    expected = {"findCards": {"edges": [{"node": {"id": "1", "title": "Card"}}]}}

    service, _ = _make_service(expected)
    result = await service.find_cards(
        pipe_id, field_id, field_value, include_fields=False
    )

    assert result == expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_passes_card_id_and_includeFields():
    """Test get_card passes card_id and includeFields in variable_values."""
    card_id = 12345

    service, executor = _make_service({"card": {"id": str(card_id), "title": "Test"}})
    await service.get_card(card_id, include_fields=False)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {"card_id": str(card_id), "includeFields": False}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_accepts_alphanumeric_id():
    """Test get_card passes an alphanumeric ID through to GraphQL variables unchanged."""
    service, executor = _make_service({"card": {"id": "Yr5RUVCi", "title": "Test"}})
    await service.get_card("Yr5RUVCi")

    variables = executor.execute_query.call_args[0][1]
    assert variables == {"card_id": "Yr5RUVCi", "includeFields": False}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_with_include_fields_true_passes_includeFields():
    """Test get_card with include_fields=True passes includeFields=True to query."""
    card_id = 12345

    service, executor = _make_service(
        {
            "card": {
                "id": str(card_id),
                "title": "Test",
                "fields": [{"name": "Field", "value": "x"}],
            }
        },
    )
    await service.get_card(card_id, include_fields=True)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {"card_id": str(card_id), "includeFields": True}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_move_card_to_phase_variable_shape():
    """Test move_card_to_phase sends correct input shape."""
    card_id = 12345
    destination_phase_id = 678

    service, executor = _make_service({"moveCardToPhase": {"clientMutationId": None}})
    result = await service.move_card_to_phase(card_id, destination_phase_id)

    variables = executor.execute_query.call_args[0][1]
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
async def test_update_card_attribute_mode_uses_update_card_shape():
    """Test update_card uses updateCard mutation when title is provided."""
    card_id = 12345
    new_title = "Updated Card Title"

    service, executor = _make_service({"updateCard": {"card": {"id": "12345"}}})
    result = await service.update_card(card_id, title=new_title)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {"input": {"id": str(card_id), "title": new_title}}, (
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

    service, executor = _make_service({"updateCard": {"card": {"id": "12345"}}})
    result = await service.update_card(card_id, due_date=due_date)

    variables = executor.execute_query.call_args[0][1]
    expected_input = {"id": str(card_id), "due_date": due_date}
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

    service, executor = _make_service({"updateFieldsValues": {"success": True}})
    result = await service.update_card(card_id, field_updates=field_updates)

    variables = executor.execute_query.call_args[0][1]
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
async def test_create_comment_variable_shape_and_returns_comment_id():
    """Test create_comment sends correct input shape and returns the new comment id."""
    card_id = 12345
    text = "This is a comment"

    service, executor = _make_service({"createComment": {"comment": {"id": "c_987"}}})
    result = await service.create_comment(card_id=card_id, text=text)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {"input": {"card_id": str(card_id), "text": text}}, (
        "Expected correct input shape"
    )
    assert result == "c_987", "Expected the comment id, not the raw GraphQL payload"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_comment_variable_shape_and_returns_comment_id():
    """Test update_comment sends correct input shape and returns the updated comment id."""
    comment_id = 12345
    text = "Updated comment text"

    service, executor = _make_service({"updateComment": {"comment": {"id": "c_999"}}})
    result = await service.update_comment(comment_id, text)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {"input": {"id": str(comment_id), "text": text}}, (
        "Expected correct input shape"
    )
    assert result == "c_999", "Expected the comment id, not the raw GraphQL payload"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_comment_variable_shape_and_success_return():
    """Test delete_comment sends correct input shape and returns success."""
    comment_id = 12345

    service, executor = _make_service({"deleteComment": {"success": True}})
    result = await service.delete_comment(comment_id)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {"input": {"id": str(comment_id)}}, (
        "Expected correct input shape"
    )
    assert result == {"deleteComment": {"success": True}}, (
        "Expected deleteComment success response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_card_success_scenario():
    """Test delete_card sends correct input and returns success response."""
    card_id = 12345

    service, executor = _make_service({"deleteCard": {"success": True}})
    result = await service.delete_card(card_id)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {"input": {"id": str(card_id)}}, "Expected correct input shape"
    assert result == {"deleteCard": {"success": True}}, "Expected deleteCard response"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_card_resource_not_found_error():
    """Test delete_card returns error response for RESOURCE_NOT_FOUND."""
    card_id = 99999

    service, _ = _make_service(
        {"deleteCard": {"success": False, "errors": ["RESOURCE_NOT_FOUND"]}},
    )
    result = await service.delete_card(card_id)

    assert result == {
        "deleteCard": {"success": False, "errors": ["RESOURCE_NOT_FOUND"]}
    }, "Expected error response passthrough"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_card_permission_denied_error():
    """Test delete_card returns error response for PERMISSION_DENIED."""
    card_id = 12345

    service, _ = _make_service(
        {"deleteCard": {"success": False, "errors": ["PERMISSION_DENIED"]}},
    )
    result = await service.delete_card(card_id)

    assert result == {
        "deleteCard": {"success": False, "errors": ["PERMISSION_DENIED"]}
    }, "Expected error response passthrough"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_relations_uses_query_and_cardId_variable():
    """Test get_card_relations calls GET_CARD_RELATIONS_QUERY with cardId."""
    card_id = 999
    expected = {
        "card": {
            "child_relations": [],
            "parent_relations": [{"name": "rel", "pipe": {"id": "1", "name": "P"}}],
        }
    }
    service, executor = _make_service(expected)
    result = await service.get_card_relations(card_id)

    query_used = executor.execute_query.call_args[0][0]
    variables = executor.execute_query.call_args[0][1]
    assert query_used is GET_CARD_RELATIONS_QUERY
    assert variables == {"cardId": "999"}
    assert result == expected
