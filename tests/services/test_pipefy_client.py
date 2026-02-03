from unittest.mock import AsyncMock, MagicMock

import pytest
from gql import Client

from pipefy_mcp.services.pipefy.card_service import CardService
from pipefy_mcp.services.pipefy.client import PipefyClient
from pipefy_mcp.services.pipefy.pipe_service import PipeService


def _make_facade_client(mock_client: MagicMock) -> PipefyClient:
    client = PipefyClient.__new__(PipefyClient)
    # Keep public attr for backward compatibility
    client.client = mock_client
    # Real services with injected client (so behavior stays identical)
    client._pipe_service = PipeService(mock_client)
    client._card_service = CardService(mock_client)
    return client


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_with_dict_fields():
    """Test create_card converts dict fields to FieldValueInput array format."""
    pipe_id = 303181849
    fields_dict = {"title": "Teste-MCP", "description": "Test description"}

    # Mock the GraphQL client and session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"createCard": {"card": {"id": "12345"}}}
    )

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.create_card(pipe_id, fields_dict)

    # Verify the session was called with correct variables
    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args

    # Check that fields were converted to array format
    variables = call_args[1]["variable_values"]
    assert variables["pipe_id"] == pipe_id
    assert isinstance(variables["fields"], list)
    assert len(variables["fields"]) == 2
    assert variables["fields"][0] == {
        "field_id": "title",
        "field_value": "Teste-MCP",
        "generated_by_ai": True,
    }
    assert variables["fields"][1] == {
        "field_id": "description",
        "field_value": "Test description",
        "generated_by_ai": True,
    }

    # Verify result
    assert result == {"createCard": {"card": {"id": "12345"}}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_with_array_fields():
    """Test create_card works with already formatted array fields."""
    pipe_id = 303181849
    fields_array = [
        {"field_id": "title", "field_value": "Teste-MCP"},
        {"field_id": "description", "field_value": "Test description"},
    ]

    # Mock the GraphQL client and session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"createCard": {"card": {"id": "12345"}}}
    )

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.create_card(pipe_id, fields_array)

    # Verify the session was called with correct variables
    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args

    # Check that fields array was used and generated_by_ai was added
    variables = call_args[1]["variable_values"]
    assert variables["pipe_id"] == pipe_id
    assert len(variables["fields"]) == 2
    assert variables["fields"][0] == {
        "field_id": "title",
        "field_value": "Teste-MCP",
        "generated_by_ai": True,
    }
    assert variables["fields"][1] == {
        "field_id": "description",
        "field_value": "Test description",
        "generated_by_ai": True,
    }

    # Verify result
    assert result == {"createCard": {"card": {"id": "12345"}}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_with_empty_dict():
    """Test create_card handles empty dict fields."""
    pipe_id = 303181849
    fields_dict = {}

    # Mock the GraphQL client and session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"createCard": {"card": {"id": "12345"}}}
    )

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.create_card(pipe_id, fields_dict)

    # Verify the session was called with empty array
    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args

    variables = call_args[1]["variable_values"]
    assert variables["pipe_id"] == pipe_id
    assert variables["fields"] == []

    # Verify result
    assert result == {"createCard": {"card": {"id": "12345"}}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_with_single_field():
    """Test create_card with a single field."""
    pipe_id = 303181849
    fields_dict = {"title": "Teste-MCP"}

    # Mock the GraphQL client and session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"createCard": {"card": {"id": "12345"}}}
    )

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.create_card(pipe_id, fields_dict)

    # Verify the session was called with correct variables
    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args

    variables = call_args[1]["variable_values"]
    assert variables["pipe_id"] == pipe_id
    assert len(variables["fields"]) == 1
    assert variables["fields"][0] == {
        "field_id": "title",
        "field_value": "Teste-MCP",
        "generated_by_ai": True,
    }

    # Verify result
    assert result == {"createCard": {"card": {"id": "12345"}}}


# ============================================================================
# Tests for get_start_form_fields
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_start_form_fields_returns_all_fields():
    """Test get_start_form_fields returns all fields correctly."""
    pipe_id = 303181849
    mock_fields = [
        {
            "id": "title",
            "label": "Title",
            "type": "short_text",
            "required": True,
            "editable": True,
            "options": None,
            "description": "Enter the card title",
            "help": None,
        },
        {
            "id": "priority",
            "label": "Priority",
            "type": "select",
            "required": False,
            "editable": True,
            "options": ["Low", "Medium", "High"],
            "description": None,
            "help": "Select the priority level",
        },
    ]

    # Mock the GraphQL client and session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"pipe": {"start_form_fields": mock_fields}}
    )

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.get_start_form_fields(pipe_id)

    # Verify the session was called with correct variables
    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]
    assert variables["pipe_id"] == pipe_id

    # Verify result contains all fields
    assert "start_form_fields" in result
    assert len(result["start_form_fields"]) == 2
    assert result["start_form_fields"][0]["id"] == "title"
    assert result["start_form_fields"][1]["id"] == "priority"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_start_form_fields_required_only_filter():
    """Test get_start_form_fields with required_only=True filters correctly."""
    pipe_id = 303181849
    mock_fields = [
        {
            "id": "title",
            "label": "Title",
            "type": "short_text",
            "required": True,
            "editable": True,
            "options": None,
            "description": None,
            "help": None,
        },
        {
            "id": "priority",
            "label": "Priority",
            "type": "select",
            "required": False,
            "editable": True,
            "options": ["Low", "Medium", "High"],
            "description": None,
            "help": None,
        },
        {
            "id": "due_date",
            "label": "Due Date",
            "type": "date",
            "required": True,
            "editable": True,
            "options": None,
            "description": None,
            "help": None,
        },
    ]

    # Mock the GraphQL client and session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"pipe": {"start_form_fields": mock_fields}}
    )

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.get_start_form_fields(pipe_id, required_only=True)

    # Verify only required fields are returned
    assert "start_form_fields" in result
    assert len(result["start_form_fields"]) == 2
    assert all(field["required"] for field in result["start_form_fields"])
    assert result["start_form_fields"][0]["id"] == "title"
    assert result["start_form_fields"][1]["id"] == "due_date"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_start_form_fields_empty_returns_friendly_message():
    """Test get_start_form_fields returns user-friendly message when no fields configured."""
    pipe_id = 303181849

    # Mock the GraphQL client and session with empty fields
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"pipe": {"start_form_fields": []}})

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.get_start_form_fields(pipe_id)

    # Verify user-friendly message is returned
    assert "message" in result
    assert result["message"] == "This pipe has no start form fields configured."
    assert "start_form_fields" in result
    assert result["start_form_fields"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_start_form_fields_required_only_no_required_fields():
    """Test get_start_form_fields with required_only=True when all fields are optional."""
    pipe_id = 303181849
    mock_fields = [
        {
            "id": "priority",
            "label": "Priority",
            "type": "select",
            "required": False,
            "editable": True,
            "options": ["Low", "Medium", "High"],
            "description": None,
            "help": None,
        },
        {
            "id": "notes",
            "label": "Notes",
            "type": "long_text",
            "required": False,
            "editable": True,
            "options": None,
            "description": None,
            "help": None,
        },
    ]

    # Mock the GraphQL client and session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"pipe": {"start_form_fields": mock_fields}}
    )

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.get_start_form_fields(pipe_id, required_only=True)

    # Verify user-friendly message is returned for no required fields
    assert "message" in result
    assert result["message"] == "This pipe has no required fields in the start form."
    assert "start_form_fields" in result
    assert result["start_form_fields"] == []


# ============================================================================
# Tests for update_card_field
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_card_field_success():
    """Test update_card_field updates a single field successfully."""
    card_id = 12345
    field_id = "status"
    new_value = "In Progress"

    mock_response = {
        "updateCardField": {
            "card": {
                "id": "12345",
                "title": "Test Card",
                "fields": [
                    {
                        "field": {"id": "status", "label": "Status"},
                        "value": "In Progress",
                    }
                ],
                "updated_at": "2024-12-16T10:00:00Z",
            },
            "success": True,
            "clientMutationId": None,
        }
    }

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_response)

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.update_card_field(card_id, field_id, new_value)

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]

    assert variables["input"]["card_id"] == card_id
    assert variables["input"]["field_id"] == field_id
    assert variables["input"]["new_value"] == new_value
    assert result == mock_response


# ============================================================================
# Tests for update_card
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_card_replacement_mode_with_title():
    """Test update_card uses updateCard mutation when title is provided."""
    card_id = 12345
    new_title = "Updated Card Title"

    mock_response = {
        "updateCard": {
            "card": {
                "id": "12345",
                "title": "Updated Card Title",
                "current_phase": {"id": "1", "name": "In Progress"},
                "assignees": [],
                "labels": [],
                "due_date": None,
                "updated_at": "2024-12-16T10:00:00Z",
            },
            "clientMutationId": None,
        }
    }

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_response)

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.update_card(card_id, title=new_title)

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]

    assert variables["input"]["id"] == card_id
    assert variables["input"]["title"] == new_title
    assert result == mock_response


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_card_with_fields_dict_uses_update_fields_values():
    """Test update_card with field_updates list uses updateFieldsValues mutation."""
    card_id = 12345
    field_updates = [
        {"field_id": "field_1", "value": "Value 1"},
        {"field_id": "field_2", "value": "Value 2"},
    ]

    mock_response = {
        "updateFieldsValues": {
            "success": True,
            "userErrors": [],
            "updatedNode": {"id": "12345", "title": "Test Card"},
        }
    }

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_response)

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.update_card(card_id, field_updates=field_updates)

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]

    # Fields are converted to updateFieldsValues format
    assert variables["input"]["nodeId"] == card_id
    assert "values" in variables["input"]
    values = variables["input"]["values"]
    assert len(values) == 2
    # Check that fields were converted to camelCase format with generatedByAi
    field_ids = [v["fieldId"] for v in values]
    assert "field_1" in field_ids
    assert "field_2" in field_ids
    assert all(v["generatedByAi"] is True for v in values)
    assert all(v["operation"] == "REPLACE" for v in values)
    assert result == mock_response


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_card_replacement_mode_with_assignees_and_labels():
    """Test update_card with assignee_ids and label_ids."""
    card_id = 12345
    assignee_ids = [100, 200]
    label_ids = [300, 400]

    mock_response = {
        "updateCard": {
            "card": {
                "id": "12345",
                "title": "Test Card",
                "assignees": [
                    {"id": "100", "name": "User 1"},
                    {"id": "200", "name": "User 2"},
                ],
                "labels": [
                    {"id": "300", "name": "Label 1"},
                    {"id": "400", "name": "Label 2"},
                ],
            },
            "clientMutationId": None,
        }
    }

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_response)

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.update_card(
        card_id, assignee_ids=assignee_ids, label_ids=label_ids
    )

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]

    assert variables["input"]["id"] == card_id
    assert variables["input"]["assignee_ids"] == assignee_ids
    assert variables["input"]["label_ids"] == label_ids
    assert result == mock_response


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_card_incremental_mode_with_add_operation():
    """Test update_card uses updateFieldsValues mutation when ADD operation is present."""
    card_id = 12345
    values = [{"field_id": "assignees", "value": [123], "operation": "ADD"}]

    mock_response = {
        "updateFieldsValues": {
            "success": True,
            "userErrors": [],
            "updatedNode": {
                "id": "12345",
                "title": "Test Card",
                "assignees": [{"id": "123", "name": "New User"}],
                "updated_at": "2024-12-16T10:00:00Z",
            },
        }
    }

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_response)

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.update_card(card_id, field_updates=values)

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]

    assert variables["input"]["nodeId"] == card_id
    assert "values" in variables["input"]
    assert result == mock_response


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_card_incremental_mode_with_remove_operation():
    """Test update_card uses updateFieldsValues mutation when REMOVE operation is present."""
    card_id = 12345
    values = [{"field_id": "labels", "value": [456], "operation": "REMOVE"}]

    mock_response = {
        "updateFieldsValues": {
            "success": True,
            "userErrors": [],
            "updatedNode": {"id": "12345", "title": "Test Card", "labels": []},
        }
    }

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_response)

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.update_card(card_id, field_updates=values)

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]

    assert variables["input"]["nodeId"] == card_id
    assert result == mock_response


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_card_incremental_mode_value_format_conversion():
    """Test update_card converts values to camelCase format with generatedByAi."""
    card_id = 12345
    values = [{"field_id": "field_1", "value": "New Value", "operation": "ADD"}]

    mock_response = {"updateFieldsValues": {"success": True, "userErrors": []}}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_response)

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    await client.update_card(card_id, field_updates=values)

    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]
    formatted_values = variables["input"]["values"]

    assert len(formatted_values) == 1
    assert formatted_values[0]["fieldId"] == "field_1"
    assert formatted_values[0]["value"] == "New Value"
    assert formatted_values[0]["operation"] == "ADD"
    assert formatted_values[0]["generatedByAi"] is True


# ============================================================================
# Regression tests for remaining public API methods (lock compatibility)
# ============================================================================


@pytest.mark.unit
def test_public_import_path_exports_pipefy_client():
    """Test public import path stays stable: from pipefy_mcp.services.pipefy import PipefyClient."""
    from pipefy_mcp.services.pipefy import PipefyClient as PublicPipefyClient

    assert PublicPipefyClient is PipefyClient


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_passes_pipe_id_variable():
    """Test get_pipe passes pipe_id under variable_values unchanged."""
    pipe_id = 303181849

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"pipe": {"id": str(pipe_id)}})

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.get_pipe(pipe_id)

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]
    assert variables == {"pipe_id": pipe_id}
    assert result == {"pipe": {"id": str(pipe_id)}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_members_calls_service():
    """Test get_pipe_members calls the pipe service with the correct pipe_id."""
    pipe_id = 123
    mock_members = [{"user": {"id": "1", "name": "Test User"}}]

    # Mock PipeService and its get_pipe_members method
    mock_pipe_service = MagicMock(spec=PipeService)
    mock_pipe_service.get_pipe_members = AsyncMock(return_value=mock_members)

    client = PipefyClient.__new__(PipefyClient)
    client._pipe_service = mock_pipe_service
    client._card_service = MagicMock(spec=CardService)  # Mock CardService as well

    # Call the method
    result = await client.get_pipe_members(pipe_id)

    # Assert that the service method was called with the correct argument
    mock_pipe_service.get_pipe_members.assert_called_once_with(pipe_id)
    assert result == mock_members


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_passes_card_id_variable():
    """Test get_card passes card_id under variable_values unchanged."""
    card_id = 12345

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={
            "card": {
                "id": str(card_id),
                "title": "Test Card",
                "current_phase": {"id": "1", "name": "Test Phase"},
                "pipe": {"id": "123", "name": "Test Pipe"},
            }
        }
    )

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.get_card(card_id)

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]
    assert variables == {"card_id": card_id, "includeFields": False}
    assert result == {
        "card": {
            "id": str(card_id),
            "title": "Test Card",
            "current_phase": {"id": "1", "name": "Test Phase"},
            "pipe": {"id": "123", "name": "Test Pipe"},
        }
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_none_search_sends_empty_search_dict():
    """Test get_cards sends an empty search object when search is None."""
    pipe_id = 303181849

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"cards": {"edges": []}})

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.get_cards(pipe_id, None)  # type: ignore[arg-type]

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]

    assert variables["pipe_id"] == pipe_id
    assert variables["search"] == {}
    assert result == {"cards": {"edges": []}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_search_dict_passes_search_as_is():
    """Test get_cards passes search dict unchanged when provided."""
    pipe_id = 303181849
    search = {"title": "Test"}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"cards": {"edges": []}})

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.get_cards(pipe_id, search)  # type: ignore[arg-type]

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]

    assert variables["pipe_id"] == pipe_id
    assert variables["search"] == search
    assert result == {"cards": {"edges": []}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_include_fields_true_passes_include_fields_to_service():
    """Test get_cards facade passes include_fields=True to CardService.get_cards."""
    pipe_id = 303181849
    expected = {"cards": {"edges": []}}

    card_service = AsyncMock()
    card_service.get_cards = AsyncMock(return_value=expected)

    client: PipefyClient = PipefyClient.__new__(PipefyClient)
    client._card_service = card_service
    client._pipe_service = MagicMock(spec=PipeService)

    result = await client.get_cards(
        pipe_id,
        search=None,
        include_fields=True,
    )

    card_service.get_cards.assert_awaited_once_with(pipe_id, None, include_fields=True)
    assert result == expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards_with_include_fields_false_passes_include_fields_to_service():
    """Test get_cards facade passes include_fields=False to CardService.get_cards."""
    pipe_id = 303181849
    expected = {"cards": {"edges": []}}

    card_service = AsyncMock()
    card_service.get_cards = AsyncMock(return_value=expected)

    client: PipefyClient = PipefyClient.__new__(PipefyClient)
    client._card_service = card_service
    client._pipe_service = MagicMock(spec=PipeService)

    result = await client.get_cards(
        pipe_id,
        search=None,
        include_fields=False,
    )

    card_service.get_cards.assert_awaited_once_with(pipe_id, None, include_fields=False)
    assert result == expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_card_comment_delegates_to_card_service_create_comment():
    """Test add_card_comment delegates unchanged to CardService.create_comment."""
    card_id = 12345
    text = "This is a comment"
    expected = {"createComment": {"comment": {"id": "c_987"}}}

    card_service = AsyncMock()
    card_service.create_comment = AsyncMock(return_value=expected)

    client: PipefyClient = PipefyClient.__new__(PipefyClient)
    client._card_service = card_service

    result = await client.add_card_comment(card_id, text)

    assert result == expected
    card_service.create_comment.assert_awaited_once_with(card_id, text)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_move_card_to_phase_variable_shape():
    """Test move_card_to_phase sends input with card_id and destination_phase_id."""
    card_id = 12345
    destination_phase_id = 678

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value={"moveCardToPhase": {"clientMutationId": None}}
    )

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client = _make_facade_client(mock_client)

    result = await client.move_card_to_phase(card_id, destination_phase_id)

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]

    assert variables == {
        "input": {"card_id": card_id, "destination_phase_id": destination_phase_id}
    }
    assert result == {"moveCardToPhase": {"clientMutationId": None}}


@pytest.mark.asyncio
async def test_search_pipes_delegates_to_pipe_service():
    """Test search_pipes delegates unchanged to PipeService.search_pipes."""
    pipe_name = "test pipe"
    expected = {"pipes": []}

    pipe_service = AsyncMock()
    pipe_service.search_pipes = AsyncMock(return_value=expected)

    client = PipefyClient.__new__(PipefyClient)
    client._pipe_service = pipe_service

    result = await client.search_pipes(pipe_name)

    pipe_service.search_pipes.assert_called_once_with(pipe_name)
    assert result == expected
