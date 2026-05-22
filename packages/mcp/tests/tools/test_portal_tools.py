"""Tests for portal read MCP tools (mocked PipefyClient)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import PipefyClient

from pipefy_mcp.tools.portal_tools import PortalTools
from pipefy_mcp.tools.tool_error_envelope import tool_error_message

_PORTAL_LIST_NODE = {
    "id": "portal-uuid-1",
    "uuid": "portal-uuid-1",
    "name": "Main Portal",
    "visibility": "internal",
    "subType": "portal",
}

_PORTAL_DETAIL = {
    "id": "portal-uuid-1",
    "uuid": "portal-uuid-1",
    "name": "Main Portal",
    "visibility": "public",
    "published": True,
    "pages": [
        {
            "id": "page-1",
            "uuid": "page-1",
            "title": "Home",
            "elements": [
                {
                    "id": "el-1",
                    "uuid": "el-1",
                    "type": "forms",
                    "metadata": {"formId": "123"},
                }
            ],
        }
    ],
    "subPortals": [{"id": "sub-1", "uuid": "sub-1", "name": "Sub Portal 1"}],
}


@pytest.fixture
def mock_portal_client():
    client = MagicMock(PipefyClient)
    client.list_portals = AsyncMock()
    client.get_portal = AsyncMock()
    return client


@pytest.fixture
def portal_mcp_server(mock_portal_client):
    mcp = FastMCP("Pipefy Portal Tools Test")
    PortalTools.register(mcp, mock_portal_client)
    return mcp


@pytest.fixture
def portal_session(portal_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        portal_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_list_portals_success(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.list_portals = AsyncMock(return_value=[_PORTAL_LIST_NODE])

    async with portal_session as session:
        result = await session.call_tool("list_portals", {"organization_uuid": "org-abc-123"})

    assert result.isError is False
    mock_portal_client.list_portals.assert_awaited_once_with(
        "org-abc-123", search_term=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "result" in payload
    assert payload["data"]["portals"] == [_PORTAL_LIST_NODE]
    assert payload["data"]["portals"][0]["name"] == "Main Portal"


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_list_portals_coerces_int_organization_uuid(
    portal_session, mock_portal_client, extract_payload
):
    """mcporter CLI sends numeric IDs as int; PipefyId must coerce to str."""
    mock_portal_client.list_portals = AsyncMock(return_value=[])

    async with portal_session as session:
        result = await session.call_tool(
            "list_portals",
            {"organization_uuid": 302398434},
        )

    assert result.isError is False
    mock_portal_client.list_portals.assert_awaited_once_with(
        "302398434", search_term=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_list_portals_passes_search_term(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.list_portals = AsyncMock(return_value=[])

    async with portal_session as session:
        result = await session.call_tool(
            "list_portals",
            {"organization_uuid": "org-abc-123", "search_term": "intake"},
        )

    assert result.isError is False
    mock_portal_client.list_portals.assert_awaited_once_with(
        "org-abc-123", search_term="intake"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["portals"] == []


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_list_portals_empty_returns_empty_list(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.list_portals = AsyncMock(return_value=[])

    async with portal_session as session:
        result = await session.call_tool("list_portals", {"organization_uuid": "org-empty"})

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["portals"] == []


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_list_portals_value_error_returns_error_envelope(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.list_portals = AsyncMock(
        side_effect=ValueError("Organization 'org-bad' was not found.")
    )

    async with portal_session as session:
        result = await session.call_tool("list_portals", {"organization_uuid": "org-bad"})

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_get_portal_success(portal_session, mock_portal_client, extract_payload):
    mock_portal_client.get_portal = AsyncMock(return_value=_PORTAL_DETAIL)

    async with portal_session as session:
        result = await session.call_tool("get_portal", {"portal_uuid": "portal-uuid-1"})

    assert result.isError is False
    mock_portal_client.get_portal.assert_awaited_once_with("portal-uuid-1")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "result" in payload
    assert payload["data"]["uuid"] == "portal-uuid-1"
    assert payload["data"]["published"] is True
    assert payload["data"]["pages"][0]["title"] == "Home"
    assert payload["data"]["subPortals"][0]["name"] == "Sub Portal 1"


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_get_portal_not_found_returns_error_envelope(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.get_portal = AsyncMock(
        side_effect=ValueError("Portal 'portal-missing' was not found.")
    )

    async with portal_session as session:
        result = await session.call_tool("get_portal", {"portal_uuid": "portal-missing"})

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_list_portals_transport_error_returns_error_envelope(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.list_portals = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "timeout"}])
    )

    async with portal_session as session:
        result = await session.call_tool("list_portals", {"organization_uuid": "org-abc-123"})

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    err = payload.get("error")
    assert isinstance(err, dict) and "message" in err


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_get_portal_transport_error_returns_error_envelope(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.get_portal = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "timeout"}])
    )

    async with portal_session as session:
        result = await session.call_tool("get_portal", {"portal_uuid": "portal-uuid-1"})

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    err = payload.get("error")
    assert isinstance(err, dict) and "message" in err


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_read_tools_have_readonly_hint(portal_session):
    read_tool_names = ["list_portals", "get_portal"]

    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    for name in read_tool_names:
        tool = tool_map[name]
        assert tool.annotations is not None, f"{name} missing annotations"
        assert tool.annotations.readOnlyHint is True, (
            f"{name} should be readOnlyHint=True"
        )
