"""Unit tests for field condition MCP tools (read + create verify)."""

from datetime import timedelta
from random import randint
from unittest.mock import AsyncMock, MagicMock

import pytest
from _mcp_compat import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import PipefyClient, PipefyGraphQLError

from pipefy_mcp.core.tool_error_envelope import tool_error_message
from pipefy_mcp.tools.field_condition_tools import FieldConditionTools
from tools.conftest import build_tool_test_server

_MINIMAL_CREATE_CONDITION = {
    "expressions": [
        {
            "structure_id": 0,
            "field_address": "425848636",
            "operation": "equals",
            "value": "Option A",
        }
    ],
    "expressions_structure": [[0]],
}
_MINIMAL_CREATE_ACTIONS = [{"phaseFieldId": "425848637", "actionId": "hide"}]


@pytest.fixture
def mock_pipefy_client():
    client = MagicMock(PipefyClient)
    client.get_field_conditions = AsyncMock()
    client.get_field_condition = AsyncMock()
    client.create_field_condition = AsyncMock()
    client.update_field_condition = AsyncMock()
    client.get_phase_fields = AsyncMock(return_value={"fields": []})
    return client


@pytest.fixture
def mcp_server(mock_pipefy_client):
    return build_tool_test_server(
        "Field Condition Tools Test",
        FieldConditionTools.register,
        mock_pipefy_client,
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
def phase_id() -> int:
    return randint(1, 10000)


@pytest.mark.anyio
class TestGetFieldConditions:
    """Tests for get_field_conditions tool."""

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_field_conditions_success_returns_list(
        self,
        client_session,
        mock_pipefy_client,
        phase_id,
        extract_payload,
    ) -> None:
        rows = [
            {
                "id": "fc-1",
                "name": "Rule A",
                "condition": {"expressions": []},
                "actions": [{"phaseFieldId": "pf-1"}],
            },
        ]
        mock_pipefy_client.get_field_conditions = AsyncMock(
            return_value={"phase": {"id": str(phase_id), "fieldConditions": rows}}
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_field_conditions", {"phase_id": phase_id}
            )
        assert result.is_error is False
        mock_pipefy_client.get_field_conditions.assert_called_once_with(str(phase_id))
        payload = extract_payload(result)
        assert payload == {
            "success": True,
            "message": "Field conditions loaded.",
            "field_conditions": rows,
        }

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_field_conditions_empty_returns_empty_list(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.get_field_conditions = AsyncMock(
            return_value={"phase": {"id": "1", "fieldConditions": []}}
        )
        async with client_session as session:
            result = await session.call_tool("get_field_conditions", {"phase_id": 1})
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["field_conditions"] == []

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_field_conditions_graphql_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.get_field_conditions.side_effect = PipefyGraphQLError(
            [
                {"message": "Denied", "extensions": {"code": "PERMISSION_DENIED"}},
            ]
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_field_conditions", {"phase_id": 1, "debug": False}
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload


@pytest.mark.anyio
class TestGetFieldCondition:
    """Tests for get_field_condition tool."""

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_field_condition_success_returns_object(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        fc = {
            "id": "fc-9",
            "name": "Rule Z",
            "phase": {"id": "10", "name": "Start"},
            "condition": {"expressions": []},
            "actions": [],
        }
        mock_pipefy_client.get_field_condition = AsyncMock(
            return_value={"fieldCondition": fc}
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_field_condition", {"field_condition_id": "fc-9"}
            )
        assert result.is_error is False
        mock_pipefy_client.get_field_condition.assert_called_once_with("fc-9")
        payload = extract_payload(result)
        assert payload == {
            "success": True,
            "message": "Field condition loaded.",
            "field_condition": fc,
        }

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_field_condition_not_found_returns_error(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.get_field_condition = AsyncMock(
            return_value={"fieldCondition": None}
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_field_condition", {"field_condition_id": 999}
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "access denied" in tool_error_message(payload).lower()

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_get_field_condition_graphql_error_returns_error_payload(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ) -> None:
        mock_pipefy_client.get_field_condition.side_effect = PipefyGraphQLError(
            [
                {"message": "Not found", "extensions": {"code": "RESOURCE_NOT_FOUND"}},
            ]
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_field_condition", {"field_condition_id": "x", "debug": False}
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload


@pytest.mark.anyio
class TestCreateFieldConditionVerify:
    """Post-create read-back honesty for create_field_condition."""

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_create_field_condition_verified_when_phase_matches(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        phase_id = "342182326"
        cid = "fc-ok"
        mock_pipefy_client.create_field_condition = AsyncMock(
            return_value={"createFieldCondition": {"fieldCondition": {"id": cid}}}
        )
        mock_pipefy_client.get_field_condition = AsyncMock(
            return_value={
                "fieldCondition": {
                    "id": cid,
                    "phase": {"id": phase_id, "name": "Inbox"},
                }
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "create_field_condition",
                {
                    "phase_id": phase_id,
                    "condition": _MINIMAL_CREATE_CONDITION,
                    "actions": _MINIMAL_CREATE_ACTIONS,
                    "name": "Hide brief",
                },
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["condition_id"] == cid
        assert payload["verified"] is True
        mock_pipefy_client.get_field_conditions.assert_not_called()

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_create_field_condition_wrong_phase_returns_failure(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        phase_id = "342182326"
        cid = "fc-wrong"
        mock_pipefy_client.create_field_condition = AsyncMock(
            return_value={"createFieldCondition": {"fieldCondition": {"id": cid}}}
        )
        mock_pipefy_client.get_field_condition = AsyncMock(
            return_value={
                "fieldCondition": {
                    "id": cid,
                    "phase": {"id": "999000111", "name": "Start form"},
                }
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "create_field_condition",
                {
                    "phase_id": phase_id,
                    "condition": _MINIMAL_CREATE_CONDITION,
                    "actions": _MINIMAL_CREATE_ACTIONS,
                    "name": "Hide brief",
                },
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        message = tool_error_message(payload)
        assert phase_id in message
        assert cid in message

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_create_field_condition_missing_when_list_lacks_id(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        phase_id = "342182326"
        cid = "fc-ghost"
        mock_pipefy_client.create_field_condition = AsyncMock(
            return_value={"createFieldCondition": {"fieldCondition": {"id": cid}}}
        )
        mock_pipefy_client.get_field_condition = AsyncMock(
            side_effect=PipefyGraphQLError([{"message": "Not found"}])
        )
        mock_pipefy_client.get_field_conditions = AsyncMock(
            return_value={
                "phase": {
                    "id": phase_id,
                    "fieldConditions": [{"id": "fc-other"}],
                }
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "create_field_condition",
                {
                    "phase_id": phase_id,
                    "condition": _MINIMAL_CREATE_CONDITION,
                    "actions": _MINIMAL_CREATE_ACTIONS,
                    "name": "Hide brief",
                },
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        message = tool_error_message(payload)
        assert "did not persist" in message.lower()
        assert cid in message
        assert phase_id in message

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_create_field_condition_verify_unavailable_returns_warning(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        phase_id = "342182326"
        cid = "fc-unverified"
        mock_pipefy_client.create_field_condition = AsyncMock(
            return_value={"createFieldCondition": {"fieldCondition": {"id": cid}}}
        )
        mock_pipefy_client.get_field_condition = AsyncMock(
            side_effect=RuntimeError("network down")
        )
        mock_pipefy_client.get_field_conditions = AsyncMock(
            side_effect=RuntimeError("network down")
        )
        async with client_session as session:
            result = await session.call_tool(
                "create_field_condition",
                {
                    "phase_id": phase_id,
                    "condition": _MINIMAL_CREATE_CONDITION,
                    "actions": _MINIMAL_CREATE_ACTIONS,
                    "name": "Hide brief",
                },
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["condition_id"] == cid
        assert "verified" not in payload
        assert "could not verify" in payload["warning"].lower()


@pytest.mark.anyio
class TestRequiredHiddenLint:
    """Block create/update when hide targets a required field."""

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_create_required_hidden_blocks_before_mutation(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        phase_id = "342182326"
        field_id = "425848637"
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "fields": [
                    {
                        "id": "brief",
                        "internal_id": field_id,
                        "required": True,
                    }
                ]
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "create_field_condition",
                {
                    "phase_id": phase_id,
                    "condition": _MINIMAL_CREATE_CONDITION,
                    "actions": [{"phaseFieldId": field_id, "actionId": "hide"}],
                    "name": "Hide brief",
                },
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert payload["error"]["code"] == "INVALID_ARGUMENTS"
        message = tool_error_message(payload)
        assert field_id in message
        assert "required" in message.lower()
        mock_pipefy_client.create_field_condition.assert_not_called()
        mock_pipefy_client.get_phase_fields.assert_awaited_once_with(phase_id)

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_create_required_hidden_legacy_action_id_blocks_before_mutation(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        phase_id = "342182326"
        field_id = "425848637"
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "fields": [
                    {
                        "id": "brief",
                        "internal_id": field_id,
                        "required": True,
                    }
                ]
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "create_field_condition",
                {
                    "phase_id": phase_id,
                    "condition": _MINIMAL_CREATE_CONDITION,
                    "actions": [{"phaseFieldId": field_id, "actionId": "hidden"}],
                    "name": "Hide brief",
                },
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert payload["error"]["code"] == "INVALID_ARGUMENTS"
        assert field_id in tool_error_message(payload)
        mock_pipefy_client.create_field_condition.assert_not_called()

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_required_hidden_blocks_before_mutation(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        condition_id = "fc-7"
        phase_id = "342182326"
        field_id = "425848637"
        mock_pipefy_client.get_field_condition = AsyncMock(
            return_value={
                "fieldCondition": {
                    "id": condition_id,
                    "phase": {"id": phase_id, "name": "Inbox"},
                }
            }
        )
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "fields": [
                    {
                        "id": "brief",
                        "internal_id": field_id,
                        "required": True,
                    }
                ]
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "update_field_condition",
                {
                    "condition_id": condition_id,
                    "actions": [{"phaseFieldId": field_id, "actionId": "hide"}],
                },
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert payload["error"]["code"] == "INVALID_ARGUMENTS"
        assert field_id in tool_error_message(payload)
        mock_pipefy_client.update_field_condition.assert_not_called()
        mock_pipefy_client.get_field_condition.assert_awaited_once_with(condition_id)
        mock_pipefy_client.get_phase_fields.assert_awaited_once_with(phase_id)

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_required_hidden_legacy_action_id_blocks_before_mutation(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        condition_id = "fc-7"
        phase_id = "342182326"
        field_id = "425848637"
        mock_pipefy_client.get_field_condition = AsyncMock(
            return_value={
                "fieldCondition": {
                    "id": condition_id,
                    "phase": {"id": phase_id, "name": "Inbox"},
                }
            }
        )
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "fields": [
                    {
                        "id": "brief",
                        "internal_id": field_id,
                        "required": True,
                    }
                ]
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "update_field_condition",
                {
                    "condition_id": condition_id,
                    "actions": [{"phaseFieldId": field_id, "actionId": "hidden"}],
                },
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert payload["error"]["code"] == "INVALID_ARGUMENTS"
        assert field_id in tool_error_message(payload)
        mock_pipefy_client.update_field_condition.assert_not_called()

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_create_no_required_hidden_conflict_proceeds(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        phase_id = "342182326"
        cid = "fc-ok"
        field_id = "425848637"
        mock_pipefy_client.get_phase_fields = AsyncMock(
            return_value={
                "fields": [
                    {
                        "id": "brief",
                        "internal_id": field_id,
                        "required": False,
                    }
                ]
            }
        )
        mock_pipefy_client.create_field_condition = AsyncMock(
            return_value={"createFieldCondition": {"fieldCondition": {"id": cid}}}
        )
        mock_pipefy_client.get_field_condition = AsyncMock(
            return_value={
                "fieldCondition": {
                    "id": cid,
                    "phase": {"id": phase_id, "name": "Inbox"},
                }
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "create_field_condition",
                {
                    "phase_id": phase_id,
                    "condition": _MINIMAL_CREATE_CONDITION,
                    "actions": [{"phaseFieldId": field_id, "actionId": "hide"}],
                    "name": "Hide brief",
                },
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["verified"] is True
        mock_pipefy_client.create_field_condition.assert_awaited_once()

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_create_phase_fields_error_proceeds_best_effort(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        phase_id = "342182326"
        cid = "fc-ok"
        mock_pipefy_client.get_phase_fields = AsyncMock(
            side_effect=RuntimeError("phase fields unavailable")
        )
        mock_pipefy_client.create_field_condition = AsyncMock(
            return_value={"createFieldCondition": {"fieldCondition": {"id": cid}}}
        )
        mock_pipefy_client.get_field_condition = AsyncMock(
            return_value={
                "fieldCondition": {
                    "id": cid,
                    "phase": {"id": phase_id, "name": "Inbox"},
                }
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "create_field_condition",
                {
                    "phase_id": phase_id,
                    "condition": _MINIMAL_CREATE_CONDITION,
                    "actions": _MINIMAL_CREATE_ACTIONS,
                    "name": "Hide brief",
                },
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is True
        mock_pipefy_client.create_field_condition.assert_awaited_once()

    @pytest.mark.parametrize("client_session", [None], indirect=True)
    async def test_update_phase_fields_error_proceeds_best_effort(
        self,
        client_session,
        mock_pipefy_client,
        extract_payload,
    ):
        condition_id = "fc-ok"
        phase_id = "342182326"
        field_id = "425848637"
        mock_pipefy_client.get_field_condition = AsyncMock(
            return_value={
                "fieldCondition": {
                    "id": condition_id,
                    "phase": {"id": phase_id, "name": "Inbox"},
                }
            }
        )
        mock_pipefy_client.get_phase_fields = AsyncMock(
            side_effect=RuntimeError("phase fields unavailable")
        )
        mock_pipefy_client.update_field_condition = AsyncMock(
            return_value={
                "updateFieldCondition": {"fieldCondition": {"id": condition_id}}
            }
        )
        async with client_session as session:
            result = await session.call_tool(
                "update_field_condition",
                {
                    "condition_id": condition_id,
                    "actions": [{"phaseFieldId": field_id, "actionId": "hide"}],
                },
            )
        assert result.is_error is False
        payload = extract_payload(result)
        assert payload["success"] is True
        mock_pipefy_client.update_field_condition.assert_awaited_once()
        mock_pipefy_client.get_phase_fields.assert_awaited_once_with(phase_id)
