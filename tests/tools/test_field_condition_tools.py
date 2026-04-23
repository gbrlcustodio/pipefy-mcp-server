from pipefy_mcp.tools.tool_error_envelope import tool_error_message

"""Unit tests for field condition read tools (get_field_conditions, get_field_condition)."""

from datetime import timedelta
from random import randint
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.field_condition_tools import FieldConditionTools


@pytest.fixture
def mock_pipefy_client():
    client = MagicMock(PipefyClient)
    client.get_field_conditions = AsyncMock()
    client.get_field_condition = AsyncMock()
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
def mcp_server(mock_pipefy_client):
    mcp = FastMCP("Field Condition Tools Test")
    FieldConditionTools.register(mcp, mock_pipefy_client)
    return mcp


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
        assert result.isError is False
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
        assert result.isError is False
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
        from gql.transport.exceptions import TransportQueryError

        mock_pipefy_client.get_field_conditions.side_effect = TransportQueryError(
            "GraphQL Error",
            errors=[
                {"message": "Denied", "extensions": {"code": "PERMISSION_DENIED"}},
            ],
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_field_conditions", {"phase_id": 1, "debug": False}
            )
        assert result.isError is False
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
        assert result.isError is False
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
        assert result.isError is False
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
        from gql.transport.exceptions import TransportQueryError

        mock_pipefy_client.get_field_condition.side_effect = TransportQueryError(
            "GraphQL Error",
            errors=[
                {"message": "Not found", "extensions": {"code": "RESOURCE_NOT_FOUND"}},
            ],
        )
        async with client_session as session:
            result = await session.call_tool(
                "get_field_condition", {"field_condition_id": "x", "debug": False}
            )
        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "error" in payload
