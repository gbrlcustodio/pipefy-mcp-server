"""Unit tests for MemberService (invite, remove, set role)."""

from unittest.mock import AsyncMock

import pytest
from gql.transport.exceptions import TransportQueryError

from pipefy_mcp.services.pipefy.member_service import MemberService
from pipefy_mcp.services.pipefy.queries.member_queries import (
    INVITE_MEMBERS_MUTATION,
    REMOVE_MEMBERS_FROM_PIPE_MUTATION,
    SET_ROLE_MUTATION,
)
from pipefy_mcp.settings import PipefySettings


@pytest.fixture
def mock_settings():
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings, return_value: dict):
    service = MemberService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invite_members_success(mock_settings):
    payload = {
        "inviteMembers": {
            "users": [{"id": "u1", "email": "a@x.com"}],
            "errors": [],
        }
    }
    service = _make_service(mock_settings, payload)
    members = [{"email": "a@x.com", "role_name": "member"}]
    result = await service.invite_members("pipe-1", members)

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is INVITE_MEMBERS_MUTATION
    inp = variables["input"]
    assert inp["pipe_id"] == "pipe-1"
    assert inp["emails"] == [{"email": "a@x.com", "role_name": "member"}]
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invite_members_transport_error(mock_settings):
    service = MemberService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.invite_members("p1", [{"email": "x@y.com", "role_name": "member"}])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remove_members_from_pipe_success(mock_settings):
    payload = {"removeMembersFromPipe": {"success": True}}
    service = _make_service(mock_settings, payload)
    result = await service.remove_members_from_pipe("pipe-1", ["user-1", "user-2"])

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is REMOVE_MEMBERS_FROM_PIPE_MUTATION
    inp = variables["input"]
    assert inp["pipeUuid"] == "pipe-1"
    assert inp["usersUuids"] == ["user-1", "user-2"]
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remove_members_from_pipe_transport_error(mock_settings):
    service = MemberService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "forbidden"}])
    )
    with pytest.raises(TransportQueryError):
        await service.remove_members_from_pipe("p1", ["u1"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_role_success(mock_settings):
    payload = {
        "setRole": {
            "member": {
                "role_name": "admin",
                "user": {"id": "u1", "email": "admin@x.com"},
            }
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.set_role("pipe-1", "member-1", "admin")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is SET_ROLE_MUTATION
    inp = variables["input"]
    assert inp["pipe_id"] == "pipe-1"
    assert inp["member"] == {"user_id": "member-1", "role_name": "admin"}
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_role_transport_error(mock_settings):
    service = MemberService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "invalid"}])
    )
    with pytest.raises(TransportQueryError):
        await service.set_role("p1", "m1", "member")
