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
from pydantic import ValidationError

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.models.comment import MAX_COMMENT_TEXT_LENGTH, CommentInput
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools import pipe_tools
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
def client_session(mcp_server, request) -> ClientSession:
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


class _FakeGraphQLException(Exception):
    """Test helper: mimics a gql exception exposing `.errors` with `message` fields."""

    def __init__(self, message: str, errors: list[dict] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


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


# =============================================================================
# CommentInput Model Validation Tests
# =============================================================================


@pytest.mark.unit
@pytest.mark.parametrize("card_id", [0, -1, -999])
def test_comment_input_rejects_card_id_zero_or_negative(card_id: int):
    """CommentInput should reject card_id <= 0."""
    with pytest.raises(ValidationError):
        CommentInput(card_id=card_id, text="ok")


@pytest.mark.unit
@pytest.mark.parametrize("text", ["", "   ", "\n\t  "])
def test_comment_input_rejects_blank_or_whitespace_text(text: str):
    """CommentInput should reject blank/whitespace-only text."""
    with pytest.raises(ValidationError):
        CommentInput(card_id=1, text=text)


@pytest.mark.unit
def test_comment_input_rejects_text_over_max_length():
    """CommentInput should reject text longer than the maximum length."""
    too_long_text = "a" * (MAX_COMMENT_TEXT_LENGTH + 1)
    with pytest.raises(ValidationError):
        CommentInput(card_id=1, text=too_long_text)


@pytest.mark.unit
def test_comment_input_accepts_text_at_max_length_boundary():
    """CommentInput should accept text exactly at the max length boundary."""
    text = "a" * MAX_COMMENT_TEXT_LENGTH
    comment = CommentInput(card_id=1, text=text)
    assert comment.card_id == 1
    assert comment.text == text


@pytest.mark.unit
def test_comment_input_valid_input():
    """CommentInput should accept valid inputs."""
    comment = CommentInput(card_id=123, text="Hello world")
    assert comment.card_id == 123
    assert comment.text == "Hello world"


# =============================================================================
# Payload Builder Tests
# =============================================================================


@pytest.mark.unit
def test_build_add_card_comment_success_payload_contract_with_string_id():
    """Tool success payload must follow the public contract."""
    payload = pipe_tools.build_add_card_comment_success_payload(comment_id="c_987")
    assert payload == {"success": True, "comment_id": "c_987"}


@pytest.mark.unit
def test_build_add_card_comment_success_payload_stringifies_id():
    """Tool success payload should always expose comment_id as a string."""
    payload = pipe_tools.build_add_card_comment_success_payload(comment_id=123)  # type: ignore[arg-type]
    assert payload == {"success": True, "comment_id": "123"}


# =============================================================================
# Error Mapping Tests
# =============================================================================


@pytest.mark.unit
def test_map_add_card_comment_error_to_message_card_not_found():
    """GraphQL errors indicating missing/invalid card should map to a friendly message."""
    exc = _FakeGraphQLException(
        message="Record not found",
        errors=[{"message": "Card not found"}],
    )

    msg = pipe_tools.map_add_card_comment_error_to_message(exc)
    assert msg == "Card not found. Please verify 'card_id' and access permissions."


@pytest.mark.unit
def test_map_add_card_comment_error_to_message_permission_denied():
    """GraphQL errors indicating lack of permission should map to a friendly message."""
    exc = _FakeGraphQLException(
        message="You do not have permission to perform this action",
        errors=[{"message": "Not authorized"}],
    )

    msg = pipe_tools.map_add_card_comment_error_to_message(exc)
    assert msg == "You don't have permission to comment on this card."


@pytest.mark.unit
def test_map_add_card_comment_error_to_message_generic_fallback():
    """Unknown errors should map to a stable generic message (no raw details)."""
    exc = RuntimeError("socket hang up")

    msg = pipe_tools.map_add_card_comment_error_to_message(exc)
    assert msg == "Unexpected error while adding comment. Please try again."
