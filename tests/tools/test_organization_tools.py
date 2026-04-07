"""Tests for organization MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.organization_tools import OrganizationTools


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_org_client():
    client = MagicMock(PipefyClient)
    client.get_organization = AsyncMock()
    return client


@pytest.fixture
def org_mcp_server(mock_org_client):
    mcp = FastMCP("Pipefy Organization Tools Test")
    OrganizationTools.register(mcp, mock_org_client)
    return mcp


@pytest.fixture
def org_session(org_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        org_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("org_session", [None], indirect=True)
async def test_get_organization_success(org_session, mock_org_client, extract_payload):
    mock_org_client.get_organization = AsyncMock(
        return_value={
            "id": "123",
            "uuid": "abc-def",
            "name": "My Org",
            "planName": "Business",
            "membersCount": 42,
        }
    )
    async with org_session as session:
        result = await session.call_tool("get_organization", {"organization_id": "123"})
    assert result.isError is False
    mock_org_client.get_organization.assert_awaited_once_with("123")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "My Org" in payload["result"]


@pytest.mark.anyio
@pytest.mark.parametrize("org_session", [None], indirect=True)
async def test_get_organization_not_found_returns_error(
    org_session, mock_org_client, extract_payload
):
    mock_org_client.get_organization = AsyncMock(
        return_value={"error": "Organization '999' was not found."}
    )
    async with org_session as session:
        result = await session.call_tool("get_organization", {"organization_id": "999"})
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in payload["error"].lower()


@pytest.mark.anyio
@pytest.mark.parametrize("org_session", [None], indirect=True)
async def test_get_organization_transport_error(
    org_session, mock_org_client, extract_payload
):
    mock_org_client.get_organization = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "timeout"}])
    )
    async with org_session as session:
        result = await session.call_tool("get_organization", {"organization_id": "123"})
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert isinstance(payload.get("error"), str)


## ---------------------------------------------------------------------------
## PipefyId coercion: int → str through MCP transport (mcporter mitigation)
## ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("org_session", [None], indirect=True)
async def test_get_organization_coerces_int_organization_id(
    org_session, mock_org_client, extract_payload
):
    mock_org_client.get_organization = AsyncMock(
        return_value={
            "id": "123",
            "uuid": "abc-def",
            "name": "My Org",
            "planName": "Business",
            "membersCount": 42,
        }
    )
    async with org_session as session:
        result = await session.call_tool("get_organization", {"organization_id": 123})
    assert result.isError is False
    mock_org_client.get_organization.assert_awaited_once_with("123")
    payload = extract_payload(result)
    assert payload["success"] is True
