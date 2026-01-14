import json
from datetime import timedelta
from random import randint
from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from mcp import ClientSession
from mcp.server.fastmcp import FastMCP
from mcp.shared.context import RequestContext
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from mcp.types import (
    ElicitRequestParams,
    ElicitResult,
)
from typing_extensions import TypedDict

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.pipe_tools import PipeTools

# =============================================================================
# Delete Card Tool Test Types
# =============================================================================


class DeleteCardPreviewPayload(TypedDict):
    preview: Literal[True]
    card_id: int
    card_title: str
    pipe_name: str
    message: str


class DeleteCardSuccessPayload(TypedDict):
    success: Literal[True]
    message: str


class DeleteCardErrorPayload(TypedDict):
    success: Literal[False]
    error: str


DeleteCardPayload = DeleteCardPreviewPayload | DeleteCardSuccessPayload | DeleteCardErrorPayload

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mcp_server(mock_pipefy_client):
    mcp = FastMCP("Pipefy MCP Test Server")
    PipeTools.register(mcp, mock_pipefy_client)

    return mcp


@pytest.fixture
def mock_pipefy_client():
    client = MagicMock(PipefyClient)
    client.get_start_form_fields = AsyncMock()
    client.create_card = AsyncMock()
    client.add_card_comment = AsyncMock(
        return_value={"createComment": {"comment": {"id": "c_987"}}}
    )
    client.get_card = AsyncMock()
    client.delete_card = AsyncMock()

    return client


@pytest.fixture(autouse=True)
def mock_services_container(mocker, mock_pipefy_client):
    container = Mock(ServicesContainer)
    container.pipefy_client = mock_pipefy_client

    return mocker.patch(
        "pipefy_mcp.core.container.ServicesContainer.get_instance",
        return_value=container,
    )


@pytest.fixture
def client_session(mcp_server, request):
    return create_client_session(
        mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=request.param,
    )


@pytest.fixture
def pipe_id() -> int:
    return randint(1, 10000)


def elicitation_callback_for(action, content=None):
    async def callback(
        context: RequestContext[ClientSession, Any],
        params: ElicitRequestParams,
    ) -> ElicitResult:
        return ElicitResult(action=action, content=content)

    return callback


# =============================================================================
# Test Helpers
# =============================================================================


def _extract_call_tool_payload(result) -> dict:
    """Extract tool payload from CallToolResult across MCP SDK versions."""
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        if isinstance(structured, dict) and "result" in structured:
            payload = structured.get("result")
            if isinstance(payload, dict):
                return payload
        if isinstance(structured, dict):
            return structured

    content = getattr(result, "content", None) or []
    for item in content:
        if getattr(item, "type", None) == "text":
            text = getattr(item, "text", "")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload

    raise AssertionError("Could not extract tool payload from CallToolResult")


# =============================================================================
# create_card Tool Tests
# =============================================================================


@pytest.mark.anyio
@pytest.mark.parametrize(
    "client_session",
    [elicitation_callback_for(action="accept", content={"confirm": True})],
    indirect=True,
)
async def test_create_card_tool_with_elicitation(
    client_session,
    mock_pipefy_client,
    pipe_id,
):
    mock_pipefy_client.get_start_form_fields.return_value = {"start_form_fields": []}
    mock_pipefy_client.create_card.return_value = {
        "createCard": {"card": {"id": "789"}}
    }

    async with client_session as session:
        result = await session.call_tool("create_card", {"pipe_id": pipe_id})
        assert result.isError is False, "Unexpected tool result"
        mock_pipefy_client.create_card.assert_called_once_with(pipe_id, {})
        response = json.loads(result.content[0].text)
        expected_response = {
            "createCard": {"card": {"id": "789"}},
            "card_link": (
                "[https://app.pipefy.com/open-cards/789](https://app.pipefy.com/open-cards/789)"
            ),
        }
        assert response == expected_response


@pytest.mark.anyio
@pytest.mark.parametrize(
    "client_session",
    [elicitation_callback_for(action="decline")],
    indirect=True,
)
async def test_create_card_tool_with_elicitation_declined(
    client_session,
    mock_pipefy_client,
    pipe_id,
):
    mock_pipefy_client.get_start_form_fields.return_value = {"start_form_fields": []}
    mock_pipefy_client.create_card.return_value = {
        "createCard": {"card": {"id": "789"}}
    }

    async with client_session as session:
        result = await session.call_tool("create_card", {"pipe_id": pipe_id})
        assert result.isError is False, "Unexpected tool result"
        mock_pipefy_client.create_card.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("client_session", [None], indirect=True)
async def test_create_card_tool_without_elicitation(
    client_session,
    mock_pipefy_client,
    pipe_id,
):
    mock_pipefy_client.get_start_form_fields.return_value = {
        "start_form_fields": ["field_1", "field_2"]
    }
    mock_pipefy_client.create_card.return_value = {
        "createCard": {"card": {"id": "789"}}
    }

    async with client_session as session:
        result = await session.call_tool(
            "create_card",
            {
                "pipe_id": pipe_id,
                "fields": {"field_1": "value_1", "field_2": "value_2"},
            },
        )
        assert result.isError is False, "Unexpected tool result"
        mock_pipefy_client.create_card.assert_called_once_with(
            pipe_id, {"field_1": "value_1", "field_2": "value_2"}
        )
        response = json.loads(result.content[0].text)
        expected_response = {
            "createCard": {"card": {"id": "789"}},
            "card_link": (
                "[https://app.pipefy.com/open-cards/789](https://app.pipefy.com/open-cards/789)"
            ),
        }
        assert response == expected_response


# =============================================================================
# get_pipe_members Tool Tests
# =============================================================================


@pytest.mark.anyio
@pytest.mark.parametrize("client_session", [None], indirect=True)
async def test_get_pipe_members_tool(client_session, mock_pipefy_client, pipe_id):
    async with client_session as session:
        mock_pipefy_client.get_pipe_members = AsyncMock(
            return_value={"pipe": {"members": []}}
        )
        result = await session.call_tool("get_pipe_members", {"pipe_id": pipe_id})

        assert result.isError is False, "Unexpected tool result"
        mock_pipefy_client.get_pipe_members.assert_called_once_with(pipe_id)


# =============================================================================
# add_card_comment Tool Tests
# =============================================================================


@pytest.mark.anyio
@pytest.mark.parametrize("client_session", [None], indirect=True)
async def test_add_card_comment_tool_success(
    client_session,
    mock_pipefy_client,
):
    async with client_session as session:
        result = await session.call_tool(
            "add_card_comment",
            {"card_id": 123, "text": "hello"},
        )

        assert result.isError is False
        mock_pipefy_client.add_card_comment.assert_called_once_with(
            card_id=123, text="hello"
        )
        payload = _extract_call_tool_payload(result)
        assert payload == {"success": True, "comment_id": "c_987"}


@pytest.mark.anyio
@pytest.mark.parametrize("client_session", [None], indirect=True)
async def test_add_card_comment_tool_invalid_input_returns_error_payload(
    client_session,
    mock_pipefy_client,
):
    async with client_session as session:
        result = await session.call_tool(
            "add_card_comment",
            {"card_id": 0, "text": "hello"},
        )

        assert result.isError is False  # Tool returns error payload, not exception
        mock_pipefy_client.add_card_comment.assert_not_called()
        payload = _extract_call_tool_payload(result)
        assert payload == {
            "success": False,
            "error": "Invalid input. Please provide a valid 'card_id' and non-empty 'text'.",
        }


@pytest.mark.anyio
@pytest.mark.parametrize("client_session", [None], indirect=True)
async def test_delete_card_tool_confirm_false_returns_preview(
    client_session,
    mock_pipefy_client,
):
    """Test delete_card tool with confirm=False returns preview without deletion."""
    # Setup mock responses
    mock_pipefy_client.get_card.return_value = {
        "card": {
            "id": "12345",
            "title": "Test Card",
            "pipe": {"name": "Test Pipe"}
        }
    }

    async with client_session as session:
        result = await session.call_tool(
            "delete_card",
            {"card_id": 12345, "confirm": False},
        )

        assert result.isError is False
        # Should fetch card for preview but not delete
        mock_pipefy_client.get_card.assert_called_once_with(12345)
        mock_pipefy_client.delete_card.assert_not_called()

        payload = _extract_call_tool_payload(result)
        expected_payload: DeleteCardPreviewPayload = {
            "success": False,
            "requires_confirmation": True,
            "card_id": 12345,
            "card_title": "Test Card",
            "pipe_name": "Test Pipe",
            "message": "⚠️ You are about to permanently delete card 'Test Card' (ID: 12345) from pipe 'Test Pipe'. This action is irreversible. Set 'confirm=True' to proceed.",
        }
        assert payload == expected_payload


@pytest.mark.anyio
@pytest.mark.parametrize("client_session", [None], indirect=True)
async def test_delete_card_tool_invalid_card_id_returns_error(
    client_session,
    mock_pipefy_client,
):
    """Test delete_card tool with invalid card_id returns error payload."""
    async with client_session as session:
        result = await session.call_tool(
            "delete_card",
            {"card_id": 0, "confirm": True},
        )

        assert result.isError is False
        # Should not call any client methods for invalid input
        mock_pipefy_client.get_card.assert_not_called()
        mock_pipefy_client.delete_card.assert_not_called()

        payload = _extract_call_tool_payload(result)
        expected_payload: DeleteCardErrorPayload = {
            "success": False,
            "error": "Invalid 'card_id'. Please provide a positive integer.",
        }
        assert payload == expected_payload


@pytest.mark.anyio
@pytest.mark.parametrize("client_session", [None], indirect=True)
async def test_delete_card_tool_resource_not_found_error_mapping(
    client_session,
    mock_pipefy_client,
):
    """Test delete_card tool maps RESOURCE_NOT_FOUND GraphQL exception to friendly message."""
    # Simulate GraphQL exception with RESOURCE_NOT_FOUND code
    from gql.transport.exceptions import TransportQueryError
    
    error = TransportQueryError(
        "GraphQL Error",
        errors=[{
            "message": "Card not found",
            "extensions": {"code": "RESOURCE_NOT_FOUND"}
        }]
    )
    mock_pipefy_client.get_card.side_effect = error

    async with client_session as session:
        result = await session.call_tool(
            "delete_card",
            {"card_id": 99999, "confirm": True},
        )

        assert result.isError is False
        mock_pipefy_client.get_card.assert_called_once_with(99999)
        mock_pipefy_client.delete_card.assert_not_called()

        payload = _extract_call_tool_payload(result)
        expected_payload: DeleteCardErrorPayload = {
            "success": False,
            "error": "Card with ID 99999 not found. Verify the card exists and you have access permissions.",
        }
        assert payload == expected_payload


@pytest.mark.anyio
@pytest.mark.parametrize("client_session", [None], indirect=True)
async def test_delete_card_tool_permission_denied_error_mapping(
    client_session,
    mock_pipefy_client,
):
    """Test delete_card tool maps PERMISSION_DENIED GraphQL exception to friendly message."""
    # Simulate GraphQL exception with PERMISSION_DENIED code
    from gql.transport.exceptions import TransportQueryError
    
    mock_pipefy_client.get_card.return_value = {
        "card": {
            "id": "12345",
            "title": "Test Card",
            "pipe": {"name": "Test Pipe"},
        }
    }
    
    error = TransportQueryError(
        "GraphQL Error",
        errors=[{
            "message": "Permission denied",
            "extensions": {"code": "PERMISSION_DENIED"}
        }]
    )
    mock_pipefy_client.delete_card.side_effect = error

    async with client_session as session:
        result = await session.call_tool(
            "delete_card",
            {"card_id": 12345, "confirm": True},
        )

        assert result.isError is False
        mock_pipefy_client.delete_card.assert_called_once_with(12345)

        payload = _extract_call_tool_payload(result)
        expected_payload: DeleteCardErrorPayload = {
            "success": False,
            "error": "You don't have permission to delete card 12345. Please check your access permissions.",
        }
        assert payload == expected_payload


@pytest.mark.anyio
@pytest.mark.parametrize("client_session", [None], indirect=True)
async def test_delete_card_tool_deletion_fails_with_success_false(
    client_session,
    mock_pipefy_client,
):
    """Test delete_card tool handles API returning success=False."""
    mock_pipefy_client.get_card.return_value = {
        "card": {
            "id": "12345",
            "title": "Test Card",
            "pipe": {"name": "Test Pipe"},
        }
    }
    # API returns success: False without throwing exception
    mock_pipefy_client.delete_card.return_value = {
        "deleteCard": {"success": False}
    }

    async with client_session as session:
        result = await session.call_tool(
            "delete_card",
            {"card_id": 12345, "confirm": True},
        )

        assert result.isError is False
        mock_pipefy_client.delete_card.assert_called_once_with(12345)

        payload = _extract_call_tool_payload(result)
        expected_payload: DeleteCardErrorPayload = {
            "success": False,
            "error": "Failed to delete card 'Test Card' (ID: 12345). Please try again or contact support.",
        }
        assert payload == expected_payload


@pytest.mark.anyio
@pytest.mark.parametrize("client_session", [None], indirect=True)
async def test_delete_card_tool_confirm_true_executes_deletion(
    client_session,
    mock_pipefy_client,
):
    """Test delete_card tool with confirm=True executes deletion."""
    # Setup mock responses for both get_card and delete_card
    mock_pipefy_client.get_card.return_value = {
        "card": {
            "id": "12345",
            "title": "Test Card",
            "pipe": {"name": "Test Pipe"}
        }
    }
    mock_pipefy_client.delete_card.return_value = {
        "deleteCard": {"success": True}
    }

    async with client_session as session:
        result = await session.call_tool(
            "delete_card",
            {"card_id": 12345, "confirm": True},
        )

        assert result.isError is False
        # Should execute deletion
        mock_pipefy_client.delete_card.assert_called_once_with(12345)

        payload = _extract_call_tool_payload(result)
        expected_payload: DeleteCardSuccessPayload = {
            "success": True,
            "card_id": 12345,
            "card_title": "Test Card",
            "pipe_name": "Test Pipe",
            "message": "Card 'Test Card' (ID: 12345) from pipe 'Test Pipe' has been permanently deleted.",
        }
        assert payload == expected_payload
