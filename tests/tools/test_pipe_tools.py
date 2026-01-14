import json
from datetime import timedelta
from random import randint
from typing import Any
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

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.pipe_tools import PipeTools

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
