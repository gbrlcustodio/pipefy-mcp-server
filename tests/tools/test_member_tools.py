"""Tests for member MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.member_tools import MemberTools


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_member_client():
    client = MagicMock(PipefyClient)
    client.invite_members = AsyncMock()
    client.remove_members_from_pipe = AsyncMock()
    client.set_role = AsyncMock()
    return client


@pytest.fixture
def member_mcp_server(mock_member_client):
    mcp = FastMCP("Member Tools Test")
    MemberTools.register(mcp, mock_member_client)
    return mcp


@pytest.fixture
def member_session(member_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        member_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("member_session", [None], indirect=True)
async def test_invite_members_success(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.invite_members.return_value = {
        "inviteMembers": {
            "users": [{"id": "u1", "email": "a@x.com"}],
            "errors": [],
        }
    }

    async with member_session as session:
        result = await session.call_tool(
            "invite_members",
            {
                "pipe_id": "pipe-1",
                "members": [{"email": "a@x.com", "role_name": "member"}],
            },
        )

    assert result.isError is False
    mock_member_client.invite_members.assert_awaited_once_with(
        "pipe-1", [{"email": "a@x.com", "role_name": "member"}]
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["inviteMembers"]["users"][0]["email"] == "a@x.com"


@pytest.mark.anyio
@pytest.mark.parametrize("member_session", [None], indirect=True)
async def test_invite_members_graphql_error(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.invite_members.side_effect = TransportQueryError(
        "failed", errors=[{"message": "invalid email"}]
    )

    async with member_session as session:
        result = await session.call_tool(
            "invite_members",
            {
                "pipe_id": "p1",
                "members": [{"email": "bad", "role_name": "member"}],
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "invalid email" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("member_session", [None], indirect=True)
async def test_remove_member_from_pipe_success(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.remove_members_from_pipe.return_value = {
        "removeMembersFromPipe": {"success": True}
    }

    async with member_session as session:
        result = await session.call_tool(
            "remove_member_from_pipe",
            {"pipe_id": "pipe-1", "user_ids": ["user-1", "user-2"]},
        )

    assert result.isError is False
    mock_member_client.remove_members_from_pipe.assert_awaited_once_with(
        "pipe-1", ["user-1", "user-2"]
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["removeMembersFromPipe"]["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("member_session", [None], indirect=True)
async def test_remove_member_from_pipe_graphql_error(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.remove_members_from_pipe.side_effect = (
        TransportQueryError("failed", errors=[{"message": "forbidden"}])
    )

    async with member_session as session:
        result = await session.call_tool(
            "remove_member_from_pipe",
            {"pipe_id": "p1", "user_ids": ["u1"]},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "forbidden" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("member_session", [None], indirect=True)
async def test_remove_member_from_pipe_has_destructive_hint(member_session):
    async with member_session as session:
        listed = await session.list_tools()
    remove_tool = next(
        t for t in listed.tools if t.name == "remove_member_from_pipe"
    )
    assert remove_tool.annotations is not None
    assert remove_tool.annotations.destructiveHint is True
    assert remove_tool.annotations.readOnlyHint is False


@pytest.mark.anyio
@pytest.mark.parametrize("member_session", [None], indirect=True)
async def test_set_role_success(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.set_role.return_value = {
        "setRole": {
            "member": {
                "role_name": "admin",
                "user": {"id": "u1", "email": "admin@x.com"},
            }
        }
    }

    async with member_session as session:
        result = await session.call_tool(
            "set_role",
            {
                "pipe_id": "pipe-1",
                "member_id": "member-1",
                "role_name": "admin",
            },
        )

    assert result.isError is False
    mock_member_client.set_role.assert_awaited_once_with(
        "pipe-1", "member-1", "admin"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["setRole"]["member"]["role_name"] == "admin"


@pytest.mark.anyio
@pytest.mark.parametrize("member_session", [None], indirect=True)
async def test_set_role_graphql_error(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.set_role.side_effect = TransportQueryError(
        "failed", errors=[{"message": "invalid role"}]
    )

    async with member_session as session:
        result = await session.call_tool(
            "set_role",
            {"pipe_id": "p1", "member_id": "m1", "role_name": "admin"},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "invalid role" in payload["error"]
