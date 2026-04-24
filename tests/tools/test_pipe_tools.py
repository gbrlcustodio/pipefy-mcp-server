import json
from datetime import timedelta
from random import randint
from types import SimpleNamespace
from typing import Any, cast
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
)
from pipefy_mcp.tools.pipe_tools import FIND_CARDS_RESPONSE_KEY, PipeTools
from pipefy_mcp.tools.tool_error_envelope import tool_error, tool_error_message

# =============================================================================
# Fixtures
# =============================================================================


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
    client.get_card_relations = AsyncMock(
        return_value={
            "card": {"child_relations": [], "parent_relations": []},
        }
    )
    client.delete_card = AsyncMock()
    client.delete_card_relation = AsyncMock(
        return_value={"deleteCardRelation": {"success": True}}
    )
    client.internal_api_available = True
    client.update_card = AsyncMock()
    client.get_pipe_members = AsyncMock()

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
            mock_pipefy_client.create_card.assert_called_once_with(str(pipe_id), {})
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
                str(pipe_id), {"field_1": "value_1", "field_2": "value_2"}
            )
            response = json.loads(result.content[0].text)
            expected_response = {
                "createCard": {"card": {"id": "789"}},
                "card_link": (
                    "[https://app.pipefy.com/open-cards/789](https://app.pipefy.com/open-cards/789)"
                ),
            }
            assert response == expected_response

    async def test_create_card_when_capabilities_missing_no_attribute_error(
        self,
        mock_pipefy_client,
        pipe_id,
    ):
        """client_params without capabilities must not raise when gating elicitation."""
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "789"}}
        }

        mcp = FastMCP("Pipefy MCP Test Server")
        PipeTools.register(mcp, mock_pipefy_client)

        ctx = MagicMock()
        ctx.debug = AsyncMock()
        ctx.session = SimpleNamespace(client_params=SimpleNamespace())

        result = await mcp._tool_manager.call_tool(
            "create_card",
            {"pipe_id": pipe_id},
            context=ctx,
            convert_result=False,
        )

        mock_pipefy_client.create_card.assert_called_once_with(str(pipe_id), {})
        assert result["createCard"]["card"]["id"] == "789"
        assert "card_link" in result

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
                str(pipe_id), {"field_1": "value_1"}
            )

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_title_sets_card_title_after_creation(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        """When title is provided, create_card calls update_card to set the title."""
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "789"}}
        }
        mock_pipefy_client.update_card.return_value = {
            "updateCard": {"card": {"id": "789", "title": "Copa América"}}
        }

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {"pipe_id": pipe_id, "title": "Copa América"},
            )
            assert result.isError is False
            mock_pipefy_client.create_card.assert_called_once_with(str(pipe_id), {})
            mock_pipefy_client.update_card.assert_called_once_with(
                "789", title="Copa América"
            )
            response = json.loads(result.content[0].text)
            assert response["createCard"]["card"]["title"] == "Copa América"
            assert "card_link" in response

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_title_update_failure_returns_warning(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        """When update_card raises after a successful create_card, the card result
        is still returned with a title_warning and no title set."""
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "789"}}
        }
        mock_pipefy_client.update_card.side_effect = RuntimeError("API timeout")

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {"pipe_id": pipe_id, "title": "My Title"},
            )
            assert result.isError is False
            mock_pipefy_client.create_card.assert_called_once_with(str(pipe_id), {})
            mock_pipefy_client.update_card.assert_called_once_with(
                "789", title="My Title"
            )
            response = json.loads(result.content[0].text)
            assert "title" not in response.get("createCard", {}).get("card", {})
            assert "title_warning" in response
            assert "API timeout" in response["title_warning"]
            assert "card_link" in response

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_no_title_skips_update_card(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        """When title is not provided, update_card is never called."""
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "789"}}
        }

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {"pipe_id": pipe_id},
            )
            assert result.isError is False
            mock_pipefy_client.update_card.assert_not_called()

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_permission_denied_enriches_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
        extract_payload,
    ):
        from gql.transport.exceptions import TransportQueryError

        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.create_card.side_effect = TransportQueryError(
            "forbidden",
            errors=[
                {
                    "message": "forbidden",
                    "extensions": {"code": "PERMISSION_DENIED"},
                }
            ],
        )
        mock_pipefy_client.get_pipe_members.side_effect = RuntimeError("no access")

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {"pipe_id": pipe_id},
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "invite_members" in tool_error_message(payload)


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
            mock_pipefy_client.get_pipe_members.assert_called_once_with(str(pipe_id))


@pytest.mark.anyio
class TestGetLabels:
    """Tests for get_labels tool (delegates to client.get_pipe)."""

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_labels_success_returns_labels(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
        extract_payload,
    ) -> None:
        labels = [{"id": "301", "name": "Urgent"}, {"id": "302", "name": "Low"}]
        mock_pipefy_client.get_pipe = AsyncMock(
            return_value={"pipe": {"id": str(pipe_id), "labels": labels}}
        )
        async with client_session as session:
            result = await session.call_tool("get_labels", {"pipe_id": pipe_id})
        assert result.isError is False
        mock_pipefy_client.get_pipe.assert_called_once_with(str(pipe_id))
        payload = extract_payload(result)
        assert payload == {
            "success": True,
            "message": "Labels loaded.",
            "labels": labels,
        }

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_labels_empty_returns_empty_list(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.get_pipe = AsyncMock(
            return_value={"pipe": {"id": "1", "labels": []}}
        )
        async with client_session as session:
            result = await session.call_tool("get_labels", {"pipe_id": 1})
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["labels"] == []

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_labels_null_labels_normalized_to_empty_list(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.get_pipe = AsyncMock(
            return_value={"pipe": {"id": "1", "labels": None}}
        )
        async with client_session as session:
            result = await session.call_tool("get_labels", {"pipe_id": "1"})
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["labels"] == []

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_labels_pipe_null_returns_access_denied(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.get_pipe = AsyncMock(return_value={"pipe": None})
        async with client_session as session:
            result = await session.call_tool("get_labels", {"pipe_id": 999})
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "access denied" in tool_error_message(payload).lower()

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_labels_get_pipe_exception_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        from gql.transport.exceptions import TransportQueryError

        mock_pipefy_client.get_pipe.side_effect = TransportQueryError(
            "GraphQL Error",
            errors=[
                {"message": "Denied", "extensions": {"code": "PERMISSION_DENIED"}},
            ],
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_labels", {"pipe_id": 1, "debug": False}
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload


@pytest.mark.anyio
class TestDirectToolCalls:
    """Direct tests for tools that simply forward params to the client."""

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_card_forwards_params_to_client(
        self, client_session, mock_pipefy_client, extract_payload
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
        mock_pipefy_client.get_card.assert_called_once_with("123", include_fields=True)
        payload = extract_payload(result)
        assert payload["card"]["id"] == "123"

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_pipe_forwards_pipe_id_to_client(
        self, client_session, mock_pipefy_client, pipe_id, extract_payload
    ):
        """get_pipe tool forwards pipe_id to client."""
        mock_pipefy_client.get_pipe = AsyncMock(
            return_value={"pipe": {"id": pipe_id, "name": "My Pipe"}}
        )
        async with client_session as session:
            result = await session.call_tool("get_pipe", {"pipe_id": pipe_id})
        assert result.isError is False
        mock_pipefy_client.get_pipe.assert_called_once_with(str(pipe_id))
        payload = extract_payload(result)
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
        mock_pipefy_client.move_card_to_phase.assert_called_once_with("100", "200")

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_move_card_to_phase_returns_enriched_payload_when_transition_invalid(
        self, client_session, mock_pipefy_client, extract_payload
    ):
        """On API failure, enrich if destination is not in cards_can_be_moved_to_phases."""

        async def _fail_move(*_args):
            raise RuntimeError("not a valid target phase")

        mock_pipefy_client.move_card_to_phase = AsyncMock(side_effect=_fail_move)
        mock_pipefy_client.get_card = AsyncMock(
            return_value={
                "card": {"id": "1", "current_phase": {"id": "10", "name": "Doing"}},
            }
        )
        mock_pipefy_client.get_phase_allowed_move_targets = AsyncMock(
            return_value={
                "phase": {
                    "id": "10",
                    "name": "Doing",
                    "cards_can_be_moved_to_phases": [
                        {"id": "11", "name": "Done"},
                    ],
                }
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "move_card_to_phase",
                {"card_id": 1, "destination_phase_id": 99},
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload.get("success") is False
        assert "99" in tool_error_message(payload)
        assert payload["valid_destinations"] == [{"id": "11", "name": "Done"}]

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_move_card_to_phase_surfaces_original_error_when_destination_allowed(
        self, client_session, mock_pipefy_client
    ):
        """If transition is allowed, surface the original API error (e.g. permissions)."""

        async def _fail_move(*_args):
            raise RuntimeError("forbidden")

        mock_pipefy_client.move_card_to_phase = AsyncMock(side_effect=_fail_move)
        mock_pipefy_client.get_card = AsyncMock(
            return_value={
                "card": {"current_phase": {"id": "10", "name": "Doing"}},
            }
        )
        mock_pipefy_client.get_phase_allowed_move_targets = AsyncMock(
            return_value={
                "phase": {
                    "id": "10",
                    "name": "Doing",
                    "cards_can_be_moved_to_phases": [
                        {"id": "99", "name": "Target"},
                    ],
                }
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "move_card_to_phase",
                {"card_id": 1, "destination_phase_id": 99},
            )
        assert result.isError is True
        assert "forbidden" in (result.content[0].text if result.content else "")

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_start_form_fields_forwards_params_to_client(
        self, client_session, mock_pipefy_client, pipe_id, extract_payload
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
        mock_pipefy_client.get_start_form_fields.assert_called_once_with(
            str(pipe_id), True
        )
        payload = extract_payload(result)
        assert "start_form_fields" in payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_comment_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        legacy_envelope,
    ):
        """update_comment with valid input returns success payload with comment_id."""
        async with client_session as session:
            result = await session.call_tool(
                "update_comment",
                {"comment_id": 456, "text": "Updated text"},
            )
        assert result.isError is False
        mock_pipefy_client.update_comment.assert_called_once_with("456", "Updated text")
        payload = extract_payload(result)
        assert payload == {"success": True, "comment_id": "c_999"}

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_comment_zero_id_coerces_to_string_and_calls_api(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        legacy_envelope,
    ):
        """update_comment with comment_id=0 coerces to '0' via PipefyId and calls the API."""
        async with client_session as session:
            result = await session.call_tool(
                "update_comment",
                {"comment_id": 0, "text": "hello"},
            )
        assert result.isError is False
        mock_pipefy_client.update_comment.assert_called_once_with("0", "hello")
        payload = extract_payload(result)
        assert payload == {"success": True, "comment_id": "c_999"}

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_comment_blank_text_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """update_comment with blank text returns error payload without calling API."""
        async with client_session as session:
            result = await session.call_tool(
                "update_comment",
                {"comment_id": 1, "text": "   "},
            )
        assert result.isError is False
        mock_pipefy_client.update_comment.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_comment_text_over_max_length_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
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
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_comment_api_exception_returns_mapped_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
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
        mock_pipefy_client.update_comment.assert_called_once_with("99999", "hello")
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert "comment" in tool_error_message(
            payload
        ).lower() or "comment_id" in tool_error_message(payload)

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_delete_comment_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """delete_comment with valid comment_id returns success payload."""
        async with client_session as session:
            result = await session.call_tool(
                "delete_comment",
                {"comment_id": 456, "confirm": True},
            )
        assert result.isError is False
        mock_pipefy_client.delete_comment.assert_called_once_with("456")
        payload = extract_payload(result)
        assert payload == {"success": True}

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_delete_comment_zero_id_coerces_to_string_and_calls_api(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """delete_comment with comment_id=0 coerces to '0' via PipefyId and calls the API."""
        async with client_session as session:
            result = await session.call_tool(
                "delete_comment",
                {"comment_id": 0, "confirm": True},
            )
        assert result.isError is False
        mock_pipefy_client.delete_comment.assert_called_once_with("0")
        payload = extract_payload(result)
        assert payload == {"success": True}

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_delete_comment_api_exception_returns_mapped_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
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
                {"comment_id": 12345, "confirm": True},
            )
        assert result.isError is False
        mock_pipefy_client.delete_comment.assert_called_once_with("12345")
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert "permission" in tool_error_message(payload).lower()

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_delete_comment_comment_not_found_returns_mapped_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
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
                {"comment_id": 99999, "confirm": True},
            )
        assert result.isError is False
        mock_pipefy_client.delete_comment.assert_called_once_with("99999")
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert "comment" in tool_error_message(
            payload
        ).lower() or "not found" in tool_error_message(payload)

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_delete_comment_preview_then_confirm_true_runs_mutation(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Destructive guard: default returns preview; confirm=True runs delete (step 2)."""
        comment_id = 42
        resource = f"comment (ID: {comment_id})"
        expected_preview = {
            "success": False,
            "requires_confirmation": True,
            "resource": resource,
            "message": (
                f"⚠️ You are about to permanently delete {resource}. "
                "This action is irreversible. Set 'confirm=True' to proceed."
            ),
        }

        async with client_session as session:
            preview = await session.call_tool(
                "delete_comment",
                {"comment_id": comment_id},
            )
            assert preview.isError is False
            mock_pipefy_client.delete_comment.assert_not_called()
            assert extract_payload(preview) == expected_preview

            result = await session.call_tool(
                "delete_comment",
                {"comment_id": comment_id, "confirm": True},
            )
        assert result.isError is False
        mock_pipefy_client.delete_comment.assert_called_once_with(str(comment_id))
        assert extract_payload(result) == {"success": True}


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
            str(pipe_id), None, include_fields=True, first=None, after=None
        )

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_cards_flag_on_emits_pagination(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
        extract_payload,
        unified_envelope,
    ):
        """Flag=true — response is the unified envelope with a top-level pagination block."""
        mock_pipefy_client.get_cards = AsyncMock(
            return_value={
                "cards": {
                    "edges": [{"node": {"id": "1"}}],
                    "pageInfo": {"hasNextPage": True, "endCursor": "x"},
                }
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_cards", {"pipe_id": pipe_id, "first": 10}
            )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["pagination"] == {
            "has_more": True,
            "end_cursor": "x",
            "page_size": 10,
        }
        assert payload["data"]["cards"]["edges"][0]["node"]["id"] == "1"

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_cards_flag_on_no_first_omits_pagination(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
        extract_payload,
        unified_envelope,
    ):
        """Flag=true with first=None — pagination block is omitted.

        Regression: the earlier implementation emitted ``page_size=0`` in this
        case, which the shared ``validate_page_size`` itself would reject as
        ``INVALID_ARGUMENTS``.
        """
        mock_pipefy_client.get_cards = AsyncMock(
            return_value={"cards": {"edges": [], "pageInfo": {"hasNextPage": False}}}
        )
        async with client_session as session:
            result = await session.call_tool("get_cards", {"pipe_id": pipe_id})
        payload = extract_payload(result)
        assert payload["success"] is True
        assert "pagination" not in payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_cards_flag_off_returns_raw_graphql(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
        extract_payload,
        legacy_envelope,
    ):
        """Flag=false — tool returns the client response verbatim (legacy shape)."""
        expected = {"cards": {"edges": [], "pageInfo": {"hasNextPage": False}}}
        mock_pipefy_client.get_cards = AsyncMock(return_value=expected)
        async with client_session as session:
            result = await session.call_tool(
                "get_cards", {"pipe_id": pipe_id, "first": 10}
            )
        payload = extract_payload(result)
        assert payload == expected

    @pytest.mark.parametrize("flag_value", [True, False])
    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_cards_out_of_bounds_returns_invalid_arguments(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
        extract_payload,
        flag_value,
        monkeypatch,
    ):
        from pipefy_mcp.settings import settings

        monkeypatch.setattr(settings.pipefy, "mcp_unified_envelope", flag_value)
        mock_pipefy_client.get_cards = AsyncMock(return_value={"cards": {}})
        async with client_session as session:
            result = await session.call_tool(
                "get_cards", {"pipe_id": pipe_id, "first": 99999}
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert payload["error"]["code"] == "INVALID_ARGUMENTS"
        assert payload["error"]["details"] == {
            "min": 1,
            "max": 500,
            "provided": 99999,
        }
        mock_pipefy_client.get_cards.assert_not_called()

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_cards_title_param_merges_into_search(
        self, client_session, mock_pipefy_client, pipe_id
    ):
        """When title is provided, it is merged into the search dict sent to the client."""
        mock_pipefy_client.get_cards = AsyncMock(return_value={"cards": {"edges": []}})

        async with client_session as session:
            result = await session.call_tool(
                "get_cards",
                {"pipe_id": pipe_id, "title": "Copa"},
            )

        assert result.isError is False
        mock_pipefy_client.get_cards.assert_called_once_with(
            str(pipe_id),
            {"title": "Copa"},
            include_fields=False,
            first=None,
            after=None,
        )

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_cards_title_merges_with_existing_search(
        self, client_session, mock_pipefy_client, pipe_id
    ):
        """When title and search are both provided, title is merged into search."""
        mock_pipefy_client.get_cards = AsyncMock(return_value={"cards": {"edges": []}})

        async with client_session as session:
            result = await session.call_tool(
                "get_cards",
                {
                    "pipe_id": pipe_id,
                    "title": "Copa",
                    "search": {"include_done": True},
                },
            )

        assert result.isError is False
        mock_pipefy_client.get_cards.assert_called_once_with(
            str(pipe_id),
            {"include_done": True, "title": "Copa"},
            include_fields=False,
            first=None,
            after=None,
        )


@pytest.mark.anyio
class TestFindCardsTool:
    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_find_cards_forwards_params_to_client(
        self, client_session, mock_pipefy_client, pipe_id, extract_payload
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
            str(pipe_id),
            field_id,
            field_value,
            include_fields=True,
            first=None,
            after=None,
        )
        payload = extract_payload(result)
        assert FIND_CARDS_RESPONSE_KEY in payload
        assert payload[FIND_CARDS_RESPONSE_KEY]["edges"]

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_find_cards_empty_edges_includes_message(
        self, client_session, mock_pipefy_client, pipe_id, extract_payload
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
        payload = extract_payload(result)
        assert payload.get("message") == FIND_CARDS_EMPTY_MESSAGE
        assert payload.get(FIND_CARDS_RESPONSE_KEY, {}).get("edges") == []


@pytest.mark.anyio
class TestAddCardCommentTool:
    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        legacy_envelope,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "add_card_comment",
                {"card_id": 123, "text": "hello"},
            )

            assert result.isError is False
            mock_pipefy_client.add_card_comment.assert_called_once_with(
                card_id="123", text="hello"
            )
            payload = extract_payload(result)
            assert payload == {"success": True, "comment_id": "c_987"}

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_zero_card_id_coerces_to_string_and_calls_api(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
        legacy_envelope,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "add_card_comment",
                {"card_id": 0, "text": "hello"},
            )

            assert result.isError is False
            mock_pipefy_client.add_card_comment.assert_called_once_with(
                card_id="0", text="hello"
            )
            payload = extract_payload(result)
            assert payload == {"success": True, "comment_id": "c_987"}

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_api_exception_returns_mapped_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
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
            card_id="123", text="hello"
        )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert "Card not found" in tool_error_message(
            payload
        ) or "card_id" in tool_error_message(payload)


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
        self, client_session, mock_pipefy_client, required_only, extract_payload
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
                str(phase_id), required_only
            )
            response = extract_payload(result)
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
            mock_pipefy_client.get_phase_fields.assert_called_once_with(
                str(phase_id), False
            )


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
            mock_pipefy_client.get_phase_fields.assert_called_once_with(
                str(phase_id), False
            )
            mock_pipefy_client.update_card.assert_called_once_with(
                card_id=str(card_id),
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
            mock_pipefy_client.get_phase_fields.assert_called_once_with(
                str(phase_id), False
            )
            mock_pipefy_client.update_card.assert_called_once_with(
                card_id=str(card_id),
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
        extract_payload,
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
            response = extract_payload(result)
            assert response == tool_error("Phase field update cancelled by user.")

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
                card_id=str(card_id),
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
                card_id=str(card_id),
                field_updates=[{"field_id": "status", "value": "completed"}],
            )

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_no_fields_returns_message(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
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
            response = extract_payload(result)
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
            mock_pipefy_client.get_phase_fields.assert_called_once_with(
                str(phase_id), False
            )
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
                card_id="123",
                title=None,
                assignee_ids=None,
                label_ids=None,
                due_date=None,
                field_updates=[{"field_id": "status", "value": "done"}],
            )


@pytest.mark.anyio
class TestDeleteCardTool:
    """Test cases for delete_card tool."""

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_preview_returned_when_no_elicitation_and_no_confirm(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        """Without elicitation and without confirm=True, return a preview payload — never delete."""
        mock_pipefy_client.get_card.return_value = {
            "card": {
                "id": "12345",
                "title": "Test Card",
                "pipe": {"name": "Test Pipe"},
            }
        }

        async with client_session as session:
            result = await session.call_tool(
                "delete_card",
                {"card_id": 12345},
            )

            assert result.isError is False
            mock_pipefy_client.get_card.assert_called_once_with("12345")
            mock_pipefy_client.delete_card.assert_not_called()

            payload = extract_payload(result)
            assert payload == {
                "success": False,
                "requires_confirmation": True,
                "resource": "card 'Test Card' (ID: 12345) from pipe 'Test Pipe'",
                "message": (
                    "⚠️ You are about to permanently delete "
                    "card 'Test Card' (ID: 12345) from pipe 'Test Pipe'. "
                    "This action is irreversible. Set 'confirm=True' to proceed."
                ),
            }

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_confirm_true_accepts_string_card_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        """String card_id is accepted (GraphQL IDs are strings)."""
        mock_pipefy_client.get_card.return_value = {
            "card": {"id": "12345", "title": "Test Card", "pipe": {"name": "Test Pipe"}}
        }
        mock_pipefy_client.delete_card.return_value = {"deleteCard": {"success": True}}

        async with client_session as session:
            result = await session.call_tool(
                "delete_card",
                {"card_id": "12345", "confirm": True},
            )

        assert result.isError is False
        mock_pipefy_client.get_card.assert_called_once_with("12345")
        mock_pipefy_client.delete_card.assert_called_once_with("12345")
        payload = extract_payload(result)
        assert payload["success"] is True

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="decline")],
        indirect=True,
    )
    async def test_user_declines_confirmation(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        """Without confirm=True, deletion never runs—even if the client supports elicitation."""
        mock_pipefy_client.get_card.return_value = {
            "card": {"id": "12345", "title": "Test Card", "pipe": {"name": "Test Pipe"}}
        }

        async with client_session as session:
            result = await session.call_tool(
                "delete_card",
                {"card_id": 12345},
            )

            assert result.isError is False
            mock_pipefy_client.get_card.assert_called_once_with("12345")
            mock_pipefy_client.delete_card.assert_not_called()

            payload = extract_payload(result)
            assert payload == {
                "success": False,
                "requires_confirmation": True,
                "resource": "card 'Test Card' (ID: 12345) from pipe 'Test Pipe'",
                "message": (
                    "⚠️ You are about to permanently delete "
                    "card 'Test Card' (ID: 12345) from pipe 'Test Pipe'. "
                    "This action is irreversible. Set 'confirm=True' to proceed."
                ),
            }

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_invalid_card_id_returns_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        """Test delete_card tool with invalid card_id returns error payload."""
        async with client_session as session:
            result = await session.call_tool(
                "delete_card",
                {"card_id": 0, "confirm": True},
            )

            assert result.isError is False
            mock_pipefy_client.get_card.assert_not_called()
            mock_pipefy_client.delete_card.assert_not_called()

            payload = extract_payload(result)
            expected_payload = cast(
                DeleteCardErrorPayload,
                tool_error("Invalid 'card_id': provide a positive integer."),
            )
            assert payload == expected_payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_resource_not_found_error_mapping(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
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
            mock_pipefy_client.get_card.assert_called_once_with("99999")
            mock_pipefy_client.delete_card.assert_not_called()

            payload = extract_payload(result)
            expected_payload = cast(
                DeleteCardErrorPayload,
                tool_error(
                    "Card with ID 99999 not found. Verify the card exists and you have access permissions."
                ),
            )
            assert payload == expected_payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_permission_denied_error_mapping(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
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
            mock_pipefy_client.delete_card.assert_called_once_with("12345")

            payload = extract_payload(result)
            expected_payload = cast(
                DeleteCardErrorPayload,
                tool_error(
                    "You don't have permission to delete card 12345. Please check your access permissions."
                ),
            )
            assert payload == expected_payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_deletion_fails_with_success_false(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
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
            mock_pipefy_client.delete_card.assert_called_once_with("12345")

            payload = extract_payload(result)
            expected_payload = cast(
                DeleteCardErrorPayload,
                tool_error(
                    "Failed to delete card 'Test Card' (ID: 12345). Please try again or contact support."
                ),
            )
            assert payload == expected_payload

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_raises(RuntimeError("elicit should not run"))],
        indirect=True,
    )
    async def test_confirm_true_bypasses_elicitation(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        """With confirm=True, delete runs without elicitation even if client supports it."""
        mock_pipefy_client.get_card.return_value = {
            "card": {"id": "12345", "title": "Test Card", "pipe": {"name": "Test Pipe"}}
        }
        mock_pipefy_client.delete_card.return_value = {"deleteCard": {"success": True}}

        async with client_session as session:
            result = await session.call_tool(
                "delete_card",
                {"card_id": 12345, "confirm": True},
            )

        assert result.isError is False
        mock_pipefy_client.delete_card.assert_called_once_with("12345")
        payload = extract_payload(result)
        assert payload["success"] is True

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="accept", content={"confirm": True})],
        indirect=True,
    )
    async def test_elicitation_does_not_authorize_delete_without_confirm_true(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        """Elicitation accept must not delete; only confirm=True may run the mutation."""
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
            mock_pipefy_client.delete_card.assert_not_called()

            payload = extract_payload(result)
            assert payload["success"] is False
            assert payload["requires_confirmation"] is True

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_raises(RuntimeError("confirmation request failed"))],
        indirect=True,
    )
    async def test_elicitation_callback_unused_for_delete_preview(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        """Guard does not call elicit; a broken elicitation callback must not affect preview."""
        mock_pipefy_client.get_card.return_value = {
            "card": {"id": "12345", "title": "Test Card", "pipe": {"name": "Test Pipe"}}
        }
        async with client_session as session:
            result = await session.call_tool("delete_card", {"card_id": 12345})
        assert result.isError is False
        mock_pipefy_client.get_card.assert_called_once_with("12345")
        mock_pipefy_client.delete_card.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert payload["requires_confirmation"] is True

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_debug_true_appends_codes_and_correlation_id_to_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
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
                "delete_card", {"card_id": 12345, "confirm": True, "debug": True}
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert "codes=" in tool_error_message(
            payload
        ) or "correlation_id=" in tool_error_message(payload)
        assert "PERMISSION_DENIED" in tool_error_message(payload)


@pytest.mark.anyio
class TestGetCardRelations:
    """Tests for get_card_relations tool."""

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_success_returns_child_and_parent_relations(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        child_rel = [
            {
                "name": "rel",
                "pipe": {"id": "10", "name": "Pipe A"},
                "cards": [{"id": "c1", "title": "One"}],
            }
        ]
        parent_rel = [
            {
                "name": "parent",
                "pipe": {"id": "20", "name": "Pipe B"},
                "cards": [{"id": "p1", "title": "Two"}],
            }
        ]
        mock_pipefy_client.get_card_relations = AsyncMock(
            return_value={
                "card": {
                    "child_relations": child_rel,
                    "parent_relations": parent_rel,
                }
            }
        )
        async with client_session as session:
            result = await session.call_tool("get_card_relations", {"card_id": 555})
        assert result.isError is False
        mock_pipefy_client.get_card_relations.assert_called_once_with("555")
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["child_relations"] == child_rel
        assert payload["parent_relations"] == parent_rel

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_success_accepts_camelcase_keys_from_response(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        """Older or alternate clients may return camelCase keys; tool normalizes both."""
        row = [{"name": "x", "pipe": {"id": "1", "name": "P"}, "cards": []}]
        mock_pipefy_client.get_card_relations = AsyncMock(
            return_value={"card": {"childRelations": row, "parentRelations": []}}
        )
        async with client_session as session:
            result = await session.call_tool("get_card_relations", {"card_id": 1})
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["child_relations"] == row
        assert payload["parent_relations"] == []

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_empty_relations_returns_empty_lists(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.get_card_relations = AsyncMock(
            return_value={"card": {"child_relations": [], "parent_relations": []}}
        )
        async with client_session as session:
            result = await session.call_tool("get_card_relations", {"card_id": "999"})
        assert result.isError is False
        payload = extract_payload(result)
        assert payload == {
            "success": True,
            "message": "Card relations loaded.",
            "child_relations": [],
            "parent_relations": [],
        }

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_graphql_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        from gql.transport.exceptions import TransportQueryError

        mock_pipefy_client.get_card_relations.side_effect = TransportQueryError(
            "GraphQL Error",
            errors=[
                {"message": "Not found", "extensions": {"code": "RESOURCE_NOT_FOUND"}},
            ],
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_card_relations", {"card_id": 1, "debug": False}
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_card_null_returns_not_found(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.get_card_relations = AsyncMock(return_value={"card": None})
        async with client_session as session:
            result = await session.call_tool("get_card_relations", {"card_id": 42})
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "not found" in tool_error_message(payload).lower()


@pytest.mark.anyio
class TestDeleteCardRelation:
    """Tests for delete_card_relation tool."""

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_preview_then_confirm_success(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        child_id, parent_id, source_id = 1, 2, 3
        resource = f"card relation (child: {child_id}, parent: {parent_id}, source: {source_id})"
        expected_preview = {
            "success": False,
            "requires_confirmation": True,
            "resource": resource,
            "message": (
                f"⚠️ You are about to permanently delete {resource}. "
                "This action is irreversible. Set 'confirm=True' to proceed."
            ),
        }
        mock_pipefy_client.delete_card_relation.return_value = {
            "deleteCardRelation": {"success": True}
        }

        async with client_session as session:
            preview = await session.call_tool(
                "delete_card_relation",
                {
                    "child_id": child_id,
                    "parent_id": parent_id,
                    "source_id": source_id,
                },
            )
            assert preview.isError is False
            mock_pipefy_client.delete_card_relation.assert_not_called()
            assert extract_payload(preview) == expected_preview

            result = await session.call_tool(
                "delete_card_relation",
                {
                    "child_id": child_id,
                    "parent_id": parent_id,
                    "source_id": source_id,
                    "confirm": True,
                },
            )
        assert result.isError is False
        mock_pipefy_client.delete_card_relation.assert_called_once_with(
            str(child_id), str(parent_id), str(source_id)
        )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["message"] == "Card relation removed."

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_api_exception_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        from gql.transport.exceptions import TransportQueryError

        mock_pipefy_client.delete_card_relation.side_effect = TransportQueryError(
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
                "delete_card_relation",
                {
                    "child_id": 10,
                    "parent_id": 20,
                    "source_id": 30,
                    "confirm": True,
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_mutation_success_false_returns_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.delete_card_relation = AsyncMock(
            return_value={"deleteCardRelation": {"success": False}}
        )
        async with client_session as session:
            result = await session.call_tool(
                "delete_card_relation",
                {
                    "child_id": "a",
                    "parent_id": "b",
                    "source_id": "c",
                    "confirm": True,
                },
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "did not succeed" in tool_error_message(payload).lower()

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_not_configured_returns_oauth_message(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        """delete_card_relation requires internal API (OAuth) credentials."""
        mock_pipefy_client.internal_api_available = False
        async with client_session as session:
            result = await session.call_tool(
                "delete_card_relation",
                {
                    "child_id": "1",
                    "parent_id": "2",
                    "source_id": "3",
                    "confirm": True,
                },
            )
        assert result.isError is False
        mock_pipefy_client.delete_card_relation.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "OAuth" in tool_error_message(payload)


@pytest.mark.anyio
class TestPipefyIdCoercion:
    """PipefyId coerces int IDs to str at the tool boundary."""

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_pipe_coerces_int_pipe_id(
        self, client_session, mock_pipefy_client, extract_payload
    ):
        mock_pipefy_client.get_pipe = AsyncMock(
            return_value={"pipe": {"id": "999", "name": "Test"}}
        )
        async with client_session as session:
            result = await session.call_tool("get_pipe", {"pipe_id": 999})
        assert result.isError is False
        mock_pipefy_client.get_pipe.assert_called_once_with("999")

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_move_card_to_phase_coerces_int_ids(
        self, client_session, mock_pipefy_client
    ):
        mock_pipefy_client.move_card_to_phase = AsyncMock(
            return_value={"moveCardToPhase": {"card": {"id": "1"}}}
        )
        async with client_session as session:
            result = await session.call_tool(
                "move_card_to_phase",
                {"card_id": 555, "destination_phase_id": 777},
            )
        assert result.isError is False
        mock_pipefy_client.move_card_to_phase.assert_called_once_with("555", "777")


@pytest.mark.anyio
class TestSkipElicitation:
    """skip_elicitation=True bypasses interactive elicitation and sends fields directly."""

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="accept", content={"confirm": True})],
        indirect=True,
    )
    async def test_create_card_skip_elicitation_filters_editable_fields(
        self, client_session, mock_pipefy_client, pipe_id
    ):
        """skip_elicitation=True: fields are filtered to editable IDs and sent directly."""
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": [
                {"id": "f1", "label": "F1", "type": "short_text", "editable": True},
                {"id": "f2", "label": "F2", "type": "short_text", "editable": False},
            ]
        }
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "10"}}
        }

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {
                    "pipe_id": pipe_id,
                    "fields": {"f1": "a", "f2": "b"},
                    "skip_elicitation": True,
                },
            )
        assert result.isError is False
        # f2 is non-editable, so only f1 should be forwarded
        mock_pipefy_client.create_card.assert_called_once_with(
            str(pipe_id), {"f1": "a"}
        )

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="accept", content={"f1": "overridden"})],
        indirect=True,
    )
    async def test_create_card_default_uses_elicitation(
        self, client_session, mock_pipefy_client, pipe_id
    ):
        """Default skip_elicitation=False: elicitation branch is taken."""
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": [
                {
                    "id": "f1",
                    "label": "F1",
                    "type": "short_text",
                    "required": False,
                    "editable": True,
                },
            ]
        }
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "11"}}
        }

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {"pipe_id": pipe_id, "fields": {"f1": "original"}},
            )
        assert result.isError is False
        # Elicitation accepted with overridden value
        mock_pipefy_client.create_card.assert_called_once_with(
            str(pipe_id), {"f1": "overridden"}
        )

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="accept", content={"status": "done"})],
        indirect=True,
    )
    async def test_fill_phase_skip_elicitation_filters_editable_fields(
        self, client_session, mock_pipefy_client
    ):
        """skip_elicitation=True on fill_card_phase_fields: fields filtered and sent directly."""
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": "100",
                "phase_name": "Review",
                "fields": [
                    {
                        "id": "status",
                        "label": "Status",
                        "type": "select",
                        "editable": True,
                    },
                    {
                        "id": "readonly",
                        "label": "RO",
                        "type": "short_text",
                        "editable": False,
                    },
                ],
            }
        )
        mock_pipefy_client.update_card = AsyncMock(
            return_value={"updateFieldsValues": {"success": True}}
        )

        async with client_session as session:
            result = await session.call_tool(
                "fill_card_phase_fields",
                {
                    "card_id": "99",
                    "phase_id": "100",
                    "fields": {"status": "done", "readonly": "nope"},
                    "skip_elicitation": True,
                },
            )
        assert result.isError is False
        # readonly should be filtered out
        mock_pipefy_client.update_card.assert_called_once_with(
            card_id="99",
            field_updates=[{"field_id": "status", "value": "done"}],
        )

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="accept", content={"status": "approved"})],
        indirect=True,
    )
    async def test_fill_phase_default_uses_elicitation(
        self, client_session, mock_pipefy_client
    ):
        """Default skip_elicitation=False: elicitation branch is taken for fill_card_phase_fields."""
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": "100",
                "phase_name": "Review",
                "fields": [
                    {
                        "id": "status",
                        "label": "Status",
                        "type": "select",
                        "required": False,
                        "editable": True,
                    },
                ],
            }
        )
        mock_pipefy_client.update_card = AsyncMock(
            return_value={"updateFieldsValues": {"success": True}}
        )

        async with client_session as session:
            result = await session.call_tool(
                "fill_card_phase_fields",
                {
                    "card_id": "99",
                    "phase_id": "100",
                    "fields": {"status": "pending"},
                },
            )
        assert result.isError is False
        # Elicitation accepted with "approved"
        mock_pipefy_client.update_card.assert_called_once_with(
            card_id="99",
            field_updates=[{"field_id": "status", "value": "approved"}],
        )


# =============================================================================
# structured_output=False on comment/card mutation tools
# =============================================================================
#
# These four tools used TypedDict return annotations, which FastMCP auto-detects
# as structured output. The resulting ``CallToolResult`` carried a
# ``structuredContent`` field that MCP clients surface wrapped in ``{"result":
# {...}}`` — visually different from the 13 other ``delete_*`` tools that
# return plain ``dict[str, Any]``. We disable structured output on the four
# outliers so all comment/card/delete tools share the same envelope shape.


@pytest.mark.anyio
@pytest.mark.parametrize("client_session", [None], indirect=True)
@pytest.mark.parametrize(
    "tool_name,args,prep",
    [
        (
            "add_card_comment",
            {"card_id": "1", "text": "hi"},
            None,
        ),
        (
            "update_comment",
            {"comment_id": "1", "text": "hi"},
            None,
        ),
        (
            "delete_comment",
            {"comment_id": "1", "confirm": True},
            None,
        ),
        (
            "delete_card",
            {"card_id": "1", "confirm": True},
            "delete_card",
        ),
    ],
)
async def test_comment_and_card_mutations_emit_unstructured_content(
    client_session, mock_pipefy_client, tool_name, args, prep
):
    """Tools keep their TypedDict return hints for callers, but
    ``structured_output=False`` prevents the ``{"result": {...}}`` wrap that
    FastMCP otherwise generates when a tool declares structured output."""
    if prep == "delete_card":
        mock_pipefy_client.get_card.return_value = {
            "card": {
                "id": "1",
                "title": "T",
                "pipe": {"name": "P"},
            }
        }
        mock_pipefy_client.delete_card.return_value = {"deleteCard": {"success": True}}
    async with client_session as session:
        result = await session.call_tool(tool_name, args)
    assert result.isError is False
    # The tool body returns a plain success dict; structured_output=False
    # means no structuredContent is emitted on the MCP protocol side.
    assert result.structuredContent is None
