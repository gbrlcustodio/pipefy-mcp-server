from unittest.mock import AsyncMock, MagicMock

import pytest
from gql import Client

from pipefy_mcp.services.pipefy.client import PipefyClient


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_with_dict_fields(mocker):
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

    # Create client instance and mock the _create_client method
    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

    # Execute create_card
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
async def test_create_card_with_array_fields(mocker):
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

    # Create client instance and mock the _create_client method
    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

    # Execute create_card
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
async def test_create_card_with_empty_dict(mocker):
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

    # Create client instance and mock the _create_client method
    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

    # Execute create_card
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
async def test_create_card_with_single_field(mocker):
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

    # Create client instance and mock the _create_client method
    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

    # Execute create_card
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

    # Create client instance
    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

    # Execute get_start_form_fields
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

    # Create client instance
    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

    # Execute get_start_form_fields with required_only=True
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

    # Create client instance
    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

    # Execute get_start_form_fields
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

    # Create client instance
    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

    # Execute get_start_form_fields with required_only=True
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

    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

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

    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

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
        {"field_id": "field_2", "value": "Value 2"}
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

    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

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

    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

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

    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

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

    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

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

    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

    await client.update_card(card_id, field_updates=values)

    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]
    formatted_values = variables["input"]["values"]

    assert len(formatted_values) == 1
    assert formatted_values[0]["fieldId"] == "field_1"
    assert formatted_values[0]["value"] == "New Value"
    assert formatted_values[0]["operation"] == "ADD"
    assert formatted_values[0]["generatedByAi"] is True


@pytest.mark.unit
def test_convert_values_to_camel_case_missing_field_id():
    """Test _convert_values_to_camel_case raises ValueError when field_id is missing."""
    client = PipefyClient.__new__(PipefyClient)

    values = [{"value": "test"}]  # Missing field_id
    with pytest.raises(ValueError, match="missing required 'field_id' key"):
        client._convert_values_to_camel_case(values)


@pytest.mark.unit
def test_convert_values_to_camel_case_missing_value():
    """Test _convert_values_to_camel_case raises ValueError when value is missing."""
    client = PipefyClient.__new__(PipefyClient)

    values = [{"field_id": "test"}]  # Missing value
    with pytest.raises(ValueError, match="missing required 'value' key"):
        client._convert_values_to_camel_case(values)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe():
    """Test get_pipe queries for a pipe by ID."""
    pipe_id = 123
    mock_response = {"pipe": {"id": "123", "name": "Test Pipe"}}
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_response)
    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

    result = await client.get_pipe(pipe_id)

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]
    assert variables["pipe_id"] == pipe_id
    assert result == mock_response


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card():
    """Test get_card queries for a card by ID."""
    card_id = 456
    mock_response = {"card": {"id": "456", "title": "Test Card"}}
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_response)
    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

    result = await client.get_card(card_id)

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]
    assert variables["card_id"] == card_id
    assert result == mock_response


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_cards():
    """Test get_cards queries for cards in a pipe."""
    pipe_id = 123
    search_params = {"assignee_ids": [1]}
    mock_response = {"cards": {"edges": []}}
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_response)
    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

    result = await client.get_cards(pipe_id, search_params)

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]
    assert variables["pipe_id"] == pipe_id
    assert variables["search"] == search_params
    assert result == mock_response


@pytest.mark.unit
@pytest.mark.asyncio
async def test_move_card_to_phase():
    """Test move_card_to_phase moves a card to a new phase."""
    card_id = 456
    destination_phase_id = 789
    mock_response = {"moveCardToPhase": {"clientMutationId": None}}
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_response)
    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    client = PipefyClient.__new__(PipefyClient)
    client.client = mock_client

    result = await client.move_card_to_phase(card_id, destination_phase_id)

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    variables = call_args[1]["variable_values"]
    assert variables["input"]["card_id"] == card_id
    assert variables["input"]["destination_phase_id"] == destination_phase_id
    assert result == mock_response

