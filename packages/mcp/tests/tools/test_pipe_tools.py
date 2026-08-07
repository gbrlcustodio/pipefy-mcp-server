import json
from datetime import timedelta
from random import randint
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from _mcp_compat import (
    create_connected_server_and_client_session as create_client_session,
)
from mcp import ClientSession
from mcp.server import ServerRequestContext
from mcp.shared.exceptions import NoBackChannelError
from mcp.types import (
    ElicitRequestParams,
    ElicitResult,
)
from pipefy_sdk import PipefyClient, PipefyGraphQLError

from pipefy_mcp.auth import RequestScopedIdentity
from pipefy_mcp.core.runtime import McpRuntime
from pipefy_mcp.core.tool_error_envelope import tool_error, tool_error_message
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.pipe_tool_helpers import (
    FIND_CARDS_EMPTY_MESSAGE,
    DeleteCardErrorPayload,
)
from pipefy_mcp.tools.pipe_tools import FIND_CARDS_RESPONSE_KEY, PipeTools
from tools.conftest import build_tool_test_server

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mcp_server(mock_pipefy_client):
    return build_tool_test_server(
        "Pipefy MCP Test Server", PipeTools.register, mock_pipefy_client
    )


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
    client.update_card = AsyncMock()
    client.get_pipe_members = AsyncMock()

    return client


@pytest.fixture(autouse=True)
def mock_mcp_runtime(mocker, mock_pipefy_client):
    runtime = Mock(McpRuntime)
    runtime.pipefy_client = mock_pipefy_client

    # build_pipefy_mcp_server constructs McpRuntime once; patch it where the
    # server module looks it up so the built runtime is this mock.
    return mocker.patch(
        "pipefy_mcp.server.McpRuntime",
        return_value=runtime,
    )


@pytest.fixture
def client_session(mcp_server, request):
    return create_client_session(
        mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=getattr(request, "param", None),
    )


@pytest.fixture
def pipe_id() -> int:
    return randint(1, 10000)


def elicitation_callback_for(action, content=None):
    async def callback(
        context: ServerRequestContext[ClientSession, Any],
        params: ElicitRequestParams,
    ) -> ElicitResult:
        return ElicitResult(action=action, content=content)

    return callback


def elicitation_callback_raises(exc=None):
    """Return an elicitation callback that raises the given exception (for testing error paths)."""
    _exc = exc if exc is not None else RuntimeError("elicit failed")

    async def callback(
        context: ServerRequestContext[ClientSession, Any],
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
            assert result.is_error is False, "Unexpected tool result"
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
            assert result.is_error is False, "Unexpected tool result"
            mock_pipefy_client.create_card.assert_not_called()

    @pytest.mark.parametrize(
        "client_session",
        [elicitation_callback_for(action="accept", content={})],
        indirect=True,
    )
    async def test_create_card_returns_friendly_error_for_malformed_form_fields(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
        extract_payload,
    ):
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": [{"label": "Status", "type": "select"}]
        }

        async with client_session as session:
            result = await session.call_tool("create_card", {"pipe_id": pipe_id})

        payload = extract_payload(result)
        assert payload.get("success") is False
        assert "interactive form" in tool_error_message(payload).lower()
        mock_pipefy_client.create_card.assert_not_called()

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
            assert result.is_error is False, "Unexpected tool result"
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

        mcp = build_tool_test_server(
            "Pipefy MCP Test Server", PipeTools.register, mock_pipefy_client
        )

        runtime = McpRuntime(settings, RequestScopedIdentity())
        runtime.session_for_request = lambda _req: mock_pipefy_client

        ctx = MagicMock()
        ctx.debug = AsyncMock()
        ctx.session = SimpleNamespace(client_params=SimpleNamespace())
        ctx.request_context = SimpleNamespace(lifespan_context=runtime, request=None)

        result = await mcp._tool_manager.call_tool(
            "create_card",
            {"pipe_id": pipe_id},
            context=ctx,
            convert_result=False,
        )

        mock_pipefy_client.create_card.assert_called_once_with(str(pipe_id), {})
        assert result["createCard"]["card"]["id"] == "789"
        assert "card_link" in result

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

            assert result.is_error is False, "Unexpected tool result"
            mock_pipefy_client.create_card.assert_called_once_with(
                str(pipe_id), {"field_1": "value_1"}
            )

    async def test_title_passed_to_create_card_on_create_card_input(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        """When title is provided, create_card passes title on CreateCardInput."""
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "789", "title": "Copa América"}}
        }

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {"pipe_id": pipe_id, "title": "Copa América"},
            )
            assert result.is_error is False
            mock_pipefy_client.create_card.assert_called_once_with(
                str(pipe_id), {}, title="Copa América"
            )
            mock_pipefy_client.update_card.assert_not_called()
            response = json.loads(result.content[0].text)
            assert response["createCard"]["card"]["title"] == "Copa América"
            assert "card_link" in response

    async def test_title_warning_when_response_title_mismatches(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        """When API stores a different title than requested, return title_warning."""
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "789", "title": "Derived from field"}}
        }

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {"pipe_id": pipe_id, "title": "My Title"},
            )
            assert result.is_error is False
            mock_pipefy_client.create_card.assert_called_once_with(
                str(pipe_id), {}, title="My Title"
            )
            mock_pipefy_client.update_card.assert_not_called()
            response = json.loads(result.content[0].text)
            assert response["createCard"]["card"]["title"] == "Derived from field"
            assert "title_warning" in response
            assert "not applied as expected" in response["title_warning"]
            assert "card_link" in response

    async def test_title_warning_skipped_when_create_card_null(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        """GraphQL null on createCard must not raise when checking title_warning."""
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.create_card.return_value = {"createCard": None}

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {"pipe_id": pipe_id, "title": "My Title"},
            )
            assert result.is_error is False
            response = json.loads(result.content[0].text)
            assert response == {"createCard": None}
            assert "title_warning" not in response
            assert "card_link" not in response

    async def test_no_title_warning_when_response_matches(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        """Titled create with matching API title must not emit title_warning."""
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "789", "title": "My Title"}}
        }

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {"pipe_id": pipe_id, "title": "My Title"},
            )
            assert result.is_error is False
            response = json.loads(result.content[0].text)
            assert response["createCard"]["card"]["title"] == "My Title"
            assert "title_warning" not in response

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
            assert result.is_error is False
            mock_pipefy_client.update_card.assert_not_called()

    async def test_permission_denied_enriches_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
        extract_payload,
    ):
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.create_card.side_effect = PipefyGraphQLError(
            [
                {
                    "message": "forbidden",
                    "extensions": {"code": "PERMISSION_DENIED"},
                }
            ]
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

    @pytest.mark.parametrize("exc_message", ["", "   "])
    async def test_create_card_empty_exception_message_uses_fallback(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
        extract_payload,
        exc_message,
    ):
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.create_card.side_effect = RuntimeError(exc_message)

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {"pipe_id": pipe_id, "skip_elicitation": True},
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        message = tool_error_message(payload)
        assert message.strip()
        assert message.startswith("Failed to create card.")
        assert "get_cards" in message or "get_phase_cards_count" in message
        assert "do not blind-retry" in message

    async def test_create_card_preserves_non_empty_exception_message(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
        extract_payload,
    ):
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.create_card.side_effect = RuntimeError("boom")

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {"pipe_id": pipe_id, "skip_elicitation": True},
            )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "boom" in tool_error_message(payload)

    @pytest.mark.parametrize("invalid_phase_id", [0, -1])
    async def test_create_card_rejects_invalid_phase_id(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
        invalid_phase_id,
        extract_payload,
    ):
        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {
                    "pipe_id": pipe_id,
                    "phase_id": invalid_phase_id,
                    "skip_elicitation": True,
                },
            )
        mock_pipefy_client.create_card.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False

    async def test_create_card_forwards_phase_id_with_skip_elicitation(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        """create_card with phase_id and skip_elicitation forwards phase_id to SDK."""
        phase_id = 987654321
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": []
        }
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": str(phase_id),
                "phase_name": "Target",
                "fields": [],
            }
        )
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "42"}}
        }

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {
                    "pipe_id": pipe_id,
                    "phase_id": phase_id,
                    "skip_elicitation": True,
                },
            )

        assert result.is_error is False
        mock_pipefy_client.create_card.assert_called_once_with(
            str(pipe_id), {}, phase_id=str(phase_id)
        )

    async def test_create_card_with_phase_id_filters_fields_via_get_phase_fields(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        """When phase_id is set, field keys are filtered via phase and start-form defs."""
        phase_id = 555666777
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": [
                {
                    "id": "sf1",
                    "label": "SF1",
                    "type": "short_text",
                    "editable": True,
                },
                {
                    "id": "sf_readonly",
                    "label": "SF RO",
                    "type": "short_text",
                    "editable": False,
                },
            ]
        }
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": str(phase_id),
                "phase_name": "Orphan",
                "fields": [
                    {
                        "id": "pf1",
                        "label": "PF1",
                        "type": "short_text",
                        "editable": True,
                    },
                    {
                        "id": "pf2",
                        "label": "PF2",
                        "type": "short_text",
                        "editable": False,
                    },
                ],
            }
        )
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "99"}}
        }

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {
                    "pipe_id": pipe_id,
                    "phase_id": phase_id,
                    "fields": {"pf1": "ok", "pf2": "ignored"},
                    "skip_elicitation": True,
                },
            )

        assert result.is_error is False
        mock_pipefy_client.get_start_form_fields.assert_called_once_with(
            str(pipe_id), False
        )
        mock_pipefy_client.get_phase_fields.assert_called_once_with(
            str(phase_id), False
        )
        mock_pipefy_client.create_card.assert_called_once_with(
            str(pipe_id), {"pf1": "ok"}, phase_id=str(phase_id)
        )

    async def test_create_card_with_phase_id_keeps_start_form_and_phase_fields(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
    ):
        """phase_id path must not drop start-form keys required by CreateCardInput."""
        phase_id = 555666778
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": [
                {
                    "id": "objetivo",
                    "label": "Objetivo",
                    "type": "long_text",
                    "editable": True,
                },
            ]
        }
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": str(phase_id),
                "phase_name": "Zona MCP",
                "fields": [
                    {
                        "id": "flag_de_teste",
                        "label": "Flag",
                        "type": "checklist_vertical",
                        "editable": True,
                    },
                ],
            }
        )
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "100"}}
        }

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {
                    "pipe_id": pipe_id,
                    "phase_id": phase_id,
                    "fields": {
                        "objetivo": "Smoke",
                        "flag_de_teste": "A",
                        "unknown": "drop",
                    },
                    "skip_elicitation": True,
                },
            )

        assert result.is_error is False
        mock_pipefy_client.create_card.assert_called_once_with(
            str(pipe_id),
            {"objetivo": "Smoke", "flag_de_teste": "A"},
            phase_id=str(phase_id),
        )


@pytest.mark.anyio
class TestGetPipeMembersTool:
    async def test_returns_members(self, client_session, mock_pipefy_client, pipe_id):
        async with client_session as session:
            mock_pipefy_client.get_pipe_members = AsyncMock(
                return_value={"pipe": {"members": []}}
            )
            result = await session.call_tool("get_pipe_members", {"pipe_id": pipe_id})

            assert result.is_error is False, "Unexpected tool result"
            mock_pipefy_client.get_pipe_members.assert_called_once_with(str(pipe_id))


@pytest.mark.anyio
class TestGetLabels:
    """Tests for get_labels tool (delegates to client.get_pipe)."""

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
        assert result.is_error is False
        mock_pipefy_client.get_pipe.assert_called_once_with(str(pipe_id))
        payload = extract_payload(result)
        assert payload == {
            "success": True,
            "message": "Labels loaded.",
            "labels": labels,
        }

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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["labels"] == []

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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["labels"] == []

    async def test_get_labels_pipe_null_returns_access_denied(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.get_pipe = AsyncMock(return_value={"pipe": None})
        async with client_session as session:
            result = await session.call_tool("get_labels", {"pipe_id": 999})
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "access denied" in tool_error_message(payload).lower()

    async def test_get_labels_get_pipe_exception_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.get_pipe.side_effect = PipefyGraphQLError(
            [
                {"message": "Denied", "extensions": {"code": "PERMISSION_DENIED"}},
            ]
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_labels", {"pipe_id": 1, "debug": False}
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload


@pytest.mark.anyio
class TestDirectToolCalls:
    """Direct tests for tools that simply forward params to the client."""

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
        assert result.is_error is False
        mock_pipefy_client.get_card.assert_called_once_with("123", include_fields=True)
        payload = extract_payload(result)
        assert payload["card"]["id"] == "123"

    async def test_get_pipe_forwards_pipe_id_to_client(
        self, client_session, mock_pipefy_client, pipe_id, extract_payload
    ):
        """get_pipe tool forwards pipe_id to client."""
        mock_pipefy_client.get_pipe = AsyncMock(
            return_value={"pipe": {"id": pipe_id, "name": "My Pipe"}}
        )
        async with client_session as session:
            result = await session.call_tool("get_pipe", {"pipe_id": pipe_id})
        assert result.is_error is False
        mock_pipefy_client.get_pipe.assert_called_once_with(str(pipe_id))
        payload = extract_payload(result)
        assert payload["pipe"]["name"] == "My Pipe"

    async def test_get_pipe_forwards_sdk_payload(
        self, client_session, mock_pipefy_client, extract_payload
    ):
        """get_pipe validates pipe_id and forwards the SDK response unchanged."""
        pipe_id = "306996634"
        sdk_payload = {
            "pipe": {
                "id": pipe_id,
                "name": "Inventory Pipe",
                "phases": [
                    {"id": "200", "name": "Doing", "cards_count": 4},
                ],
                "labels": [],
                "start_form_fields": [],
            }
        }
        mock_pipefy_client.get_pipe = AsyncMock(return_value=sdk_payload)
        async with client_session as session:
            result = await session.call_tool("get_pipe", {"pipe_id": pipe_id})
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload == sdk_payload

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
        assert result.is_error is False
        mock_pipefy_client.move_card_to_phase.assert_called_once_with("100", "200")

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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload.get("success") is False
        assert "99" in tool_error_message(payload)
        assert payload["valid_destinations"] == [{"id": "11", "name": "Done"}]

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
        assert result.is_error is True
        assert "forbidden" in (result.content[0].text if result.content else "")

    async def test_move_card_to_phase_returns_tool_error_for_required_field_when_dest_allowed(
        self, client_session, mock_pipefy_client, extract_payload
    ):
        """Required-field move failures become success:false (not a tool crash)."""
        api_msg = 'Field "Foo" is required! Please fill it and you\'ll be ready to go!'
        mock_pipefy_client.move_card_to_phase = AsyncMock(
            side_effect=PipefyGraphQLError([{"message": api_msg}])
        )
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
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "fields": [
                    {
                        "id": "slug-foo",
                        "internal_id": "123",
                        "label": "Foo",
                        "required": True,
                    },
                ]
            }
        )
        mock_pipefy_client.get_field_conditions = AsyncMock(
            return_value={
                "phase": {
                    "fieldConditions": [
                        {
                            "id": "fc-1",
                            "actions": [
                                {"phaseFieldId": "123", "actionId": "hide"},
                            ],
                        }
                    ]
                }
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "move_card_to_phase",
                {"card_id": 1, "destination_phase_id": 99},
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload.get("success") is False
        message = tool_error_message(payload)
        assert "Foo" in message
        assert "may be hidden by a field condition while still required" in message

    async def test_move_card_to_phase_required_field_without_hide_still_tool_error(
        self, client_session, mock_pipefy_client, extract_payload
    ):
        """Pattern match alone wraps the API message even when hide cross-check misses."""
        api_msg = 'Field "Foo" is required! Please fill it and you\'ll be ready to go!'
        mock_pipefy_client.move_card_to_phase = AsyncMock(
            side_effect=PipefyGraphQLError([{"message": api_msg}])
        )
        mock_pipefy_client.get_card = AsyncMock(
            return_value={
                "card": {"current_phase": {"id": "10", "name": "Doing"}},
            }
        )
        mock_pipefy_client.get_phase_allowed_move_targets = AsyncMock(
            return_value={
                "phase": {
                    "id": "10",
                    "cards_can_be_moved_to_phases": [
                        {"id": "99", "name": "Target"},
                    ],
                }
            }
        )
        mock_pipefy_client.get_phase_fields = AsyncMock(
            side_effect=RuntimeError("fields unavailable")
        )
        async with client_session as session:
            result = await session.call_tool(
                "move_card_to_phase",
                {"card_id": 1, "destination_phase_id": 99},
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload.get("success") is False
        message = tool_error_message(payload)
        assert "Foo" in message
        assert "hidden by a field condition" not in message

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
        assert result.is_error is False
        mock_pipefy_client.get_start_form_fields.assert_called_once_with(
            str(pipe_id), True
        )
        payload = extract_payload(result)
        assert "start_form_fields" in payload

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
        assert result.is_error is False
        mock_pipefy_client.update_comment.assert_called_once_with("456", "Updated text")
        payload = extract_payload(result)
        assert payload == {"success": True, "comment_id": "c_999"}

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
        assert result.is_error is False
        mock_pipefy_client.update_comment.assert_called_once_with("0", "hello")
        payload = extract_payload(result)
        assert payload == {"success": True, "comment_id": "c_999"}

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
        assert result.is_error is False
        mock_pipefy_client.update_comment.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    async def test_update_comment_text_over_max_length_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """update_comment with text > 1000 chars returns error payload without calling API."""
        from pipefy_sdk.models.comment import MAX_COMMENT_TEXT_LENGTH

        async with client_session as session:
            result = await session.call_tool(
                "update_comment",
                {"comment_id": 1, "text": "a" * (MAX_COMMENT_TEXT_LENGTH + 1)},
            )
        assert result.is_error is False
        mock_pipefy_client.update_comment.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    async def test_update_comment_api_exception_returns_mapped_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """When update_comment API raises, tool returns error payload with friendly message."""

        mock_pipefy_client.update_comment.side_effect = PipefyGraphQLError(
            [{"message": "Comment not found", "extensions": {"code": "NOT_FOUND"}}]
        )
        async with client_session as session:
            result = await session.call_tool(
                "update_comment",
                {"comment_id": 99999, "text": "hello"},
            )
        assert result.is_error is False
        mock_pipefy_client.update_comment.assert_called_once_with("99999", "hello")
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert "comment" in tool_error_message(
            payload
        ).lower() or "comment_id" in tool_error_message(payload)

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
        assert result.is_error is False
        mock_pipefy_client.delete_comment.assert_called_once_with("456")
        payload = extract_payload(result)
        assert payload == {"success": True}

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
        assert result.is_error is False
        mock_pipefy_client.delete_comment.assert_called_once_with("0")
        payload = extract_payload(result)
        assert payload == {"success": True}

    async def test_delete_comment_api_exception_returns_mapped_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """When delete_comment API raises, tool returns error payload with friendly message."""

        mock_pipefy_client.delete_comment.side_effect = PipefyGraphQLError(
            [
                {
                    "message": "Permission denied",
                    "extensions": {"code": "PERMISSION_DENIED"},
                }
            ]
        )
        async with client_session as session:
            result = await session.call_tool(
                "delete_comment",
                {"comment_id": 12345, "confirm": True},
            )
        assert result.is_error is False
        mock_pipefy_client.delete_comment.assert_called_once_with("12345")
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert "permission" in tool_error_message(payload).lower()

    async def test_delete_comment_comment_not_found_returns_mapped_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """When delete_comment API returns not found, tool returns friendly error payload."""

        mock_pipefy_client.delete_comment.side_effect = PipefyGraphQLError(
            [{"message": "Record not found", "extensions": {}}]
        )
        async with client_session as session:
            result = await session.call_tool(
                "delete_comment",
                {"comment_id": 99999, "confirm": True},
            )
        assert result.is_error is False
        mock_pipefy_client.delete_comment.assert_called_once_with("99999")
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert "comment" in tool_error_message(
            payload
        ).lower() or "not found" in tool_error_message(payload)

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
            assert preview.is_error is False
            mock_pipefy_client.delete_comment.assert_not_called()
            assert extract_payload(preview) == expected_preview

            result = await session.call_tool(
                "delete_comment",
                {"comment_id": comment_id, "confirm": True},
            )
        assert result.is_error is False
        mock_pipefy_client.delete_comment.assert_called_once_with(str(comment_id))
        assert extract_payload(result) == {"success": True}


@pytest.mark.anyio
class TestGetCardsTool:
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

        assert result.is_error is False, "Unexpected tool error"
        mock_pipefy_client.get_cards.assert_called_once_with(
            str(pipe_id), None, include_fields=True, first=None, after=None
        )

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

    async def test_get_cards_out_of_bounds_returns_invalid_arguments(
        self,
        client_session,
        mock_pipefy_client,
        pipe_id,
        extract_payload,
        envelope_flag,
    ):
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

        assert result.is_error is False
        mock_pipefy_client.get_cards.assert_called_once_with(
            str(pipe_id),
            {"title": "Copa"},
            include_fields=False,
            first=None,
            after=None,
        )

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

        assert result.is_error is False
        mock_pipefy_client.get_cards.assert_called_once_with(
            str(pipe_id),
            {"include_done": True, "title": "Copa"},
            include_fields=False,
            first=None,
            after=None,
        )


@pytest.mark.anyio
class TestFindCardsTool:
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

        assert result.is_error is False, "Unexpected tool error"
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

        assert result.is_error is False
        payload = extract_payload(result)
        assert payload.get("message") == FIND_CARDS_EMPTY_MESSAGE
        assert payload.get(FIND_CARDS_RESPONSE_KEY, {}).get("edges") == []

    async def test_find_cards_graphql_error_returns_enriched_envelope(
        self, client_session, mock_pipefy_client, pipe_id, extract_payload
    ):
        """Bad field_id (RESOURCE_NOT_FOUND) returns envelope with get_phase_fields hint."""

        mock_pipefy_client.find_cards = AsyncMock(
            side_effect=PipefyGraphQLError(
                [
                    {
                        "message": "Field not found with id: title",
                        "extensions": {"code": "RESOURCE_NOT_FOUND"},
                    }
                ]
            )
        )

        async with client_session as session:
            result = await session.call_tool(
                "find_cards",
                {
                    "pipe_id": pipe_id,
                    "field_id": "title",
                    "field_value": "anything",
                },
            )

        assert result.is_error is False, "Raw exception leaked instead of envelope"
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "get_phase_fields" in tool_error_message(payload)


@pytest.mark.anyio
class TestUpdateCardFieldTool:
    async def test_update_card_field_graphql_error_returns_enriched_envelope(
        self, client_session, mock_pipefy_client, extract_payload
    ):
        """Bad field_id slug returns envelope mentioning get_phase_fields, not raw exception."""

        mock_pipefy_client.update_card_field = AsyncMock(
            side_effect=PipefyGraphQLError(
                [
                    {
                        "message": "Field not found with id: nonexistent_slug_xyz",
                        "extensions": {"code": "RESOURCE_NOT_FOUND"},
                    }
                ]
            )
        )

        async with client_session as session:
            result = await session.call_tool(
                "update_card_field",
                {
                    "card_id": 12345,
                    "field_id": "nonexistent_slug_xyz",
                    "new_value": "x",
                },
            )

        assert result.is_error is False, "Raw exception leaked instead of envelope"
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "get_phase_fields" in tool_error_message(payload)


@pytest.mark.anyio
class TestAddCardCommentTool:
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

            assert result.is_error is False
            mock_pipefy_client.add_card_comment.assert_called_once_with(
                card_id="123", text="hello"
            )
            payload = extract_payload(result)
            assert payload == {"success": True, "comment_id": "c_987"}

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

            assert result.is_error is False
            mock_pipefy_client.add_card_comment.assert_called_once_with(
                card_id="0", text="hello"
            )
            payload = extract_payload(result)
            assert payload == {"success": True, "comment_id": "c_987"}

    async def test_api_exception_returns_mapped_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """When add_card_comment API raises, tool returns error payload with mapped message."""

        mock_pipefy_client.add_card_comment.side_effect = PipefyGraphQLError(
            [
                {
                    "message": "Record not found",
                    "extensions": {"code": "RESOURCE_NOT_FOUND"},
                }
            ]
        )
        async with client_session as session:
            result = await session.call_tool(
                "add_card_comment",
                {"card_id": 123, "text": "hello"},
            )
        assert result.is_error is False
        mock_pipefy_client.add_card_comment.assert_called_once_with(
            card_id="123", text="hello"
        )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
        assert "Card not found" in tool_error_message(
            payload
        ) or "card_id" in tool_error_message(payload)

    async def test_validation_error_text_over_limit_returns_explicit_length_message(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        """Comment text over max length surfaces cap and length, not generic card_id hint."""
        long_text = "a" * 1001
        async with client_session as session:
            result = await session.call_tool(
                "add_card_comment",
                {"card_id": 123, "text": long_text},
            )
        assert result.is_error is False
        mock_pipefy_client.add_card_comment.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        msg = tool_error_message(payload)
        assert "1000" in msg
        assert "got 1001" in msg


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

            assert result.is_error is False, "Unexpected tool error"
            mock_pipefy_client.get_phase_fields.assert_called_once_with(
                str(phase_id), required_only
            )
            response = extract_payload(result)
            assert response["phase_id"] == str(phase_id)
            assert response["phase_name"] == "In Progress"
            assert response["fields"] == mock_fields

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

            assert result.is_error is True, "Expected tool error for permission denied"
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

            assert result.is_error is False, "Unexpected tool error"
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

            assert result.is_error is False, "Unexpected tool error"
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

            assert result.is_error is False
            mock_pipefy_client.update_card.assert_not_called()
            response = extract_payload(result)
            assert response == tool_error("Phase field update cancelled by user.")

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

            assert result.is_error is False, "Unexpected tool error"
            mock_pipefy_client.update_card.assert_called_once_with(
                card_id=str(card_id),
                field_updates=[{"field_id": "status", "value": "completed"}],
            )

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

            assert result.is_error is False, "Unexpected tool error"
            mock_pipefy_client.update_card.assert_called_once_with(
                card_id=str(card_id),
                field_updates=[{"field_id": "status", "value": "completed"}],
            )

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

            assert result.is_error is False
            mock_pipefy_client.update_card.assert_not_called()
            response = extract_payload(result)
            assert response.get("message") == "No fields to update."

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

            assert result.is_error is True, "Expected tool error for permission denied"
            mock_pipefy_client.get_phase_fields.assert_called_once_with(
                str(phase_id), False
            )
            mock_pipefy_client.update_card.assert_not_called()


@pytest.mark.anyio
class TestUpdateCardTool:
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

            assert result.is_error is False, "Unexpected tool error"
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

            assert result.is_error is False
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

        assert result.is_error is False
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

            assert result.is_error is False
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

            assert result.is_error is False
            mock_pipefy_client.get_card.assert_not_called()
            mock_pipefy_client.delete_card.assert_not_called()

            payload = extract_payload(result)
            expected_payload = cast(
                DeleteCardErrorPayload,
                tool_error("Invalid 'card_id': provide a positive integer."),
            )
            assert payload == expected_payload

    async def test_resource_not_found_error_mapping(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        """Test delete_card tool maps RESOURCE_NOT_FOUND GraphQL exception to friendly message."""

        error = PipefyGraphQLError(
            [
                {
                    "message": "Card not found",
                    "extensions": {"code": "RESOURCE_NOT_FOUND"},
                }
            ]
        )
        mock_pipefy_client.get_card.side_effect = error

        async with client_session as session:
            result = await session.call_tool(
                "delete_card",
                {"card_id": 99999, "confirm": True},
            )

            assert result.is_error is False
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

    async def test_permission_denied_error_mapping(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        """Test delete_card tool maps PERMISSION_DENIED GraphQL exception to friendly message."""

        mock_pipefy_client.get_card.return_value = {
            "card": {
                "id": "12345",
                "title": "Test Card",
                "pipe": {"name": "Test Pipe"},
            }
        }

        error = PipefyGraphQLError(
            [
                {
                    "message": "Permission denied",
                    "extensions": {"code": "PERMISSION_DENIED"},
                }
            ]
        )
        mock_pipefy_client.delete_card.side_effect = error

        async with client_session as session:
            result = await session.call_tool(
                "delete_card",
                {"card_id": 12345, "confirm": True},
            )

            assert result.is_error is False
            mock_pipefy_client.delete_card.assert_called_once_with("12345")

            payload = extract_payload(result)
            expected_payload = cast(
                DeleteCardErrorPayload,
                tool_error(
                    "You don't have permission to delete card 12345. Please check your access permissions."
                ),
            )
            assert payload == expected_payload

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

            assert result.is_error is False
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

        assert result.is_error is False
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

            assert result.is_error is False
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
        assert result.is_error is False
        mock_pipefy_client.get_card.assert_called_once_with("12345")
        mock_pipefy_client.delete_card.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert payload["requires_confirmation"] is True

    async def test_debug_true_appends_codes_and_correlation_id_to_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        """When debug=True and client raises, error message includes codes and correlation_id."""

        error = PipefyGraphQLError(
            [
                {
                    "message": "Denied",
                    "extensions": {"code": "PERMISSION_DENIED"},
                }
            ]
        )
        mock_pipefy_client.get_card.return_value = {
            "card": {"id": "12345", "title": "Test Card", "pipe": {"name": "Test Pipe"}}
        }
        mock_pipefy_client.delete_card.side_effect = error
        async with client_session as session:
            result = await session.call_tool(
                "delete_card", {"card_id": 12345, "confirm": True, "debug": True}
            )
        assert result.is_error is False
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
        assert result.is_error is False
        mock_pipefy_client.get_card_relations.assert_called_once_with("555")
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["child_relations"] == child_rel
        assert payload["parent_relations"] == parent_rel

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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["child_relations"] == row
        assert payload["parent_relations"] == []

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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload == {
            "success": True,
            "message": "Card relations loaded.",
            "child_relations": [],
            "parent_relations": [],
        }

    async def test_graphql_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.get_card_relations.side_effect = PipefyGraphQLError(
            [
                {"message": "Not found", "extensions": {"code": "RESOURCE_NOT_FOUND"}},
            ]
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_card_relations", {"card_id": 1, "debug": False}
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

    async def test_card_null_returns_not_found(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.get_card_relations = AsyncMock(return_value={"card": None})
        async with client_session as session:
            result = await session.call_tool("get_card_relations", {"card_id": 42})
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "not found" in tool_error_message(payload).lower()


@pytest.mark.anyio
class TestDeleteCardRelation:
    """Tests for delete_card_relation tool."""

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
            assert preview.is_error is False
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
        assert result.is_error is False
        mock_pipefy_client.delete_card_relation.assert_called_once_with(
            str(child_id), str(parent_id), str(source_id)
        )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["message"] == "Card relation removed."

    async def test_api_exception_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.delete_card_relation.side_effect = PipefyGraphQLError(
            [
                {
                    "message": "Permission denied",
                    "extensions": {"code": "PERMISSION_DENIED"},
                }
            ]
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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload

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
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "did not succeed" in tool_error_message(payload).lower()


@pytest.mark.anyio
class TestPipefyIdCoercion:
    """PipefyId coerces int IDs to str at the tool boundary."""

    async def test_get_pipe_coerces_int_pipe_id(
        self, client_session, mock_pipefy_client, extract_payload
    ):
        mock_pipefy_client.get_pipe = AsyncMock(
            return_value={"pipe": {"id": "999", "name": "Test"}}
        )
        async with client_session as session:
            result = await session.call_tool("get_pipe", {"pipe_id": 999})
        assert result.is_error is False
        mock_pipefy_client.get_pipe.assert_called_once_with("999")

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
        assert result.is_error is False
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
        assert result.is_error is False
        # f2 is non-editable, so only f1 should be forwarded
        mock_pipefy_client.create_card.assert_called_once_with(
            str(pipe_id), {"f1": "a"}
        )

    async def test_create_card_skip_elicitation_returns_error_for_malformed_fields(
        self, client_session, mock_pipefy_client, pipe_id, extract_payload
    ):
        """skip_elicitation=True surfaces SDK field-definition validation errors."""
        from pipefy_sdk.models.field_definition import MalformedFieldDefinitionError

        mock_pipefy_client.get_start_form_fields.side_effect = (
            MalformedFieldDefinitionError(
                "Cannot return start form fields: 1 field definition(s) from Pipefy "
                "are missing required 'id' or 'type'. "
                "The pipe configuration may be incomplete or unsupported."
            )
        )

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {
                    "pipe_id": pipe_id,
                    "fields": {"status": "open"},
                    "skip_elicitation": True,
                },
            )

        payload = extract_payload(result)
        assert payload.get("success") is False
        assert "return start form fields" in tool_error_message(payload).lower()
        mock_pipefy_client.create_card.assert_not_called()

    @pytest.mark.parametrize("exc_message", ["", "   "])
    async def test_create_card_malformed_fields_empty_message_uses_fallback(
        self, client_session, mock_pipefy_client, pipe_id, extract_payload, exc_message
    ):
        from pipefy_sdk.models.field_definition import MalformedFieldDefinitionError

        mock_pipefy_client.get_start_form_fields.side_effect = (
            MalformedFieldDefinitionError(exc_message)
        )

        async with client_session as session:
            result = await session.call_tool(
                "create_card",
                {
                    "pipe_id": pipe_id,
                    "fields": {"status": "open"},
                    "skip_elicitation": True,
                },
            )

        payload = extract_payload(result)
        assert payload.get("success") is False
        message = tool_error_message(payload)
        assert message.strip()
        assert "Invalid field definition." in message
        assert "do not blind-retry" in message
        mock_pipefy_client.create_card.assert_not_called()

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
        assert result.is_error is False
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
        assert result.is_error is False
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
        assert result.is_error is False
        # Elicitation accepted with "approved"
        mock_pipefy_client.update_card.assert_called_once_with(
            card_id="99",
            field_updates=[{"field_id": "status", "value": "approved"}],
        )


@pytest.mark.anyio
class TestElicitationWithoutABackChannel:
    """Elicitation must degrade, not escape, when the client cannot be called.

    A default ``Client`` negotiates 2026-07-28, which has no server-to-client
    channel: the client still advertises the ``elicitation`` capability in its
    request envelope, but ``ctx.elicit`` raises ``NoBackChannelError``. Gating on
    the advertised capability alone let that raise leave the tool as a JSON-RPC
    protocol error instead of a tool result. Each tool must instead take the same
    path it takes for a client that advertises no elicitation at all: use the
    values it was given.
    """

    @staticmethod
    def _modern_session(mcp_server):
        return create_client_session(
            mcp_server,
            mode="auto",
            read_timeout_seconds=timedelta(seconds=10),
            raise_exceptions=True,
            elicitation_callback=elicitation_callback_for(
                action="accept", content={"f1": "from-elicitation"}
            ),
        )

    async def test_create_card_uses_supplied_fields(
        self, mcp_server, mock_pipefy_client, pipe_id
    ):
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
            "createCard": {"card": {"id": "12"}}
        }

        async with self._modern_session(mcp_server) as session:
            assert session.protocol_version == "2026-07-28"
            result = await session.call_tool(
                "create_card",
                {"pipe_id": pipe_id, "fields": {"f1": "from-arguments"}},
            )

        assert result.is_error is False
        mock_pipefy_client.create_card.assert_called_once_with(
            str(pipe_id), {"f1": "from-arguments"}
        )

    async def test_create_card_with_phase_id_uses_supplied_fields(
        self, mcp_server, mock_pipefy_client, pipe_id
    ):
        field = {
            "id": "f1",
            "label": "F1",
            "type": "short_text",
            "required": False,
            "editable": True,
        }
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": [field]
        }
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={"phase_id": "100", "phase_name": "Review", "fields": [field]}
        )
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "13"}}
        }

        async with self._modern_session(mcp_server) as session:
            result = await session.call_tool(
                "create_card",
                {
                    "pipe_id": pipe_id,
                    "phase_id": "100",
                    "fields": {"f1": "from-arguments"},
                },
            )

        assert result.is_error is False
        mock_pipefy_client.create_card.assert_called_once_with(
            str(pipe_id), {"f1": "from-arguments"}, phase_id="100"
        )

    async def test_fill_card_phase_fields_uses_supplied_fields(
        self, mcp_server, mock_pipefy_client
    ):
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": "100",
                "phase_name": "Review",
                "fields": [
                    {
                        "id": "f1",
                        "label": "F1",
                        "type": "short_text",
                        "required": False,
                        "editable": True,
                    },
                ],
            }
        )
        mock_pipefy_client.update_card = AsyncMock(
            return_value={"updateFieldsValues": {"success": True}}
        )

        async with self._modern_session(mcp_server) as session:
            result = await session.call_tool(
                "fill_card_phase_fields",
                {
                    "card_id": "99",
                    "phase_id": "100",
                    "fields": {"f1": "from-arguments"},
                },
            )

        assert result.is_error is False
        mock_pipefy_client.update_card.assert_called_once_with(
            card_id="99",
            field_updates=[{"field_id": "f1", "value": "from-arguments"}],
        )

    async def test_create_card_without_fields_sends_no_values(
        self, mcp_server, mock_pipefy_client, pipe_id, extract_payload
    ):
        """The uncovered corner: no form, a required field, and no ``fields``.

        The other cases in this class supply ``fields``, so they cannot show what
        happens when there is nothing to fall back to. ``create_card`` sends an
        empty field map and lets the API rule on its own required fields; it does
        not pre-empt that check locally. Pinned so a change to either half (a
        local required-field guard, or a different fallback) is deliberate.
        """
        mock_pipefy_client.get_start_form_fields.return_value = {
            "start_form_fields": [
                {
                    "id": "f_req",
                    "label": "Required",
                    "type": "short_text",
                    "required": True,
                    "editable": True,
                },
            ]
        }
        mock_pipefy_client.create_card.return_value = {
            "createCard": {"card": {"id": "77"}}
        }

        async with self._modern_session(mcp_server) as session:
            result = await session.call_tool("create_card", {"pipe_id": pipe_id})

        assert result.is_error is False
        mock_pipefy_client.create_card.assert_called_once_with(str(pipe_id), {})
        assert extract_payload(result)["createCard"]["card"]["id"] == "77"

    async def test_fill_card_phase_fields_without_fields_reports_nothing_collected(
        self, mcp_server, mock_pipefy_client, extract_payload
    ):
        """Same corner on the sibling tool, where the API never gets a say.

        ``fill_card_phase_fields`` short-circuits before ``update_card`` when
        nothing was collected, so the message is the only thing a caller reads.
        "No fields to update." would be false here: the phase has a required
        editable field and no form could be shown to collect it.
        """
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "phase_id": "100",
                "phase_name": "Review",
                "fields": [
                    {
                        "id": "f_req",
                        "label": "Required",
                        "type": "short_text",
                        "required": True,
                        "editable": True,
                    },
                ],
            }
        )
        mock_pipefy_client.update_card = AsyncMock()

        async with self._modern_session(mcp_server) as session:
            result = await session.call_tool(
                "fill_card_phase_fields", {"card_id": "99", "phase_id": "100"}
            )

        assert result.is_error is False
        mock_pipefy_client.update_card.assert_not_called()
        payload = extract_payload(result)
        assert payload["message"] != "No fields to update."
        assert "nothing was updated" in payload["message"]
        assert "1 editable field(s)" in payload["message"]

    async def test_elicit_raising_no_back_channel_is_absorbed(
        self, mock_pipefy_client, pipe_id
    ):
        """The residual case: the channel closes after the capability check.

        ``supports_elicitation`` reads ``can_send_request`` at the top of the
        tool, but the channel can close before the elicitation request goes out
        (the inbound request finishing closes its dispatch context), and a
        session shape that does not expose the flag passes the check unmeasured.
        Here the check is satisfied and ``ctx.elicit`` still raises.
        """
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
            "createCard": {"card": {"id": "14"}}
        }

        mcp = build_tool_test_server(
            "Pipefy MCP Test Server", PipeTools.register, mock_pipefy_client
        )
        runtime = McpRuntime(settings, RequestScopedIdentity())
        runtime.session_for_request = lambda _req: mock_pipefy_client

        ctx = MagicMock()
        ctx.debug = AsyncMock()
        ctx.elicit = AsyncMock(side_effect=NoBackChannelError("elicitation/create"))
        ctx.session = SimpleNamespace(
            client_params=SimpleNamespace(
                capabilities=SimpleNamespace(elicitation=True)
            ),
            can_send_request=True,
        )
        ctx.request_context = SimpleNamespace(lifespan_context=runtime, request=None)

        result = await mcp._tool_manager.call_tool(
            "create_card",
            {"pipe_id": pipe_id, "fields": {"f1": "from-arguments"}},
            context=ctx,
            convert_result=False,
        )

        ctx.elicit.assert_awaited_once()
        mock_pipefy_client.create_card.assert_called_once_with(
            str(pipe_id), {"f1": "from-arguments"}
        )
        assert result["createCard"]["card"]["id"] == "14"


# =============================================================================
# structured_output=False on comment/card mutation tools
# =============================================================================
#
# These four tools used TypedDict return annotations, which the SDK auto-detects
# as structured output. The resulting ``CallToolResult`` carried a
# ``structuredContent`` field that MCP clients surface wrapped in ``{"result":
# {...}}`` — visually different from the 13 other ``delete_*`` tools that
# return plain ``dict[str, Any]``. We disable structured output on the four
# outliers so all comment/card/delete tools share the same envelope shape.


@pytest.mark.anyio
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
    The SDK otherwise generates when a tool declares structured output."""
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
    assert result.is_error is False
    # The tool body returns a plain success dict; structured_output=False
    # means no structuredContent is emitted on the MCP protocol side.
    assert result.structured_content is None
