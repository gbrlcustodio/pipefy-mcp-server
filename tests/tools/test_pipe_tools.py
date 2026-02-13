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
from pipefy_mcp.tools.pipe_tool_helpers import (
    FIND_CARDS_EMPTY_MESSAGE,
    DeleteCardErrorPayload,
    DeleteCardSuccessPayload,
)
from pipefy_mcp.tools.pipe_tools import FIND_CARDS_RESPONSE_KEY, PipeTools

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
    client.update_comment = AsyncMock(
        return_value={"updateComment": {"comment": {"id": "c_999"}}}
    )
    client.delete_comment = AsyncMock(return_value={"deleteComment": {"success": True}})
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


def elicitation_callback_raises(exc=None):
    """Return an elicitation callback that raises the given exception (for testing error paths)."""
    _exc = exc if exc is not None else RuntimeError("elicit failed")

    async def callback(
        context: RequestContext[ClientSession, Any],
        params: ElicitRequestParams,
    ) -> ElicitResult:
        raise _exc

    return callback


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


@pytest.mark.anyio
class TestCreateCardTool:
    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="accept", content={"confirm": True})],
        indirect=True,
    )
    async def test_with_elicitation(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
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

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="decline")],
        indirect=True,
    )
    async def test_with_elicitation_declined(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "789"}}
        }

        async with client_session as session:
            result = await session.call_tool("create_card", {"pipe_id": pipe_id})
            assert result.isError is False, "Unexpected tool result"
            mock_pipefy_client.create_card.assert_not_called()

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_without_elicitation(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": [
                {
                    "id": "field_1",
                    "label": "Field 1",
                    "type": "short_text",
                    "required": True,
                    "editable": True,
                },
                {
                    "id": "field_2",
                    "label": "Field 2",
                    "type": "short_text",
                    "required": True,
                    "editable": True,
                },
            ]
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

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_without_elicitation_filters_non_editable_fields(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": [
                {
                    "id": "field_1",
                    "label": "Field 1",
                    "type": "short_text",
                    "required": True,
                    "editable": True,
                },
                {
                    "id": "field_2",
                    "label": "Field 2",
                    "type": "short_text",
                    "required": False,
                    "editable": False,
                },
            ]
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
                pipe_id, {"field_1": "value_1"}
            )


@pytest.mark.anyio
class TestGetPipeMembersTool:
    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_returns_members(self, client_session, mock_pipefy_client, pipe_id):
        async with client_session as session:
            mock_pipefy_client.get_pipe_members = AsyncMock(
                return_value={"pipe": {"members": []}}
            )
            result = await session.call_tool("get_pipe_members", {"pipe_id": pipe_id})

            assert result.isError is False, "Unexpected tool result"
            mock_pipefy_client.get_pipe_members.assert_called_once_with(pipe_id)


@pytest.mark.anyio
class TestDirectToolCalls:
    """Direct tests for tools that simply forward params to the client."""

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_card_forwards_params_to_client(
        self, client_session, mock_pipefy_client
    ):
        """get_card tool forwards card_id and include_fields to client."""
        mock_pipefy_client.get_card = AsyncMock(
            return_value={"card": {"id": "123", "title": "A Card"}}
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_card", {"card_id": 123, "include_fields": True}
            )
        assert result.isError is False
        mock_pipefy_client.get_card.assert_called_once_with(123, include_fields=True)
        payload = _extract_call_tool_payload(result)
        assert payload["card"]["id"] == "123"

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_pipe_forwards_pipe_id_to_client(
        self, client_session, mock_pipefy_client, pipe_id
    ):
        """get_pipe tool forwards pipe_id to client."""
        mock_pipefy_client.get_pipe = AsyncMock(
            return_value={"pipe": {"id": pipe_id, "name": "My Pipe"}}
        )
        async with client_session as session:
            result = await session.call_tool("get_pipe", {"pipe_id": pipe_id})
        assert result.isError is False
        mock_pipefy_client.get_pipe.assert_called_once_with(pipe_id)
        payload = _extract_call_tool_payload(result)
        assert payload["pipe"]["name"] == "My Pipe"

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_move_card_to_phase_forwards_params_to_client(
        self, client_session, mock_pipefy_client
    ):
        """move_card_to_phase tool forwards card_id and destination_phase_id to client."""
        mock_pipefy_client.move_card_to_phase = AsyncMock(
            return_value={"moveCardToPhase": {"card": {"id": "1"}}}
        )
        async with client_session as session:
            result = await session.call_tool(
                "move_card_to_phase",
                {"card_id": 100, "destination_phase_id": 200},
            )
        assert result.isError is False
        mock_pipefy_client.move_card_to_phase.assert_called_once_with(100, 200)

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_start_form_fields_forwards_params_to_client(
        self, client_session, mock_pipefy_client, pipe_id
    ):
        """get_start_form_fields tool forwards pipe_id and required_only to client."""
        mock_pipefy_client.get_start_form_fields = AsyncMock(
            return_value={"start_form_fields": [{"id": "title", "label": "Title"}]}
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_start_form_fields",
                {"pipe_id": pipe_id, "required_only": True},
            )
        assert result.isError is False
        mock_pipefy_client.get_start_form_fields.assert_called_once_with(pipe_id, True)
        payload = _extract_call_tool_payload(result)
        assert "start_form_fields" in payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_comment_success(
        self,
        client_session,
        mock_pipefy_client,
    ):
        """update_comment with valid input returns success payload with comment_id."""
        async with client_session as session:
            result = await session.call_tool(
                "update_comment",
                {"comment_id": 456, "text": "Updated text"},
            )
        assert result.isError is False
        mock_pipefy_client.update_comment.assert_called_once_with(456, "Updated text")
        payload = _extract_call_tool_payload(result)
        assert payload == {"success": True, "comment_id": "c_999"}

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_comment_invalid_comment_id_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
    ):
        """update_comment with comment_id <= 0 returns error payload without calling API."""
        async with client_session as session:
            result = await session.call_tool(
                "update_comment",
                {"comment_id": 0, "text": "hello"},
            )
        assert result.isError is False
        mock_pipefy_client.update_comment.assert_not_called()
        payload = _extract_call_tool_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_comment_blank_text_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
    ):
        """update_comment with blank text returns error payload without calling API."""
        async with client_session as session:
            result = await session.call_tool(
                "update_comment",
                {"comment_id": 1, "text": "   "},
            )
        assert result.isError is False
        mock_pipefy_client.update_comment.assert_not_called()
        payload = _extract_call_tool_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_comment_text_over_max_length_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
    ):
        """update_comment with text > 1000 chars returns error payload without calling API."""
        from pipefy_mcp.models.comment import MAX_COMMENT_TEXT_LENGTH

        async with client_session as session:
            result = await session.call_tool(
                "update_comment",
                {"comment_id": 1, "text": "a" * (MAX_COMMENT_TEXT_LENGTH + 1)},
            )
        assert result.isError is False
        mock_pipefy_client.update_comment.assert_not_called()
        payload = _extract_call_tool_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_comment_api_exception_returns_mapped_error_payload(
        self,
        client_session,
        mock_pipefy_client,
    ):
        """When update_comment API raises, tool returns error payload with friendly message."""
        from gql.transport.exceptions import TransportQueryError

        mock_pipefy_client.update_comment.side_effect = TransportQueryError(
            "GraphQL Error",
            errors=[
                {"message": "Comment not found", "extensions": {"code": "NOT_FOUND"}}
            ],
        )
        async with client_session as session:
            result = await session.call_tool(
                "update_comment",
                {"comment_id": 99999, "text": "hello"},
            )
        assert result.isError is False
        mock_pipefy_client.update_comment.assert_called_once_with(99999, "hello")
        payload = _extract_call_tool_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert "comment" in payload["error"].lower() or "comment_id" in payload["error"]

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_delete_comment_success(
        self,
        client_session,
        mock_pipefy_client,
    ):
        """delete_comment with valid comment_id returns success payload."""
        async with client_session as session:
            result = await session.call_tool(
                "delete_comment",
                {"comment_id": 456},
            )
        assert result.isError is False
        mock_pipefy_client.delete_comment.assert_called_once_with(456)
        payload = _extract_call_tool_payload(result)
        assert payload == {"success": True}

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_delete_comment_invalid_comment_id_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
    ):
        """delete_comment with comment_id <= 0 returns error payload without calling API."""
        async with client_session as session:
            result = await session.call_tool(
                "delete_comment",
                {"comment_id": 0},
            )
        assert result.isError is False
        mock_pipefy_client.delete_comment.assert_not_called()
        payload = _extract_call_tool_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_delete_comment_api_exception_returns_mapped_error_payload(
        self,
        client_session,
        mock_pipefy_client,
    ):
        """When delete_comment API raises, tool returns error payload with friendly message."""
        from gql.transport.exceptions import TransportQueryError

        mock_pipefy_client.delete_comment.side_effect = TransportQueryError(
            "GraphQL Error",
            errors=[
                {
                    "message": "Permission denied",
                    "extensions": {"code": "PERMISSION_DENIED"},
                }
            ],
        )
        async with client_session as session:
            result = await session.call_tool(
                "delete_comment",
                {"comment_id": 12345},
            )
        assert result.isError is False
        mock_pipefy_client.delete_comment.assert_called_once_with(12345)
        payload = _extract_call_tool_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert "permission" in payload["error"].lower()

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_delete_comment_comment_not_found_returns_mapped_error_payload(
        self,
        client_session,
        mock_pipefy_client,
    ):
        """When delete_comment API returns not found, tool returns friendly error payload."""
        from gql.transport.exceptions import TransportQueryError

        mock_pipefy_client.delete_comment.side_effect = TransportQueryError(
            "GraphQL Error",
            errors=[{"message": "Record not found", "extensions": {}}],
        )
        async with client_session as session:
            result = await session.call_tool(
                "delete_comment",
                {"comment_id": 99999},
            )
        assert result.isError is False
        mock_pipefy_client.delete_comment.assert_called_once_with(99999)
        payload = _extract_call_tool_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert "comment" in payload["error"].lower() or "not found" in payload["error"]


@pytest.mark.anyio
class TestGetCardsTool:
    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_cards_with_include_fields_true_passes_to_client(
        self, client_session, mock_pipefy_client, pipe_id
    ):
        """Integration test: get_cards tool with include_fields=True calls client with include_fields=True."""
        mock_pipefy_client.get_cards = AsyncMock(
            return_value={"cards": {"edges": [{"node": {"id": "1", "title": "Card"}}]}}
        )

        async with client_session as session:
            result = await session.call_tool(
                "get_cards",
                {"pipe_id": pipe_id, "include_fields": True},
            )

        assert result.isError is False, "Unexpected tool error"
        mock_pipefy_client.get_cards.assert_called_once_with(
            pipe_id, None, include_fields=True
        )


@pytest.mark.anyio
class TestFindCardsTool:
    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_find_cards_forwards_params_to_client(
        self, client_session, mock_pipefy_client, pipe_id
    ):
        """Integration test: find_cards tool forwards pipe_id, field_id, field_value, include_fields to client."""
        mock_pipefy_client.find_cards = AsyncMock(
            return_value={
                FIND_CARDS_RESPONSE_KEY: {
                    "edges": [{"node": {"id": "1", "title": "Card"}}]
                }
            }
        )
        field_id = "status"
        field_value = "In Progress"

        async with client_session as session:
            result = await session.call_tool(
                "find_cards",
                {
                    "pipe_id": pipe_id,
                    "field_id": field_id,
                    "field_value": field_value,
                    "include_fields": True,
                },
            )

        assert result.isError is False, "Unexpected tool error"
        mock_pipefy_client.find_cards.assert_called_once_with(
            pipe_id, field_id, field_value, include_fields=True
        )
        payload = _extract_call_tool_payload(result)
        assert FIND_CARDS_RESPONSE_KEY in payload
        assert payload[FIND_CARDS_RESPONSE_KEY]["edges"]

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_find_cards_empty_edges_includes_message(
        self, client_session, mock_pipefy_client, pipe_id
    ):
        """When findCards returns empty edges, tool response includes FIND_CARDS_EMPTY_MESSAGE."""
        mock_pipefy_client.find_cards = AsyncMock(
            return_value={FIND_CARDS_RESPONSE_KEY: {"edges": []}}
        )

        async with client_session as session:
            result = await session.call_tool(
                "find_cards",
                {
                    "pipe_id": pipe_id,
                    "field_id": "field_1",
                    "field_value": "Value 1",
                },
            )

        assert result.isError is False
        payload = _extract_call_tool_payload(result)
        assert payload.get("message") == FIND_CARDS_EMPTY_MESSAGE
        assert payload.get(FIND_CARDS_RESPONSE_KEY, {}).get("edges") == []


@pytest.mark.anyio
class TestAddCardCommentTool:
    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_success(
        self,
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

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_invalid_input_returns_error_payload(
        self,
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

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_api_exception_returns_mapped_error_payload(
        self,
        client_session,
        mock_pipefy_client,
    ):
        """When add_card_comment API raises, tool returns error payload with mapped message."""
        from gql.transport.exceptions import TransportQueryError

        mock_pipefy_client.add_card_comment.side_effect = TransportQueryError(
            "GraphQL Error",
            errors=[
                {
                    "message": "Record not found",
                    "extensions": {"code": "RESOURCE_NOT_FOUND"},
                }
            ],
        )
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
        assert payload["success"] is False
        assert "error" in payload
        assert "Card not found" in payload["error"] or "card_id" in payload["error"]


@pytest.mark.anyio
class TestGetPhaseFieldsTool:
    @pytest.mark.parametrize(
        "client_session,required_only",
        [
            (None, False),
            (None, True),
        ],
        indirect=["client_session"],
    )
    async def test_returns_phase_fields(
        self, client_session, mock_pipefy_client, required_only
    ):
        phase_id = 12345
        mock_fields = [
            {"id": "status", "label": "Status", "type": "select", "required": True},
            {"id": "notes", "label": "Notes", "type": "long_text", "required": False},
        ]
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": str(phase_id),
                "phase_name": "In Progress",
                "fields": mock_fields,
            }
        )

        async with client_session as session:
            result = await session.call_tool(
                "get_phase_fields",
                {"phase_id": phase_id, "required_only": required_only},
            )

            assert result.isError is False, "Unexpected tool error"
            mock_pipefy_client.get_phase_fields.assert_called_once_with(
                phase_id, required_only
            )
            response = _extract_call_tool_payload(result)
            assert response["phase_id"] == str(phase_id)
            assert response["phase_name"] == "In Progress"
            assert response["fields"] == mock_fields

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_permission_denied(self, client_session, mock_pipefy_client):
        phase_id = 3190653829
        permission_error = Exception("Permission denied")
        permission_error.errors = [
            {
                "message": "Permission denied",
                "extensions": {"code": "PERMISSION_DENIED"},
            }
        ]
        mock_pipefy_client.get_phase_fields = AsyncMock(side_effect=permission_error)

        async with client_session as session:
            result = await session.call_tool(
                "get_phase_fields",
                {"phase_id": phase_id},
            )

            assert result.isError is True, "Expected tool error for permission denied"
            mock_pipefy_client.get_phase_fields.assert_called_once_with(phase_id, False)


@pytest.mark.anyio
class TestFillCardPhaseFieldsTool:
    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="accept", content={"status": "done"})],
        indirect=True,
    )
    async def test_with_elicitation(
        self,
        client_session,
        mock_pipefy_client,
    ):
        card_id = 456
        phase_id = 12345
        mock_fields = [
            {"id": "status", "label": "Status", "type": "select", "required": True},
        ]
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": str(phase_id),
                "phase_name": "Done",
                "fields": mock_fields,
            }
        )
        mock_pipefy_client.update_card = AsyncMock(
            return_value={"updateFieldsValues": {"success": True}}
        )

        async with client_session as session:
            result = await session.call_tool(
                "fill_card_phase_fields",
                {"card_id": card_id, "phase_id": phase_id},
            )

            assert result.isError is False, "Unexpected tool error"
            mock_pipefy_client.get_phase_fields.assert_called_once_with(phase_id, False)
            mock_pipefy_client.update_card.assert_called_once_with(
                card_id=card_id,
                field_updates=[{"field_id": "status", "value": "done"}],
            )

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="accept", content={"status": "done"})],
        indirect=True,
    )
    async def test_filters_non_editable_fields(
        self,
        client_session,
        mock_pipefy_client,
    ):
        card_id = 456
        phase_id = 12345
        mock_fields = [
            {
                "id": "status",
                "label": "Status",
                "type": "select",
                "required": True,
                "editable": True,
            },
            {
                "id": "internal_notes",
                "label": "Internal Notes",
                "type": "long_text",
                "required": False,
                "editable": False,
            },
        ]
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": str(phase_id),
                "phase_name": "Done",
                "fields": mock_fields,
            }
        )
        mock_pipefy_client.update_card = AsyncMock(
            return_value={"updateFieldsValues": {"success": True}}
        )

        async with client_session as session:
            result = await session.call_tool(
                "fill_card_phase_fields",
                {"card_id": card_id, "phase_id": phase_id},
            )

            assert result.isError is False, "Unexpected tool error"
            mock_pipefy_client.get_phase_fields.assert_called_once_with(phase_id, False)
            mock_pipefy_client.update_card.assert_called_once_with(
                card_id=card_id,
                field_updates=[{"field_id": "status", "value": "done"}],
            )

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="decline")],
        indirect=True,
    )
    async def test_cancelled_by_user(
        self,
        client_session,
        mock_pipefy_client,
    ):
        card_id = 456
        phase_id = 12345
        mock_fields = [
            {"id": "status", "label": "Status", "type": "select", "required": True},
        ]
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": str(phase_id),
                "phase_name": "Done",
                "fields": mock_fields,
            }
        )
        mock_pipefy_client.update_card = AsyncMock()

        async with client_session as session:
            result = await session.call_tool(
                "fill_card_phase_fields",
                {"card_id": card_id, "phase_id": phase_id},
            )

            assert result.isError is False
            mock_pipefy_client.update_card.assert_not_called()
            response = _extract_call_tool_payload(result)
            assert response == {
                "success": False,
                "error": "Phase field update cancelled by user.",
            }

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_without_elicitation(
        self,
        client_session,
        mock_pipefy_client,
    ):
        card_id = 456
        phase_id = 12345
        mock_fields = [
            {"id": "status", "label": "Status", "type": "select", "required": True},
        ]
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": str(phase_id),
                "phase_name": "Done",
                "fields": mock_fields,
            }
        )
        mock_pipefy_client.update_card = AsyncMock(
            return_value={"updateFieldsValues": {"success": True}}
        )

        async with client_session as session:
            result = await session.call_tool(
                "fill_card_phase_fields",
                {
                    "card_id": card_id,
                    "phase_id": phase_id,
                    "fields": {"status": "completed"},
                },
            )

            assert result.isError is False, "Unexpected tool error"
            mock_pipefy_client.update_card.assert_called_once_with(
                card_id=card_id,
                field_updates=[{"field_id": "status", "value": "completed"}],
            )

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_without_elicitation_filters_non_editable_fields(
        self,
        client_session,
        mock_pipefy_client,
    ):
        card_id = 456
        phase_id = 12345
        mock_fields = [
            {
                "id": "status",
                "label": "Status",
                "type": "select",
                "required": True,
                "editable": True,
            },
            {
                "id": "internal_notes",
                "label": "Internal Notes",
                "type": "long_text",
                "required": False,
                "editable": False,
            },
        ]
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": str(phase_id),
                "phase_name": "Done",
                "fields": mock_fields,
            }
        )
        mock_pipefy_client.update_card = AsyncMock(
            return_value={"updateFieldsValues": {"success": True}}
        )

        async with client_session as session:
            result = await session.call_tool(
                "fill_card_phase_fields",
                {
                    "card_id": card_id,
                    "phase_id": phase_id,
                    "fields": {"status": "completed", "internal_notes": "secret"},
                },
            )

            assert result.isError is False, "Unexpected tool error"
            mock_pipefy_client.update_card.assert_called_once_with(
                card_id=card_id,
                field_updates=[{"field_id": "status", "value": "completed"}],
            )

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_no_fields_returns_message(
        self,
        client_session,
        mock_pipefy_client,
    ):
        card_id = 456
        phase_id = 12345
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": str(phase_id),
                "phase_name": "Empty Phase",
                "message": "This phase has no fields configured.",
                "fields": [],
            }
        )
        mock_pipefy_client.update_card = AsyncMock()

        async with client_session as session:
            result = await session.call_tool(
                "fill_card_phase_fields",
                {"card_id": card_id, "phase_id": phase_id},
            )

            assert result.isError is False
            mock_pipefy_client.update_card.assert_not_called()
            response = _extract_call_tool_payload(result)
            assert response.get("message") == "No fields to update."

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_permission_denied(
        self,
        client_session,
        mock_pipefy_client,
    ):
        card_id = 456
        phase_id = 3190653829
        permission_error = Exception("Permission denied")
        permission_error.errors = [
            {
                "message": "Permission denied",
                "extensions": {"code": "PERMISSION_DENIED"},
            }
        ]
        mock_pipefy_client.get_phase_fields = AsyncMock(side_effect=permission_error)
        mock_pipefy_client.update_card = AsyncMock()

        async with client_session as session:
            result = await session.call_tool(
                "fill_card_phase_fields",
                {"card_id": card_id, "phase_id": phase_id},
            )

            assert result.isError is True, "Expected tool error for permission denied"
            mock_pipefy_client.get_phase_fields.assert_called_once_with(phase_id, False)
            mock_pipefy_client.update_card.assert_not_called()


@pytest.mark.anyio
class TestUpdateCardTool:
    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_card_field(
        self,
        client_session,
        mock_pipefy_client,
    ):
        mock_pipefy_client.update_card = AsyncMock(return_value={"ok": True})

        async with client_session as session:
            result = await session.call_tool(
                "update_card",
                {
                    "card_id": 123,
                    "field_updates": [
                        {"field_id": "status", "value": "done"},
                    ],
                },
            )

            assert result.isError is False, "Unexpected tool error"
            mock_pipefy_client.update_card.assert_called_once_with(
                card_id=123,
                title=None,
                assignee_ids=None,
                label_ids=None,
                due_date=None,
                field_updates=[{"field_id": "status", "value": "done"}],
            )


@pytest.mark.anyio
class TestDeleteCardTool:
    """Test cases for delete_card tool."""

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="decline")],
        indirect=True,
    )
    async def test_user_declines_confirmation(
        self,
        client_session,
        mock_pipefy_client,
    ) -> None:
        """Test delete_card tool when user declines confirmation via elicitation."""
        # Setup mock responses
        mock_pipefy_client.get_card.return_value = {
            "card": {"id": "12345", "title": "Test Card", "pipe": {"name": "Test Pipe"}}
        }

        async with client_session as session:
            result = await session.call_tool(
                "delete_card",
                {"card_id": 12345},
            )

            assert result.isError is False
            # Should fetch card for preview but not delete when user declines
            mock_pipefy_client.get_card.assert_called_once_with(12345)
            mock_pipefy_client.delete_card.assert_not_called()

            payload = _extract_call_tool_payload(result)
            expected_payload: DeleteCardErrorPayload = {
                "success": False,
                "error": "Card deletion cancelled by user.",
            }
            assert payload == expected_payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_invalid_card_id_returns_error(
        self,
        client_session,
        mock_pipefy_client,
    ) -> None:
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

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_resource_not_found_error_mapping(
        self,
        client_session,
        mock_pipefy_client,
    ) -> None:
        """Test delete_card tool maps RESOURCE_NOT_FOUND GraphQL exception to friendly message."""
        # Simulate GraphQL exception with RESOURCE_NOT_FOUND code
        from gql.transport.exceptions import TransportQueryError

        error = TransportQueryError(
            "GraphQL Error",
            errors=[
                {
                    "message": "Card not found",
                    "extensions": {"code": "RESOURCE_NOT_FOUND"},
                }
            ],
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

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_permission_denied_error_mapping(
        self,
        client_session,
        mock_pipefy_client,
    ) -> None:
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
            errors=[
                {
                    "message": "Permission denied",
                    "extensions": {"code": "PERMISSION_DENIED"},
                }
            ],
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

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_deletion_fails_with_success_false(
        self,
        client_session,
        mock_pipefy_client,
    ) -> None:
        """Test delete_card tool handles API returning success=False."""
        mock_pipefy_client.get_card.return_value = {
            "card": {
                "id": "12345",
                "title": "Test Card",
                "pipe": {"name": "Test Pipe"},
            }
        }
        # API returns success: False without throwing exception
        mock_pipefy_client.delete_card.return_value = {"deleteCard": {"success": False}}

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

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="accept", content={"confirm": True})],
        indirect=True,
    )
    async def test_user_confirms_deletion(
        self,
        client_session,
        mock_pipefy_client,
    ) -> None:
        """Test delete_card tool when user confirms deletion via elicitation."""
        # Setup mock responses for both get_card and delete_card
        mock_pipefy_client.get_card.return_value = {
            "card": {"id": "12345", "title": "Test Card", "pipe": {"name": "Test Pipe"}}
        }
        mock_pipefy_client.delete_card.return_value = {"deleteCard": {"success": True}}

        async with client_session as session:
            result = await session.call_tool(
                "delete_card",
                {"card_id": 12345},
            )

            assert result.isError is False
            # Should execute deletion when user confirms
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

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_raises(RuntimeError("confirmation request failed"))],
        indirect=True,
    )
    async def test_elicitation_raises_returns_failed_request_confirmation(
        self,
        client_session,
        mock_pipefy_client,
    ) -> None:
        """When elicitation for confirmation raises, tool returns error with 'Failed to request confirmation'."""
        mock_pipefy_client.get_card.return_value = {
            "card": {"id": "12345", "title": "Test Card", "pipe": {"name": "Test Pipe"}}
        }
        async with client_session as session:
            result = await session.call_tool("delete_card", {"card_id": 12345})
        assert result.isError is False
        mock_pipefy_client.get_card.assert_called_once_with(12345)
        mock_pipefy_client.delete_card.assert_not_called()
        payload = _extract_call_tool_payload(result)
        assert payload["success"] is False
        assert "Failed to request confirmation" in payload["error"]

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_debug_true_appends_codes_and_correlation_id_to_error(
        self,
        client_session,
        mock_pipefy_client,
    ) -> None:
        """When debug=True and client raises, error message includes codes and correlation_id."""
        from gql.transport.exceptions import TransportQueryError

        error = TransportQueryError(
            '{"code": "PERMISSION_DENIED", "correlation_id": "corr-xyz"}',
            errors=[
                {
                    "message": "Denied",
                    "extensions": {"code": "PERMISSION_DENIED"},
                }
            ],
        )
        mock_pipefy_client.get_card.return_value = {
            "card": {"id": "12345", "title": "Test Card", "pipe": {"name": "Test Pipe"}}
        }
        mock_pipefy_client.delete_card.side_effect = error
        async with client_session as session:
            result = await session.call_tool(
                "delete_card", {"card_id": 12345, "debug": True}
            )
        assert result.isError is False
        payload = _extract_call_tool_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert "codes=" in payload["error"] or "correlation_id=" in payload["error"]
        assert "PERMISSION_DENIED" in payload["error"]
