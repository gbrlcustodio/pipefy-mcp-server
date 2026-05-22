"""Unit tests for MemberService (invite, remove, set role)."""

from unittest.mock import AsyncMock

import pytest
from gql.transport.exceptions import TransportQueryError
from pipefy_auth import StaticBearerAuth

from pipefy_sdk.queries.member_queries import (
    INVITE_MEMBERS_MUTATION,
    REMOVE_MEMBERS_FROM_PIPE_MUTATION,
    SET_ROLE_MUTATION,
)
from pipefy_sdk.services.member_service import MemberService
from pipefy_sdk.services.pipe_service import PipeService
from pipefy_sdk.settings import PipefySettings

_TEST_AUTH = StaticBearerAuth("test-bearer-token")


@pytest.fixture
def mock_settings():
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings, return_value: dict):
    service = MemberService(settings=mock_settings, auth=_TEST_AUTH)
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
    result = await service.invite_members("601", members)

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is INVITE_MEMBERS_MUTATION
    inp = variables["input"]
    assert inp["pipe_id"] == "601"
    assert inp["emails"] == [{"email": "a@x.com", "role_name": "member"}]
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invite_members_transport_error(mock_settings):
    service = MemberService(settings=mock_settings, auth=_TEST_AUTH)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.invite_members(
            "602", [{"email": "x@y.com", "role_name": "member"}]
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invite_members_rejects_invalid_email(mock_settings):
    service = MemberService(settings=mock_settings, auth=_TEST_AUTH)
    service.execute_query = AsyncMock()
    with pytest.raises(ValueError) as excinfo:
        await service.invite_members(
            "602",
            [{"email": "invalid-email-format", "role_name": "member"}],
        )
    message = str(excinfo.value)
    assert "members[0].email" in message
    assert "\n" not in message
    service.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invite_members_rejects_unknown_keys(mock_settings):
    """``MemberInvite.model_config`` forbids extras; surfaced as one-line ``ValueError``."""
    service = MemberService(settings=mock_settings, auth=_TEST_AUTH)
    service.execute_query = AsyncMock()
    with pytest.raises(ValueError) as excinfo:
        await service.invite_members(
            "602",
            [
                {
                    "email": "ok@example.com",
                    "role_name": "member",
                    "foo": "bar",
                },
            ],
        )
    message = str(excinfo.value)
    assert "members[0].foo" in message
    assert "\n" not in message
    service.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invite_members_rejects_blank_role_name(mock_settings):
    """Blank ``role_name`` surfaces a single-line error pointing at the right field."""
    service = MemberService(settings=mock_settings, auth=_TEST_AUTH)
    service.execute_query = AsyncMock()
    with pytest.raises(ValueError) as excinfo:
        await service.invite_members(
            "602",
            [{"email": "ok@example.com", "role_name": ""}],
        )
    message = str(excinfo.value)
    assert "members[0].role_name" in message
    assert "\n" not in message
    service.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invite_members_lowercases_email(mock_settings):
    payload = {
        "inviteMembers": {
            "users": [{"id": "u1", "email": "user@example.com"}],
            "errors": [],
        }
    }
    service = _make_service(mock_settings, payload)
    await service.invite_members(
        "601",
        [{"email": "User@Example.COM", "role_name": "member"}],
    )
    _q, variables = service.execute_query.call_args[0]
    assert variables["input"]["emails"] == [
        {"email": "user@example.com", "role_name": "member"},
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remove_members_from_pipe_success(mock_settings):
    payload = {"removeMembersFromPipe": {"success": True}}
    pipe_service = AsyncMock(spec=PipeService)
    pipe_service.get_pipe = AsyncMock(
        return_value={"pipe": {"uuid": "pipe-uuid-1", "id": 99}}
    )
    service = MemberService(settings=mock_settings, pipe_service=pipe_service)
    service.execute_query = AsyncMock(return_value=payload)
    result = await service.remove_members_from_pipe(
        "99",
        [
            "550e8400-e29b-41d4-a716-446655440001",
            "550e8400-e29b-41d4-a716-446655440002",
        ],
    )

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is REMOVE_MEMBERS_FROM_PIPE_MUTATION
    inp = variables["input"]
    assert inp["pipeUuid"] == "pipe-uuid-1"
    assert inp["usersUuids"] == [
        "550e8400-e29b-41d4-a716-446655440001",
        "550e8400-e29b-41d4-a716-446655440002",
    ]
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remove_members_from_pipe_transport_error(mock_settings):
    pipe_service = AsyncMock(spec=PipeService)
    pipe_service.get_pipe = AsyncMock(return_value={"pipe": {"uuid": "pu", "id": 1}})
    service = MemberService(settings=mock_settings, pipe_service=pipe_service)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "forbidden"}])
    )
    with pytest.raises(TransportQueryError):
        await service.remove_members_from_pipe(
            "1", ["550e8400-e29b-41d4-a716-446655440000"]
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remove_members_from_pipe_invalid_pipe_id_raises(mock_settings):
    service = MemberService(settings=mock_settings, auth=_TEST_AUTH)
    service.execute_query = AsyncMock()
    with pytest.raises(ValueError, match="pipe_id must be a numeric"):
        await service.remove_members_from_pipe("not-a-pipe-id", ["u1"])

    with pytest.raises(ValueError, match="pipe_id must be a numeric"):
        await service.remove_members_from_pipe("bad", ["u1"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remove_members_from_pipe_resolves_numeric_user_ids(mock_settings):
    payload = {"removeMembersFromPipe": {"success": True}}
    pipe_service = AsyncMock(spec=PipeService)
    pipe_service.get_pipe = AsyncMock(
        return_value={"pipe": {"uuid": "pipe-uuid-x", "id": 42}}
    )
    pipe_service.get_pipe_members = AsyncMock(
        return_value={
            "pipe": {
                "members": [
                    {"user": {"id": "7", "uuid": "resolved-uuid-7"}},
                    {"user": {"id": "8", "uuid": "resolved-uuid-8"}},
                ]
            }
        }
    )
    service = MemberService(settings=mock_settings, pipe_service=pipe_service)
    service.execute_query = AsyncMock(return_value=payload)
    await service.remove_members_from_pipe("42", ["7", "8"])

    _, variables = service.execute_query.call_args[0]
    assert variables["input"]["usersUuids"] == ["resolved-uuid-7", "resolved-uuid-8"]


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
    result = await service.set_role("603", "member-1", "admin")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is SET_ROLE_MUTATION
    inp = variables["input"]
    assert inp["pipe_id"] == "603"
    assert inp["member"] == {"user_id": "member-1", "role_name": "admin"}
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_role_transport_error(mock_settings):
    service = MemberService(settings=mock_settings, auth=_TEST_AUTH)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "invalid"}])
    )
    with pytest.raises(TransportQueryError):
        await service.set_role("604", "m1", "member")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remove_members_rejects_uuid_pipe_id(mock_settings):
    service = MemberService(settings=mock_settings, auth=_TEST_AUTH)
    with pytest.raises(ValueError, match="numeric pipe ID"):
        await service.remove_members_from_pipe(
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890", ["u1"]
        )
