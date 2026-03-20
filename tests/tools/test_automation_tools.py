"""Tests for traditional automation MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.automation_tools import AutomationTools


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_automation_client():
    client = MagicMock(PipefyClient)
    client.get_automation = AsyncMock()
    client.get_automations = AsyncMock()
    client.get_automation_actions = AsyncMock()
    client.get_automation_events = AsyncMock()
    client.create_automation = AsyncMock()
    client.update_automation = AsyncMock()
    client.delete_automation = AsyncMock()
    return client


@pytest.fixture
def automation_mcp_server(mock_automation_client):
    mcp = FastMCP("Automation Tools Test")
    AutomationTools.register(mcp, mock_automation_client)
    return mcp


@pytest.fixture
def automation_session(automation_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        automation_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_success(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.get_automation.return_value = {
        "id": "a1",
        "name": "Rule",
        "active": True,
    }

    async with automation_session as session:
        result = await session.call_tool("get_automation", {"automation_id": "a1"})

    assert result.isError is False
    mock_automation_client.get_automation.assert_awaited_once_with("a1")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"] == mock_automation_client.get_automation.return_value


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_graphql_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.get_automation.side_effect = TransportQueryError(
        "failed", errors=[{"message": "not found"}]
    )

    async with automation_session as session:
        result = await session.call_tool("get_automation", {"automation_id": "x"})

    assert result.isError is False
    p = extract_payload(result)
    assert p["success"] is False
    assert "not found" in p["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_not_found_returns_empty_data_and_message(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.get_automation.return_value = {}

    async with automation_session as session:
        result = await session.call_tool("get_automation", {"automation_id": "999"})

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"] == {}
    assert "No automation found" in payload["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_rejects_empty_automation_id(
    automation_session, mock_automation_client, extract_payload
):
    async with automation_session as session:
        result = await session.call_tool("get_automation", {"automation_id": ""})

    mock_automation_client.get_automation.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "automation_id" in p["error"].lower()


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_rejects_non_positive_int_id(
    automation_session, mock_automation_client, extract_payload
):
    async with automation_session as session:
        result = await session.call_tool("get_automation", {"automation_id": -1})

    mock_automation_client.get_automation.assert_not_called()
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automations_rejects_empty_string_filters(
    automation_session, mock_automation_client, extract_payload
):
    async with automation_session as session:
        result = await session.call_tool(
            "get_automations",
            {"organization_id": "", "pipe_id": ""},
        )

    mock_automation_client.get_automations.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "organization_id" in p["error"].lower()


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_rejects_empty_name(
    automation_session, mock_automation_client, extract_payload
):
    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "",
                "trigger_id": "e1",
                "action_id": "a1",
            },
        )

    mock_automation_client.create_automation.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "name" in p["error"].lower()


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_rejects_non_dict_extra_input(
    automation_session, mock_automation_client, extract_payload
):
    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "Rule",
                "trigger_id": "e1",
                "action_id": "a1",
                "extra_input": "not_a_dict",
            },
        )

    mock_automation_client.create_automation.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "extra_input" in p["error"].lower()
    assert "dict" in p["error"].lower()


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_delete_automation_rejects_invalid_id(
    automation_session, mock_automation_client, extract_payload
):
    async with automation_session as session:
        result = await session.call_tool("delete_automation", {"automation_id": -5})

    mock_automation_client.delete_automation.assert_not_called()
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automations_success(
    automation_session, mock_automation_client, extract_payload
):
    rows = [{"id": "1", "name": "R1", "active": True}]
    mock_automation_client.get_automations.return_value = rows

    async with automation_session as session:
        result = await session.call_tool(
            "get_automations", {"organization_id": None, "pipe_id": "p9"}
        )

    assert result.isError is False
    mock_automation_client.get_automations.assert_awaited_once_with(
        organization_id=None, pipe_id="p9"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"] == rows


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automations_graphql_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.get_automations.side_effect = TransportQueryError(
        "failed", errors=[{"message": "denied"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "get_automations",
            {"pipe_id": "bad"},
        )

    assert extract_payload(result)["success"] is False
    assert "denied" in extract_payload(result)["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_actions_success(
    automation_session, mock_automation_client, extract_payload
):
    actions = [{"id": "act1", "label": "Email"}]
    mock_automation_client.get_automation_actions.return_value = actions

    async with automation_session as session:
        result = await session.call_tool(
            "get_automation_actions", {"pipe_id": "pipe-1"}
        )

    assert result.isError is False
    mock_automation_client.get_automation_actions.assert_awaited_once_with("pipe-1")
    assert extract_payload(result)["success"] is True
    assert extract_payload(result)["data"] == actions


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_actions_graphql_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.get_automation_actions.side_effect = TransportQueryError(
        "failed", errors=[{"message": "bad pipe"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "get_automation_actions",
            {"pipe_id": "x"},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_events_success(
    automation_session, mock_automation_client, extract_payload
):
    events = [{"id": "e1", "label": "Done"}]
    mock_automation_client.get_automation_events.return_value = events

    async with automation_session as session:
        result = await session.call_tool("get_automation_events", {"pipe_id": "pipe-2"})

    assert result.isError is False
    mock_automation_client.get_automation_events.assert_awaited_once_with("pipe-2")
    assert extract_payload(result)["success"] is True
    assert extract_payload(result)["data"] == events


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_events_graphql_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.get_automation_events.side_effect = TransportQueryError(
        "failed", errors=[{"message": "nope"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "get_automation_events",
            {"pipe_id": "y"},
        )

    assert extract_payload(result)["success"] is False
    assert "nope" in extract_payload(result)["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_read_automation_tools_have_read_only_hint(automation_session):
    async with automation_session as session:
        listed = await session.list_tools()
    names = {
        "get_automation",
        "get_automations",
        "get_automation_actions",
        "get_automation_events",
    }
    by_name = {t.name: t for t in listed.tools}
    for name in names:
        tool = by_name[name]
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_success(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.create_automation.return_value = {
        "createAutomation": {
            "automation": {"id": "a-new", "name": "Notify", "active": True},
        },
    }

    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "Notify",
                "trigger_id": "evt-1",
                "action_id": "act-1",
                "active": True,
                "extra_input": None,
                "debug": False,
            },
        )

    assert result.isError is False
    mock_automation_client.create_automation.assert_awaited_once_with(
        "p1",
        "Notify",
        "evt-1",
        "act-1",
        active=True,
        extra_input=None,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["automation"] == {
        "id": "a-new",
        "name": "Notify",
        "active": True,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.create_automation.side_effect = TransportQueryError(
        "failed", errors=[{"message": "invalid event"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "N",
                "trigger_id": "e",
                "action_id": "a",
            },
        )

    assert extract_payload(result)["success"] is False
    assert "invalid event" in extract_payload(result)["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_update_automation_success(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.update_automation.return_value = {
        "updateAutomation": {
            "automation": {"id": "a7", "name": "Renamed", "active": False},
        },
    }

    async with automation_session as session:
        result = await session.call_tool(
            "update_automation",
            {
                "automation_id": "a7",
                "extra_input": {"name": "Renamed"},
                "debug": False,
            },
        )

    assert result.isError is False
    mock_automation_client.update_automation.assert_awaited_once_with(
        "a7",
        extra_input={"name": "Renamed"},
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["automation"]["id"] == "a7"
    assert payload["automation"]["name"] == "Renamed"


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_update_automation_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.update_automation.side_effect = TransportQueryError(
        "failed", errors=[{"message": "not found"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "update_automation",
            {"automation_id": "missing", "extra_input": {"name": "x"}},
        )

    assert extract_payload(result)["success"] is False
    assert "not found" in extract_payload(result)["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_delete_automation_success(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.delete_automation.return_value = {"success": True}

    async with automation_session as session:
        result = await session.call_tool(
            "delete_automation",
            {"automation_id": "rm-1", "debug": False},
        )

    assert result.isError is False
    mock_automation_client.delete_automation.assert_awaited_once_with("rm-1")
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_delete_automation_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.delete_automation.side_effect = TransportQueryError(
        "failed", errors=[{"message": "forbidden"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "delete_automation",
            {"automation_id": "z"},
        )

    assert extract_payload(result)["success"] is False
    assert "forbidden" in extract_payload(result)["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_delete_automation_has_destructive_hint(automation_session):
    async with automation_session as session:
        listed = await session.list_tools()
    delete_tool = next(t for t in listed.tools if t.name == "delete_automation")
    assert delete_tool.annotations is not None
    assert delete_tool.annotations.destructiveHint is True
    assert delete_tool.annotations.readOnlyHint is False


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_and_update_automation_tools_are_not_read_only(
    automation_session,
):
    async with automation_session as session:
        listed = await session.list_tools()
    by_name = {t.name: t for t in listed.tools}
    for name in ("create_automation", "update_automation"):
        ann = by_name[name].annotations
        assert ann is not None
        assert ann.readOnlyHint is False
        assert ann.destructiveHint is False
