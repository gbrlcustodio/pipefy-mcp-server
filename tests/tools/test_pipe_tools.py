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


class DeleteCardSuccessPayload(TypedDict):
    success: Literal[True]
    card_id: int
    card_title: str
    pipe_name: str
    message: str


class DeleteCardErrorPayload(TypedDict):
    success: Literal[False]
    error: str


DeleteCardPayload = DeleteCardSuccessPayload | DeleteCardErrorPayload


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
    ):
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

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_resource_not_found_error_mapping(
        self,
        client_session,
        mock_pipefy_client,
    ):
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
    ):
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
