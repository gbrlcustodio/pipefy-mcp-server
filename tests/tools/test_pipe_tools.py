import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp.server.fastmcp import FastMCP
from mcp.server.elicitation import AcceptedElicitation, DeclinedElicitation
from pydantic import BaseModel

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.tools.pipe_tools import PipeTools


@pytest.fixture
def mock_pipefy_client():
    """Fixture to mock the PipefyClient."""
    return AsyncMock()


@pytest.fixture(autouse=True)
def services_container(mock_pipefy_client):
    """Fixture to provide a ServicesContainer with a mocked PipefyClient."""
    container = ServicesContainer.get_instance()
    container.pipefy_client = mock_pipefy_client
    return container


@pytest.fixture
def mcp_server():
    """Fixture to create a FastMCP server instance."""
    server = FastMCP("test-server")
    PipeTools.register(server)
    return server


class DummyModel(BaseModel):
    field1: str
    field2: int


@pytest.mark.skip(reason="Test is failing due to context issues, will be fixed later")
@pytest.mark.asyncio
async def test_create_card_elicitation_accepted(mcp_server, mock_pipefy_client):
    """Test the create_card tool when the user accepts the elicitation."""
    # Arrange
    mock_pipefy_client.get_start_form_fields.return_value = {
        "start_form_fields": [
            {"id": "field1", "type": "short_text", "required": True, "label": "Field 1"},
            {"id": "field2", "type": "number", "required": True, "label": "Field 2"},
        ]
    }

    mock_ctx = MagicMock()
    mock_ctx.elicit.return_value = AcceptedElicitation(
        data=DummyModel(field1="test", field2=123),
    )

    # Act
    await mcp_server.call_tool(name="create_card", arguments={"pipe_id": 123, "ctx": mock_ctx})

    # Assert
    mock_pipefy_client.get_start_form_fields.assert_called_once_with(123, False)
    mock_ctx.elicit.assert_called_once()
    mock_pipefy_client.create_card.assert_called_once_with(123, {"field1": "test", "field2": 123})


@pytest.mark.skip(reason="Test is failing due to context issues, will be fixed later")
@pytest.mark.asyncio
async def test_create_card_elicitation_rejected(mcp_server, mock_pipefy_client):
    """Test the create_card tool when the user rejects the elicitation."""
    # Arrange
    mock_pipefy_client.get_start_form_fields.return_value = {
        "start_form_fields": [
            {"id": "field1", "type": "short_text", "required": True, "label": "Field 1"},
        ]
    }

    mock_ctx = MagicMock()
    mock_ctx.elicit.return_value = DeclinedElicitation()

    # Act
    result = await mcp_server.call_tool(name="create_card", arguments={"pipe_id": 123, "ctx": mock_ctx})

    # Assert
    mock_pipefy_client.get_start_form_fields.assert_called_once_with(123, False)
    mock_ctx.elicit.assert_called_once()
    mock_pipefy_client.create_card.assert_not_called()
    assert result == {"error": "Card creation cancelled by user."}


@pytest.mark.asyncio
async def test_get_card(mcp_server, mock_pipefy_client):
    """Test the get_card tool."""
    # Arrange
    tool = mcp_server._tool_manager.get_tool("get_card")

    # Act
    await tool.fn(card_id=456)

    # Assert
    mock_pipefy_client.get_card.assert_called_once_with(456)


@pytest.mark.asyncio
async def test_get_cards(mcp_server, mock_pipefy_client):
    """Test the get_cards tool."""
    # Arrange
    tool = mcp_server._tool_manager.get_tool("get_cards")

    # Act
    await tool.fn(pipe_id=123, search={"status": "open"})

    # Assert
    mock_pipefy_client.get_cards.assert_called_once_with(123, {"status": "open"})


@pytest.mark.asyncio
async def test_get_pipe(mcp_server, mock_pipefy_client):
    """Test the get_pipe tool."""
    # Arrange
    tool = mcp_server._tool_manager.get_tool("get_pipe")

    # Act
    await tool.fn(pipe_id=123)

    # Assert
    mock_pipefy_client.get_pipe.assert_called_once_with(123)


@pytest.mark.asyncio
async def test_move_card_to_phase(mcp_server, mock_pipefy_client):
    """Test the move_card_to_phase tool."""
    # Arrange
    tool = mcp_server._tool_manager.get_tool("move_card_to_phase")

    # Act
    await tool.fn(card_id=456, destination_phase_id=789)

    # Assert
    mock_pipefy_client.move_card_to_phase.assert_called_once_with(456, 789)


@pytest.mark.asyncio
async def test_update_card_field(mcp_server, mock_pipefy_client):
    """Test the update_card_field tool."""
    # Arrange
    tool = mcp_server._tool_manager.get_tool("update_card_field")

    # Act
    await tool.fn(card_id=456, field_id="my_field", new_value="new value")

    # Assert
    mock_pipefy_client.update_card_field.assert_called_once_with(456, "my_field", "new value")


@pytest.mark.asyncio
async def test_update_card(mcp_server, mock_pipefy_client):
    """Test the update_card tool."""
    # Arrange
    tool = mcp_server._tool_manager.get_tool("update_card")

    # Act
    await tool.fn(card_id=456, title="New Title")

    # Assert
    mock_pipefy_client.update_card.assert_called_once_with(card_id=456, title="New Title", assignee_ids=None, label_ids=None, due_date=None, field_updates=None)


@pytest.mark.asyncio
async def test_get_start_form_fields(mcp_server, mock_pipefy_client):
    """Test the get_start_form_fields tool."""
    # Arrange
    tool = mcp_server._tool_manager.get_tool("get_start_form_fields")

    # Act
    await tool.fn(pipe_id=123, required_only=True)

    # Assert
    mock_pipefy_client.get_start_form_fields.assert_called_once_with(123, True)