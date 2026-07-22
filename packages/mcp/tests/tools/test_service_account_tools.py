"""Tests for service-account MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import PipefyClient

from pipefy_mcp.core.tool_error_envelope import tool_error_message
from pipefy_mcp.tools.service_account_tools import ServiceAccountTools
from tools.conftest import build_tool_test_server

ORG = "341c1327-261c-4766-bb96-7953e4c3970d"


@pytest.fixture
def mock_sa_client():
    client = MagicMock(PipefyClient)
    client.create_service_account = AsyncMock()
    client.delete_service_account = AsyncMock()
    client.get_pipe_members = AsyncMock()
    return client


@pytest.fixture
def sa_mcp_server(mock_sa_client):
    return build_tool_test_server(
        "Service Account Tools Test", ServiceAccountTools.register, mock_sa_client
    )


@pytest.fixture
def sa_session(sa_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        sa_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("sa_session", [None], indirect=True)
async def test_create_service_account_success(
    sa_session, mock_sa_client, extract_payload
):
    mock_sa_client.create_service_account.return_value = {
        "createServiceAccount": {
            "serviceAccount": {
                "id": "1",
                "uuid": "u1",
                "email": "sa@x.com",
                "client": {"id": "cid", "secret": "csecret"},
                "token": {"endpoint": "https://token"},
            }
        }
    }
    async with sa_session as session:
        result = await session.call_tool(
            "create_service_account",
            {"organization_uuid": ORG, "name": "sa", "role": "normal"},
        )

    assert result.isError is False
    mock_sa_client.create_service_account.assert_awaited_once_with(
        organization_uuid=ORG,
        name="sa",
        role="normal",
        description=None,
        expiration=None,
        pipe_ids=None,
        pipe_role="admin",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    # The secret is returned to the caller (needed to authenticate the account).
    assert payload["data"]["serviceAccount"]["client"]["secret"] == "csecret"
    assert "once" in payload["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("sa_session", [None], indirect=True)
async def test_create_service_account_passes_expiration(
    sa_session, mock_sa_client, extract_payload
):
    mock_sa_client.create_service_account.return_value = {
        "createServiceAccount": {"serviceAccount": {}}
    }
    async with sa_session as session:
        await session.call_tool(
            "create_service_account",
            {
                "organization_uuid": ORG,
                "name": "sa",
                "role": "normal",
                "expiration_unit": "days",
                "expiration_value": 1,
            },
        )
    mock_sa_client.create_service_account.assert_awaited_once_with(
        organization_uuid=ORG,
        name="sa",
        role="normal",
        description=None,
        expiration={"unit": "days", "value": 1},
        pipe_ids=None,
        pipe_role="admin",
    )


@pytest.mark.anyio
@pytest.mark.parametrize("sa_session", [None], indirect=True)
async def test_create_service_account_with_pipe_ids_chains_and_verifies(
    sa_session, mock_sa_client, extract_payload
):
    mock_sa_client.create_service_account.return_value = {
        "createServiceAccount": {"serviceAccount": {"email": "sa@x.com", "uuid": "u"}},
        "pipe_memberships": [{"pipe_id": "100", "invited": True}],
    }
    mock_sa_client.get_pipe_members.return_value = {
        "pipe": {"members": [{"user": {"email": "sa@x.com"}}]}
    }
    async with sa_session as session:
        result = await session.call_tool(
            "create_service_account",
            {
                "organization_uuid": ORG,
                "name": "sa",
                "role": "normal",
                "pipe_ids": ["100"],
            },
        )
    assert result.isError is False
    # pipe_role defaults to admin.
    mock_sa_client.create_service_account.assert_awaited_once_with(
        organization_uuid=ORG,
        name="sa",
        role="normal",
        description=None,
        expiration=None,
        pipe_ids=["100"],
        pipe_role="admin",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    membership = payload["data"]["pipe_memberships"][0]
    assert membership["pipe_id"] == "100"
    assert membership["member"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("sa_session", [None], indirect=True)
async def test_create_service_account_pipe_ids_null_members_still_returns_secret(
    sa_session, mock_sa_client, extract_payload
):
    """A GraphQL `members: null` during post-create verification must not crash
    the tool and strand the one-time client secret."""
    mock_sa_client.create_service_account.return_value = {
        "createServiceAccount": {
            "serviceAccount": {
                "email": "sa@x.com",
                "client": {"id": "cid", "secret": "csecret"},
            }
        },
        "pipe_memberships": [{"pipe_id": "100", "invited": True}],
    }
    mock_sa_client.get_pipe_members.return_value = {"pipe": {"members": None}}

    async with sa_session as session:
        result = await session.call_tool(
            "create_service_account",
            {
                "organization_uuid": ORG,
                "name": "sa",
                "role": "normal",
                "pipe_ids": ["100"],
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["serviceAccount"]["client"]["secret"] == "csecret"
    # Verification could not confirm membership, but the secret is still returned.
    assert payload["data"]["pipe_memberships"][0]["member"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("sa_session", [None], indirect=True)
async def test_create_service_account_rejects_bad_pipe_ids(
    sa_session, mock_sa_client, extract_payload
):
    async with sa_session as session:
        result = await session.call_tool(
            "create_service_account",
            {
                "organization_uuid": ORG,
                "name": "sa",
                "role": "normal",
                "pipe_ids": ["  "],
            },
        )
    mock_sa_client.create_service_account.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "pipe_ids" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("sa_session", [None], indirect=True)
async def test_create_service_account_rejects_long_name(
    sa_session, mock_sa_client, extract_payload
):
    async with sa_session as session:
        result = await session.call_tool(
            "create_service_account",
            {"organization_uuid": ORG, "name": "x" * 21, "role": "normal"},
        )
    mock_sa_client.create_service_account.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "20 characters" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("sa_session", [None], indirect=True)
async def test_create_service_account_rejects_bad_expiration_pair(
    sa_session, mock_sa_client, extract_payload
):
    async with sa_session as session:
        result = await session.call_tool(
            "create_service_account",
            {
                "organization_uuid": ORG,
                "name": "sa",
                "role": "normal",
                "expiration_unit": "days",
            },
        )
    mock_sa_client.create_service_account.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "expiration" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("sa_session", [None], indirect=True)
async def test_create_service_account_rejects_blank_org(
    sa_session, mock_sa_client, extract_payload
):
    async with sa_session as session:
        result = await session.call_tool(
            "create_service_account",
            {"organization_uuid": "  ", "name": "sa", "role": "normal"},
        )
    mock_sa_client.create_service_account.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "organization_uuid" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("sa_session", [None], indirect=True)
async def test_create_service_account_graphql_error(
    sa_session, mock_sa_client, extract_payload
):
    mock_sa_client.create_service_account.side_effect = TransportQueryError(
        "failed", errors=[{"message": "not allowed"}]
    )
    async with sa_session as session:
        result = await session.call_tool(
            "create_service_account",
            {"organization_uuid": ORG, "name": "sa", "role": "normal"},
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not allowed" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("sa_session", [None], indirect=True)
async def test_delete_service_account_preview_does_not_call_mutation(
    sa_session, mock_sa_client, extract_payload
):
    async with sa_session as session:
        result = await session.call_tool(
            "delete_service_account",
            {"organization_uuid": ORG, "service_account_uuid": "sa-uuid-1"},
        )
    mock_sa_client.delete_service_account.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload.get("requires_confirmation") is True
    assert "sa-uuid-1" in payload["resource"]


@pytest.mark.anyio
@pytest.mark.parametrize("sa_session", [None], indirect=True)
async def test_delete_service_account_confirmed(
    sa_session, mock_sa_client, extract_payload
):
    mock_sa_client.delete_service_account.return_value = {
        "deleteServiceAccount": {"success": True}
    }
    async with sa_session as session:
        result = await session.call_tool(
            "delete_service_account",
            {
                "organization_uuid": ORG,
                "service_account_uuid": "sa-uuid-1",
                "confirm": True,
            },
        )
    assert result.isError is False
    mock_sa_client.delete_service_account.assert_awaited_once_with(
        organization_uuid=ORG, service_account_uuid="sa-uuid-1"
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("sa_session", [None], indirect=True)
async def test_delete_service_account_rejects_blank_uuid(
    sa_session, mock_sa_client, extract_payload
):
    async with sa_session as session:
        result = await session.call_tool(
            "delete_service_account",
            {"organization_uuid": ORG, "service_account_uuid": "  ", "confirm": True},
        )
    mock_sa_client.delete_service_account.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "service_account_uuid" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("sa_session", [None], indirect=True)
async def test_delete_service_account_has_destructive_hint(sa_session):
    async with sa_session as session:
        listed = await session.list_tools()
    tool = next(t for t in listed.tools if t.name == "delete_service_account")
    assert tool.annotations is not None
    assert tool.annotations.destructiveHint is True
