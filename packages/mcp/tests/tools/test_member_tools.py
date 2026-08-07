"""Tests for member MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from _mcp_compat import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import PipefyClient, PipefyGraphQLError

from pipefy_mcp.core.tool_error_envelope import tool_error_message
from pipefy_mcp.tools.member_tools import MemberTools
from tools.conftest import build_tool_test_server


@pytest.fixture
def mock_member_client():
    client = MagicMock(PipefyClient)
    client.invite_members = AsyncMock()
    client.add_service_account_to_pipe = AsyncMock()
    client.remove_members_from_pipe = AsyncMock()
    client.get_pipe_members = AsyncMock()
    client.set_role = AsyncMock()
    return client


@pytest.fixture
def member_mcp_server(mock_member_client):
    return build_tool_test_server(
        "Member Tools Test", MemberTools.register, mock_member_client
    )


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
async def test_invite_members_rejects_empty_members(member_session, extract_payload):
    async with member_session as session:
        result = await session.call_tool(
            "invite_members",
            {"pipe_id": "pipe-1", "members": []},
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "members" in tool_error_message(payload)


def _members_payload(*emails: str) -> dict:
    return {
        "pipe": {
            "members": [
                {
                    "user": {
                        "id": str(i),
                        "uuid": f"uuid-{i}",
                        "name": e,
                        "email": e,
                    },
                    "role_name": "member",
                }
                for i, e in enumerate(emails)
            ]
        }
    }


@pytest.mark.anyio
async def test_add_service_account_verified_member(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.add_service_account_to_pipe.return_value = {
        "inviteMembers": {"users": [{"id": "sa1", "email": "svc@x.com"}], "errors": []}
    }
    mock_member_client.get_pipe_members.return_value = _members_payload(
        "other@x.com", "svc@x.com"
    )

    async with member_session as session:
        result = await session.call_tool(
            "add_service_account_to_pipe",
            {"pipe_id": "100", "email": "svc@x.com", "role_name": "member"},
        )

    assert result.is_error is False
    mock_member_client.add_service_account_to_pipe.assert_awaited_once_with(
        "100", "svc@x.com", "member"
    )
    mock_member_client.get_pipe_members.assert_awaited_once_with("100")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "warning" not in payload


@pytest.mark.anyio
async def test_add_service_account_matches_email_case_insensitively(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.add_service_account_to_pipe.return_value = {
        "inviteMembers": {"users": [], "errors": []}
    }
    mock_member_client.get_pipe_members.return_value = _members_payload("svc@x.com")

    async with member_session as session:
        result = await session.call_tool(
            "add_service_account_to_pipe",
            {"pipe_id": "100", "email": "SVC@X.com", "role_name": "member"},
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    assert "warning" not in payload


@pytest.mark.anyio
async def test_add_service_account_errors_when_not_a_member(
    member_session, mock_member_client, extract_payload
):
    """Verification is authoritative: absent afterwards → failure, not silent success."""
    mock_member_client.add_service_account_to_pipe.return_value = {
        "inviteMembers": {"users": [], "errors": []}
    }
    mock_member_client.get_pipe_members.return_value = _members_payload("other@x.com")

    async with member_session as session:
        result = await session.call_tool(
            "add_service_account_to_pipe",
            {"pipe_id": "100", "email": "svc@x.com", "role_name": "member"},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "svc@x.com" in tool_error_message(payload)


@pytest.mark.anyio
async def test_add_service_account_surfaces_invite_errors_when_absent(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.add_service_account_to_pipe.return_value = {
        "inviteMembers": {
            "users": [],
            "errors": [{"index": 0, "message": "email is not a service account"}],
        }
    }
    mock_member_client.get_pipe_members.return_value = _members_payload("other@x.com")

    async with member_session as session:
        result = await session.call_tool(
            "add_service_account_to_pipe",
            {"pipe_id": "100", "email": "svc@x.com", "role_name": "member"},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert "not a service account" in tool_error_message(payload)


@pytest.mark.anyio
async def test_add_service_account_ignores_invite_errors_when_member_present(
    member_session, mock_member_client, extract_payload
):
    """'Already a member'-style row error is non-fatal once membership is confirmed."""
    mock_member_client.add_service_account_to_pipe.return_value = {
        "inviteMembers": {
            "users": [],
            "errors": [{"index": 0, "message": "already invited"}],
        }
    }
    mock_member_client.get_pipe_members.return_value = _members_payload("svc@x.com")

    async with member_session as session:
        result = await session.call_tool(
            "add_service_account_to_pipe",
            {"pipe_id": "100", "email": "svc@x.com", "role_name": "member"},
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    assert "warning" not in payload


@pytest.mark.anyio
async def test_add_service_account_handles_null_pipe_members(
    member_session, mock_member_client, extract_payload
):
    """A GraphQL `members: null` verification response must not raise TypeError."""
    mock_member_client.add_service_account_to_pipe.return_value = {
        "inviteMembers": {"users": [], "errors": []}
    }
    mock_member_client.get_pipe_members.return_value = {"pipe": {"members": None}}

    async with member_session as session:
        result = await session.call_tool(
            "add_service_account_to_pipe",
            {"pipe_id": "100", "email": "svc@x.com", "role_name": "member"},
        )

    # No crash; verification treats null as absent -> tool reports not-added.
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "svc@x.com" in tool_error_message(payload)


@pytest.mark.anyio
async def test_add_service_account_skips_verification_for_non_numeric_pipe_id(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.add_service_account_to_pipe.return_value = {
        "inviteMembers": {"users": [{"id": "sa1", "email": "svc@x.com"}], "errors": []}
    }

    async with member_session as session:
        result = await session.call_tool(
            "add_service_account_to_pipe",
            {"pipe_id": "pipe-uuid-1", "email": "svc@x.com", "role_name": "member"},
        )

    mock_member_client.get_pipe_members.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "warning" not in payload


@pytest.mark.anyio
async def test_add_service_account_rejects_blank_email(
    member_session, mock_member_client, extract_payload
):
    async with member_session as session:
        result = await session.call_tool(
            "add_service_account_to_pipe",
            {"pipe_id": "100", "email": "   ", "role_name": "member"},
        )
    mock_member_client.add_service_account_to_pipe.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "email" in tool_error_message(payload)


@pytest.mark.anyio
async def test_add_service_account_maps_value_error_to_invalid_arguments(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.add_service_account_to_pipe.side_effect = ValueError(
        "Invalid members[0].email: value is not a valid email address"
    )
    async with member_session as session:
        result = await session.call_tool(
            "add_service_account_to_pipe",
            {"pipe_id": "100", "email": "not-an-email", "role_name": "member"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"


@pytest.mark.anyio
async def test_add_service_account_graphql_error(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.add_service_account_to_pipe.side_effect = PipefyGraphQLError(
        [{"message": "permission denied"}]
    )
    async with member_session as session:
        result = await session.call_tool(
            "add_service_account_to_pipe",
            {"pipe_id": "100", "email": "svc@x.com", "role_name": "member"},
        )
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "permission denied" in tool_error_message(payload)


@pytest.mark.anyio
async def test_remove_member_from_pipe_rejects_empty_user_ids(
    member_session, extract_payload
):
    async with member_session as session:
        result = await session.call_tool(
            "remove_member_from_pipe",
            {"pipe_id": "pipe-1", "user_ids": []},
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "user_ids" in tool_error_message(payload)


@pytest.mark.anyio
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

    assert result.is_error is False
    mock_member_client.invite_members.assert_awaited_once_with(
        "pipe-1", [{"email": "a@x.com", "role_name": "member"}]
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["inviteMembers"]["users"][0]["email"] == "a@x.com"


@pytest.mark.anyio
async def test_invite_members_maps_sdk_value_error_to_invalid_arguments(
    member_session, mock_member_client, extract_payload
):
    """MCP maps ``ValueError`` from ``invite_members`` (e.g. email validation) to INVALID_ARGUMENTS."""
    mock_member_client.invite_members.side_effect = ValueError(
        "Invalid members[0]: expected valid email and non-empty role_name (x)."
    )
    async with member_session as session:
        result = await session.call_tool(
            "invite_members",
            {
                "pipe_id": "p1",
                "members": [{"email": "not-an-email", "role_name": "member"}],
            },
        )
    mock_member_client.invite_members.assert_awaited_once()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert "email" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_invite_members_graphql_error(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.invite_members.side_effect = PipefyGraphQLError(
        [{"message": "invalid email"}]
    )

    async with member_session as session:
        result = await session.call_tool(
            "invite_members",
            {
                "pipe_id": "p1",
                "members": [{"email": "valid@example.com", "role_name": "member"}],
            },
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "invalid email" in tool_error_message(payload)


@pytest.mark.anyio
async def test_remove_member_from_pipe_value_error_from_client(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.remove_members_from_pipe.side_effect = ValueError(
        "pipe_id must be a numeric pipe ID or a pipe UUID, got 'bad'."
    )

    async with member_session as session:
        result = await session.call_tool(
            "remove_member_from_pipe",
            {"pipe_id": "bad", "user_ids": ["u1"], "confirm": True},
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "pipe_id" in tool_error_message(payload)


@pytest.mark.anyio
async def test_remove_member_verified_all_removed(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.remove_members_from_pipe.return_value = {
        "removeMembersFromPipe": {"success": True}
    }
    mock_member_client.get_pipe_members.return_value = {
        "pipe": {
            "members": [
                {
                    "user": {
                        "id": "99",
                        "uuid": "uuid-99",
                        "name": "Other",
                        "email": "other@x.com",
                    },
                    "role_name": "member",
                },
            ]
        }
    }

    async with member_session as session:
        result = await session.call_tool(
            "remove_member_from_pipe",
            {"pipe_id": "100", "user_ids": ["user-1", "user-2"], "confirm": True},
        )

    assert result.is_error is False
    mock_member_client.remove_members_from_pipe.assert_awaited_once_with(
        "100", ["user-1", "user-2"]
    )
    mock_member_client.get_pipe_members.assert_awaited_once_with("100")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "warning" not in payload


@pytest.mark.anyio
async def test_remove_member_warns_when_member_still_present(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.remove_members_from_pipe.return_value = {
        "removeMembersFromPipe": {"success": True}
    }
    mock_member_client.get_pipe_members.return_value = {
        "pipe": {
            "members": [
                {
                    "user": {
                        "id": "160654",
                        "uuid": "uuid-160654",
                        "name": "Rodrigo",
                        "email": "rodrigo@x.com",
                    },
                    "role_name": "admin",
                },
                {
                    "user": {
                        "id": "99",
                        "uuid": "uuid-99",
                        "name": "Other",
                        "email": "other@x.com",
                    },
                    "role_name": "member",
                },
            ]
        }
    }

    async with member_session as session:
        result = await session.call_tool(
            "remove_member_from_pipe",
            {"pipe_id": "100", "user_ids": ["160654"], "confirm": True},
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    assert "warning" in payload
    assert "160654" in payload["warning"]
    assert "org-level" in payload["warning"]


@pytest.mark.anyio
async def test_remove_member_warns_when_uuid_still_present(
    member_session, mock_member_client, extract_payload
):
    """Verification matches user UUIDs too, not just numeric IDs."""
    mock_member_client.remove_members_from_pipe.return_value = {
        "removeMembersFromPipe": {"success": True}
    }
    mock_member_client.get_pipe_members.return_value = {
        "pipe": {
            "members": [
                {
                    "user": {
                        "id": "160654",
                        "uuid": "abc-def-123",
                        "name": "Rodrigo",
                        "email": "rodrigo@x.com",
                    },
                    "role_name": "admin",
                },
            ]
        }
    }

    async with member_session as session:
        result = await session.call_tool(
            "remove_member_from_pipe",
            {"pipe_id": "100", "user_ids": ["abc-def-123"], "confirm": True},
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    assert "warning" in payload
    assert "abc-def-123" in payload["warning"]


@pytest.mark.anyio
async def test_remove_member_skips_verification_for_non_numeric_pipe_id(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.remove_members_from_pipe.return_value = {
        "removeMembersFromPipe": {"success": True}
    }

    async with member_session as session:
        result = await session.call_tool(
            "remove_member_from_pipe",
            {"pipe_id": "pipe-1", "user_ids": ["user-1"], "confirm": True},
        )

    mock_member_client.get_pipe_members.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "warning" not in payload


@pytest.mark.anyio
async def test_remove_member_returns_success_when_verification_fails(
    member_session, mock_member_client, extract_payload
):
    """If get_pipe_members raises, don't fail the whole operation."""
    mock_member_client.remove_members_from_pipe.return_value = {
        "removeMembersFromPipe": {"success": True}
    }
    mock_member_client.get_pipe_members.side_effect = Exception("network error")

    async with member_session as session:
        result = await session.call_tool(
            "remove_member_from_pipe",
            {"pipe_id": "100", "user_ids": ["user-1"], "confirm": True},
        )

    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
async def test_remove_member_coerces_int_user_ids_to_str(
    member_session, mock_member_client, extract_payload
):
    """Agent may re-serialize user_ids as ints on the confirm call."""
    mock_member_client.remove_members_from_pipe.return_value = {
        "removeMembersFromPipe": {"success": True}
    }
    mock_member_client.get_pipe_members.return_value = {"pipe": {"members": []}}

    async with member_session as session:
        result = await session.call_tool(
            "remove_member_from_pipe",
            {"pipe_id": "100", "user_ids": [307516938], "confirm": True},
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    mock_member_client.remove_members_from_pipe.assert_awaited_once_with(
        "100", ["307516938"]
    )


@pytest.mark.anyio
async def test_remove_member_from_pipe_graphql_error(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.remove_members_from_pipe.side_effect = PipefyGraphQLError(
        [{"message": "forbidden"}]
    )

    async with member_session as session:
        result = await session.call_tool(
            "remove_member_from_pipe",
            {"pipe_id": "p1", "user_ids": ["u1"], "confirm": True},
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "forbidden" in tool_error_message(payload)


@pytest.mark.anyio
async def test_remove_member_from_pipe_has_destructive_hint(member_session):
    async with member_session as session:
        listed = await session.list_tools()
    remove_tool = next(t for t in listed.tools if t.name == "remove_member_from_pipe")
    assert remove_tool.annotations is not None
    assert remove_tool.annotations.destructive_hint is True
    assert remove_tool.annotations.read_only_hint is False


@pytest.mark.anyio
async def test_set_role_success(member_session, mock_member_client, extract_payload):
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

    assert result.is_error is False
    mock_member_client.set_role.assert_awaited_once_with("pipe-1", "member-1", "admin")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["setRole"]["member"]["role_name"] == "admin"
    assert "warning" not in payload


@pytest.mark.anyio
async def test_invite_members_rejects_missing_email_or_role(
    member_session, mock_member_client, extract_payload
):
    async with member_session as session:
        result = await session.call_tool(
            "invite_members",
            {"pipe_id": "pipe-1", "members": [{"email": "x@y.com"}]},
        )
    mock_member_client.invite_members.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "email" in tool_error_message(payload)
    assert "role_name" in tool_error_message(payload)


@pytest.mark.anyio
async def test_remove_member_preview_does_not_call_mutation(
    member_session, mock_member_client, extract_payload
):
    """Default ``confirm=false`` must surface the preview guard and skip the API."""
    async with member_session as session:
        result = await session.call_tool(
            "remove_member_from_pipe",
            {"pipe_id": "100", "user_ids": ["user-1"]},  # no confirm → preview
        )
    mock_member_client.remove_members_from_pipe.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload.get("requires_confirmation") is True
    assert "1 member(s)" in payload["resource"]
    assert "pipe 100" in payload["resource"]


@pytest.mark.anyio
async def test_set_role_rejects_blank_role_name(
    member_session, mock_member_client, extract_payload
):
    async with member_session as session:
        result = await session.call_tool(
            "set_role",
            {"pipe_id": "p1", "member_id": "m1", "role_name": "   "},
        )
    mock_member_client.set_role.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "role_name" in tool_error_message(payload)


@pytest.mark.anyio
async def test_set_role_graphql_error(
    member_session, mock_member_client, extract_payload
):
    mock_member_client.set_role.side_effect = PipefyGraphQLError(
        [{"message": "invalid role"}]
    )

    async with member_session as session:
        result = await session.call_tool(
            "set_role",
            {"pipe_id": "p1", "member_id": "m1", "role_name": "admin"},
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "invalid role" in tool_error_message(payload)
