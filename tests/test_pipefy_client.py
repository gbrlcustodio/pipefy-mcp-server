import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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
    assert variables["fields"][0] == {"field_id": "title", "field_value": "Teste-MCP"}
    assert variables["fields"][1] == {"field_id": "description", "field_value": "Test description"}
    
    # Verify result
    assert result == {"createCard": {"card": {"id": "12345"}}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_with_array_fields(mocker):
    """Test create_card works with already formatted array fields."""
    pipe_id = 303181849
    fields_array = [
        {"field_id": "title", "field_value": "Teste-MCP"},
        {"field_id": "description", "field_value": "Test description"}
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
    
    # Check that fields array was used as-is
    variables = call_args[1]["variable_values"]
    assert variables["pipe_id"] == pipe_id
    assert variables["fields"] == fields_array
    
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
    assert variables["fields"][0] == {"field_id": "title", "field_value": "Teste-MCP"}
    
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
            "help": None
        },
        {
            "id": "priority",
            "label": "Priority",
            "type": "select",
            "required": False,
            "editable": True,
            "options": ["Low", "Medium", "High"],
            "description": None,
            "help": "Select the priority level"
        }
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
            "help": None
        },
        {
            "id": "priority",
            "label": "Priority",
            "type": "select",
            "required": False,
            "editable": True,
            "options": ["Low", "Medium", "High"],
            "description": None,
            "help": None
        },
        {
            "id": "due_date",
            "label": "Due Date",
            "type": "date",
            "required": True,
            "editable": True,
            "options": None,
            "description": None,
            "help": None
        }
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
    mock_session.execute = AsyncMock(
        return_value={"pipe": {"start_form_fields": []}}
    )
    
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
            "help": None
        },
        {
            "id": "notes",
            "label": "Notes",
            "type": "long_text",
            "required": False,
            "editable": True,
            "options": None,
            "description": None,
            "help": None
        }
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

