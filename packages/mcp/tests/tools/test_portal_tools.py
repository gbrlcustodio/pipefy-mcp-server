"""Tests for portal MCP tools (mocked PipefyClient)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from _shared.fixture_ids import EXAMPLE_NUMERIC_ORG_ID, EXAMPLE_PIPE_REPO_ID
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import PipefyClient
from pipefy_sdk.exceptions import PortalPermissionError

from pipefy_mcp.tools.portal_tools import PortalTools
from pipefy_mcp.tools.tool_error_envelope import tool_error_message
from tools.conftest import assert_invalid_arguments_envelope

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
                    "metadata": {"name": "Request form"},
                }
            ],
        }
    ],
    "subPortals": [{"id": "sub-1", "uuid": "sub-1", "name": "Sub Portal 1"}],
}

_CREATED_PORTAL = {
    "id": "portal-created-uuid",
    "uuid": "portal-created-uuid",
    "name": "Org Portal",
    "visibility": "internal",
    "subType": "portal",
}

_PORTAL_PERMISSION_DENIED_MSG = (
    "Permission denied. Request organization permissions such as "
    "`create_portal` or `manage_portals` from your admin."
)

_PORTAL_UUID = "portal-uuid-1"
_PAGE_UUID = "page-uuid-1"
_PAGE_UUID_2 = "page-uuid-2"
_PAGE_TITLE = "Portal Home"

_CREATED_PAGE = {
    "id": _PAGE_UUID,
    "uuid": _PAGE_UUID,
    "title": _PAGE_TITLE,
    "elements": [{"id": "el-1", "uuid": "el-1", "type": "text"}],
}

_PAGE_LAYOUT = {"rows": [{"columns": [{"width": 12}]}]}

_ELEMENT_UUID = "el-uuid-1"
_FORMS_METADATA = {"name": "Request form"}
_FORMS_DATA_SOURCES = [{"repo_uuid": EXAMPLE_PIPE_REPO_ID}]

_CREATED_ELEMENT = {
    "id": _ELEMENT_UUID,
    "uuid": _ELEMENT_UUID,
    "type": "forms",
    "metadata": _FORMS_METADATA,
}

_MAIN_PORTAL_UUID = _PORTAL_UUID
_SUB_PORTAL_UUID = "sub-portal-uuid-1"
_FORMS_ELEMENT_ID = "el-forms-1"
_SUB_PORTAL_NAME = "Sub Portal 1"

_CREATED_SUB_PORTAL = {
    "id": _SUB_PORTAL_UUID,
    "uuid": _SUB_PORTAL_UUID,
    "name": _SUB_PORTAL_NAME,
}

_SUB_PORTAL_WRITE_TOOL_NAMES = [
    "create_sub_portal",
    "update_sub_portal_element",
    "publish_sub_portal",
    "unpublish_sub_portal",
    "delete_sub_portal_element",
    "delete_sub_portal",
]


@pytest.fixture
def mock_portal_client():
    client = MagicMock(PipefyClient)
    client.list_portals = AsyncMock()
    client.get_portal = AsyncMock()
    client.create_portal = AsyncMock()
    client.update_portal = AsyncMock()
    client.delete_portal = AsyncMock()
    client.create_portal_page = AsyncMock()
    client.update_portal_page = AsyncMock()
    client.delete_portal_page = AsyncMock()
    client.sort_portal_pages = AsyncMock()
    client.update_portal_page_layout = AsyncMock()
    client.create_portal_element = AsyncMock()
    client.update_portal_element = AsyncMock()
    client.delete_portal_element = AsyncMock()
    client.duplicate_portal_element = AsyncMock()
    client.create_sub_portal = AsyncMock()
    client.update_sub_portal_element = AsyncMock()
    client.publish_sub_portal = AsyncMock()
    client.unpublish_sub_portal = AsyncMock()
    client.delete_sub_portal_element = AsyncMock()
    client.delete_sub_portal = AsyncMock()
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
        result = await session.call_tool(
            "list_portals", {"organization_uuid": "org-abc-123"}
        )

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
            {"organization_uuid": int(EXAMPLE_NUMERIC_ORG_ID)},
        )

    assert result.isError is False
    mock_portal_client.list_portals.assert_awaited_once_with(
        EXAMPLE_NUMERIC_ORG_ID, search_term=None
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
        result = await session.call_tool(
            "list_portals", {"organization_uuid": "org-empty"}
        )

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
        result = await session.call_tool(
            "list_portals", {"organization_uuid": "org-bad"}
        )

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
        result = await session.call_tool(
            "get_portal", {"portal_uuid": "portal-missing"}
        )

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
        result = await session.call_tool(
            "list_portals", {"organization_uuid": "org-abc-123"}
        )

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


# ---------------------------------------------------------------------------
# Portal metadata CRUD write tools
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_coerces_int_organization_uuid(
    portal_session, mock_portal_client, extract_payload
):
    """mcporter CLI sends numeric IDs as int; PipefyId must coerce to str."""
    mock_portal_client.create_portal = AsyncMock(return_value=_CREATED_PORTAL)

    async with portal_session as session:
        result = await session.call_tool(
            "create_portal",
            {"organization_uuid": int(EXAMPLE_NUMERIC_ORG_ID)},
        )

    assert result.isError is False
    mock_portal_client.create_portal.assert_awaited_once_with(EXAMPLE_NUMERIC_ORG_ID)
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_success(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.create_portal = AsyncMock(return_value=_CREATED_PORTAL)

    async with portal_session as session:
        result = await session.call_tool(
            "create_portal", {"organization_uuid": EXAMPLE_NUMERIC_ORG_ID}
        )

    assert result.isError is False
    mock_portal_client.create_portal.assert_awaited_once_with(EXAMPLE_NUMERIC_ORG_ID)
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["uuid"] == "portal-created-uuid"
    assert payload["data"]["name"] == "Org Portal"


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_permission_denied_returns_actionable_error(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.create_portal = AsyncMock(
        side_effect=ValueError(_PORTAL_PERMISSION_DENIED_MSG)
    )

    async with portal_session as session:
        result = await session.call_tool(
            "create_portal", {"organization_uuid": "org-abc-123"}
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload).lower()
    assert "create_portal" in message or "manage_portals" in message


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_success(
    portal_session, mock_portal_client, extract_payload
):
    updated = {**_CREATED_PORTAL, "name": "Renamed Portal", "visibility": "public"}
    mock_portal_client.update_portal = AsyncMock(return_value=updated)

    async with portal_session as session:
        result = await session.call_tool(
            "update_portal",
            {
                "portal_uuid": "portal-created-uuid",
                "name": "Renamed Portal",
                "visibility": "public",
            },
        )

    assert result.isError is False
    mock_portal_client.update_portal.assert_awaited_once_with(
        "portal-created-uuid",
        name="Renamed Portal",
        visibility="public",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["name"] == "Renamed Portal"
    assert payload["data"]["visibility"] == "public"


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_invalid_visibility_returns_validation_envelope(
    portal_session, mock_portal_client
):
    async with portal_session as session:
        result = await session.call_tool(
            "update_portal",
            {
                "portal_uuid": "portal-created-uuid",
                "visibility": "public_visibility",
            },
        )

    assert_invalid_arguments_envelope(result)
    mock_portal_client.update_portal.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_rejects_when_no_fields_to_update(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "update_portal",
            {"portal_uuid": "portal-created-uuid"},
        )

    mock_portal_client.update_portal.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert "at least one" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_rejects_blank_name(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "update_portal",
            {"portal_uuid": "portal-created-uuid", "name": "   "},
        )

    mock_portal_client.update_portal.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert "name" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_get_portal_rejects_empty_portal_uuid(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool("get_portal", {"portal_uuid": "  "})

    mock_portal_client.get_portal.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "portal_uuid" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_rejects_empty_portal_uuid(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "delete_portal",
            {"portal_uuid": "", "confirm": True},
        )

    mock_portal_client.delete_portal.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "portal_uuid" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_permission_denied_returns_actionable_error(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.update_portal = AsyncMock(
        side_effect=ValueError(_PORTAL_PERMISSION_DENIED_MSG)
    )

    async with portal_session as session:
        result = await session.call_tool(
            "update_portal",
            {
                "portal_uuid": "portal-created-uuid",
                "name": "Renamed Portal",
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload).lower()
    assert "create_portal" in message or "manage_portals" in message


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_preview_does_not_delete(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "delete_portal", {"portal_uuid": "portal-to-delete"}
        )

    assert result.isError is False
    mock_portal_client.delete_portal.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert payload["resource"] == "portal (UUID: portal-to-delete)"
    assert "confirm=True" in payload["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_success(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.delete_portal = AsyncMock(
        return_value={"deleteInterface": {"success": True}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "delete_portal",
            {"portal_uuid": "portal-to-delete", "confirm": True},
        )

    assert result.isError is False
    mock_portal_client.delete_portal.assert_awaited_once_with("portal-to-delete")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["deleteInterface"]["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_fails_when_success_false(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.delete_portal = AsyncMock(
        return_value={"deleteInterface": {"success": False}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "delete_portal",
            {"portal_uuid": "portal-to-delete", "confirm": True},
        )

    assert result.isError is False
    mock_portal_client.delete_portal.assert_awaited_once_with("portal-to-delete")
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "failed to delete portal" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_permission_denied_returns_actionable_error(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.delete_portal = AsyncMock(
        side_effect=ValueError(_PORTAL_PERMISSION_DENIED_MSG)
    )

    async with portal_session as session:
        result = await session.call_tool(
            "delete_portal",
            {"portal_uuid": "portal-to-delete", "confirm": True},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload).lower()
    assert "create_portal" in message or "manage_portals" in message


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_has_destructive_hint(portal_session):
    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    delete_tool = tool_map["delete_portal"]
    assert delete_tool.annotations is not None
    assert delete_tool.annotations.destructiveHint is True
    assert delete_tool.annotations.readOnlyHint is not True


# ---------------------------------------------------------------------------
# Portal page write tools
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_page_success(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.create_portal_page = AsyncMock(return_value=_CREATED_PAGE)

    async with portal_session as session:
        result = await session.call_tool(
            "create_portal_page",
            {"portal_uuid": _PORTAL_UUID, "title": _PAGE_TITLE},
        )

    assert result.isError is False
    mock_portal_client.create_portal_page.assert_awaited_once_with(
        _PORTAL_UUID,
        _PAGE_TITLE,
        description=None,
        index=None,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["uuid"] == _PAGE_UUID
    assert payload["data"]["title"] == _PAGE_TITLE


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_page_passes_optional_fields(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.create_portal_page = AsyncMock(return_value=_CREATED_PAGE)

    async with portal_session as session:
        result = await session.call_tool(
            "create_portal_page",
            {
                "portal_uuid": _PORTAL_UUID,
                "title": _PAGE_TITLE,
                "description": "Landing copy",
                "index": 1,
            },
        )

    assert result.isError is False
    mock_portal_client.create_portal_page.assert_awaited_once_with(
        _PORTAL_UUID,
        _PAGE_TITLE,
        description="Landing copy",
        index=1,
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_page_permission_denied_returns_actionable_error(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.create_portal_page = AsyncMock(
        side_effect=ValueError(_PORTAL_PERMISSION_DENIED_MSG)
    )

    async with portal_session as session:
        result = await session.call_tool(
            "create_portal_page",
            {"portal_uuid": _PORTAL_UUID, "title": _PAGE_TITLE},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload).lower()
    assert "create_portal" in message or "manage_portals" in message


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_page_rejects_negative_index(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "create_portal_page",
            {"portal_uuid": _PORTAL_UUID, "title": _PAGE_TITLE, "index": -1},
        )

    mock_portal_client.create_portal_page.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert "index" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_page_rejects_empty_portal_uuid(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "create_portal_page",
            {"portal_uuid": "  ", "title": _PAGE_TITLE},
        )

    mock_portal_client.create_portal_page.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "portal_uuid" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_page_success(
    portal_session, mock_portal_client, extract_payload
):
    updated_page = {**_CREATED_PAGE, "title": "Renamed Page"}
    mock_portal_client.update_portal_page = AsyncMock(return_value=updated_page)

    async with portal_session as session:
        result = await session.call_tool(
            "update_portal_page",
            {
                "portal_uuid": _PORTAL_UUID,
                "page_id": _PAGE_UUID,
                "title": "Renamed Page",
            },
        )

    assert result.isError is False
    mock_portal_client.update_portal_page.assert_awaited_once_with(
        _PORTAL_UUID,
        _PAGE_UUID,
        title="Renamed Page",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["title"] == "Renamed Page"


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_page_rejects_negative_index(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "update_portal_page",
            {
                "portal_uuid": _PORTAL_UUID,
                "page_id": _PAGE_UUID,
                "index": -1,
            },
        )

    mock_portal_client.update_portal_page.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert "index" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_page_rejects_when_no_fields_to_update(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "update_portal_page",
            {"portal_uuid": _PORTAL_UUID, "page_id": _PAGE_UUID},
        )

    mock_portal_client.update_portal_page.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert "at least one" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_page_preview_does_not_delete(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "delete_portal_page",
            {"portal_uuid": _PORTAL_UUID, "page_id": _PAGE_UUID},
        )

    assert result.isError is False
    mock_portal_client.delete_portal_page.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert _PAGE_UUID in payload["resource"]
    assert "confirm=True" in payload["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_page_success(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.delete_portal_page = AsyncMock(
        return_value={"deletePage": {"success": True}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "delete_portal_page",
            {
                "portal_uuid": _PORTAL_UUID,
                "page_id": _PAGE_UUID,
                "confirm": True,
            },
        )

    assert result.isError is False
    mock_portal_client.delete_portal_page.assert_awaited_once_with(
        _PORTAL_UUID, _PAGE_UUID
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["deletePage"]["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_page_fails_when_success_false(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.delete_portal_page = AsyncMock(
        return_value={"deletePage": {"success": False}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "delete_portal_page",
            {
                "portal_uuid": _PORTAL_UUID,
                "page_id": _PAGE_UUID,
                "confirm": True,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "failed to delete" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_page_has_destructive_hint(portal_session):
    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    delete_tool = tool_map["delete_portal_page"]
    assert delete_tool.annotations is not None
    assert delete_tool.annotations.destructiveHint is True
    assert delete_tool.annotations.readOnlyHint is not True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_sort_portal_pages_success(
    portal_session, mock_portal_client, extract_payload
):
    page_ids = [_PAGE_UUID_2, _PAGE_UUID]
    mock_portal_client.sort_portal_pages = AsyncMock(
        return_value={"sortPages": {"success": True}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "sort_portal_pages",
            {"portal_uuid": _PORTAL_UUID, "page_ids": page_ids},
        )

    assert result.isError is False
    mock_portal_client.sort_portal_pages.assert_awaited_once_with(
        _PORTAL_UUID, page_ids
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["sortPages"]["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_sort_portal_pages_rejects_empty_page_ids(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "sort_portal_pages",
            {"portal_uuid": _PORTAL_UUID, "page_ids": []},
        )

    mock_portal_client.sort_portal_pages.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert "page_ids" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_sort_portal_pages_rejects_duplicate_page_ids(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "sort_portal_pages",
            {"portal_uuid": _PORTAL_UUID, "page_ids": [_PAGE_UUID, _PAGE_UUID]},
        )

    mock_portal_client.sort_portal_pages.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert "duplicate" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
@pytest.mark.parametrize(
    "invalid_page_ids",
    [
        ["   "],
        [True],
        [None],
        [{"id": "x"}],
    ],
)
async def test_sort_portal_pages_rejects_invalid_page_id_items(
    portal_session,
    mock_portal_client,
    extract_payload,
    invalid_page_ids,
):
    async with portal_session as session:
        result = await session.call_tool(
            "sort_portal_pages",
            {"portal_uuid": _PORTAL_UUID, "page_ids": invalid_page_ids},
        )

    mock_portal_client.sort_portal_pages.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "page_ids" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_sort_portal_pages_fails_when_success_false(
    portal_session, mock_portal_client, extract_payload
):
    page_ids = [_PAGE_UUID_2, _PAGE_UUID]
    mock_portal_client.sort_portal_pages = AsyncMock(
        return_value={"sortPages": {"success": False}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "sort_portal_pages",
            {"portal_uuid": _PORTAL_UUID, "page_ids": page_ids},
        )

    assert result.isError is False
    mock_portal_client.sort_portal_pages.assert_awaited_once_with(
        _PORTAL_UUID, page_ids
    )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "failed to reorder" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_page_layout_success(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.update_portal_page_layout = AsyncMock(
        return_value={"updatePageLayout": {"success": True}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "update_portal_page_layout",
            {"page_id": _PAGE_UUID, "layout": _PAGE_LAYOUT},
        )

    assert result.isError is False
    mock_portal_client.update_portal_page_layout.assert_awaited_once_with(
        _PAGE_UUID, _PAGE_LAYOUT
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["updatePageLayout"]["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_page_layout_fails_when_success_false(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.update_portal_page_layout = AsyncMock(
        return_value={"updatePageLayout": {"success": False}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "update_portal_page_layout",
            {"page_id": _PAGE_UUID, "layout": _PAGE_LAYOUT},
        )

    assert result.isError is False
    mock_portal_client.update_portal_page_layout.assert_awaited_once_with(
        _PAGE_UUID, _PAGE_LAYOUT
    )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "failed to update layout" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_page_layout_permission_denied_returns_actionable_error(
    portal_session, mock_portal_client, extract_payload
):
    exc = TransportQueryError("forbidden")
    exc.errors = [{"extensions": {"code": "PERMISSION_DENIED"}}]
    mock_portal_client.update_portal_page_layout = AsyncMock(side_effect=exc)

    async with portal_session as session:
        result = await session.call_tool(
            "update_portal_page_layout",
            {"page_id": _PAGE_UUID, "layout": _PAGE_LAYOUT},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload).lower()
    assert "create_portal" in message or "manage_portals" in message


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_page_layout_transport_error_returns_envelope(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.update_portal_page_layout = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "timeout"}])
    )

    async with portal_session as session:
        result = await session.call_tool(
            "update_portal_page_layout",
            {"page_id": _PAGE_UUID, "layout": _PAGE_LAYOUT},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    err = payload.get("error")
    assert isinstance(err, dict) and "message" in err


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_page_write_tools_are_not_readonly(portal_session):
    write_tool_names = [
        "create_portal_page",
        "update_portal_page",
        "delete_portal_page",
        "sort_portal_pages",
        "update_portal_page_layout",
    ]

    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    for name in write_tool_names:
        tool = tool_map[name]
        assert tool.annotations is not None, f"{name} missing annotations"
        assert tool.annotations.readOnlyHint is not True, (
            f"{name} should not be readOnlyHint=True"
        )


# ---------------------------------------------------------------------------
# Portal element write tools
# ---------------------------------------------------------------------------

_ELEMENT_WRITE_TOOL_NAMES = [
    "create_portal_element",
    "update_portal_element",
    "delete_portal_element",
    "duplicate_portal_element",
]


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_element_success(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.create_portal_element = AsyncMock(return_value=_CREATED_ELEMENT)

    async with portal_session as session:
        result = await session.call_tool(
            "create_portal_element",
            {
                "page_id": _PAGE_UUID,
                "type": "forms",
                "metadata": _FORMS_METADATA,
                "data_sources": _FORMS_DATA_SOURCES,
            },
        )

    assert result.isError is False
    mock_portal_client.create_portal_element.assert_awaited_once_with(
        _PAGE_UUID,
        type="forms",
        metadata=_FORMS_METADATA,
        data_sources=_FORMS_DATA_SOURCES,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["uuid"] == _ELEMENT_UUID
    assert payload["data"]["type"] == "forms"


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_element_rejects_invalid_metadata_before_client(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "create_portal_element",
            {
                "page_id": _PAGE_UUID,
                "type": "forms",
                "metadata": {},
            },
        )

    mock_portal_client.create_portal_element.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    message = tool_error_message(payload).lower()
    assert "name" in message


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_element_rejects_unknown_type_before_client(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "create_portal_element",
            {
                "page_id": _PAGE_UUID,
                "type": "not_a_portal_element_type",
                "metadata": {},
            },
        )

    mock_portal_client.create_portal_element.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_element_rejects_blank_page_id(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "create_portal_element",
            {
                "page_id": "  ",
                "type": "forms",
                "metadata": _FORMS_METADATA,
            },
        )

    mock_portal_client.create_portal_element.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "page_id" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_element_permission_denied_returns_actionable_error(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.create_portal_element = AsyncMock(
        side_effect=ValueError(_PORTAL_PERMISSION_DENIED_MSG)
    )

    async with portal_session as session:
        result = await session.call_tool(
            "create_portal_element",
            {
                "page_id": _PAGE_UUID,
                "type": "forms",
                "metadata": _FORMS_METADATA,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload).lower()
    assert "create_portal" in message or "manage_portals" in message


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_portal_element_docstring_mentions_portal_tool_in_ui(
    portal_session,
):
    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    create_tool = tool_map["create_portal_element"]
    description = (create_tool.description or "").lower()
    assert "tool" in description or "widget" in description


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_element_success(
    portal_session, mock_portal_client, extract_payload
):
    link_metadata = {
        "linkUrl": "https://example.com/pipefy",
        "linkName": "Open",
    }
    updated_element = {
        **_CREATED_ELEMENT,
        "type": "link",
        "metadata": link_metadata,
    }
    mock_portal_client.update_portal_element = AsyncMock(return_value=updated_element)

    async with portal_session as session:
        result = await session.call_tool(
            "update_portal_element",
            {
                "element_id": _ELEMENT_UUID,
                "page_id": _PAGE_UUID,
                "type": "link",
                "metadata": link_metadata,
            },
        )

    assert result.isError is False
    mock_portal_client.update_portal_element.assert_awaited_once_with(
        _ELEMENT_UUID,
        _PAGE_UUID,
        type="link",
        metadata=link_metadata,
        data_sources=[],
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["metadata"]["linkUrl"] == "https://example.com/pipefy"


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_portal_element_rejects_invalid_metadata_before_client(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "update_portal_element",
            {
                "element_id": _ELEMENT_UUID,
                "page_id": _PAGE_UUID,
                "type": "link",
                "metadata": {},
            },
        )

    mock_portal_client.update_portal_element.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert "linkname" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_element_preview_does_not_delete(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "delete_portal_element",
            {"element_id": _ELEMENT_UUID, "page_id": _PAGE_UUID},
        )

    assert result.isError is False
    mock_portal_client.delete_portal_element.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert _ELEMENT_UUID in payload["resource"]
    assert "confirm=True" in payload["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_element_success(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.delete_portal_element = AsyncMock(
        return_value={"deleteElement": {"success": True}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "delete_portal_element",
            {
                "element_id": _ELEMENT_UUID,
                "page_id": _PAGE_UUID,
                "confirm": True,
            },
        )

    assert result.isError is False
    mock_portal_client.delete_portal_element.assert_awaited_once_with(
        _ELEMENT_UUID, _PAGE_UUID
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["deleteElement"]["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_element_fails_when_success_false(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.delete_portal_element = AsyncMock(
        return_value={"deleteElement": {"success": False}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "delete_portal_element",
            {
                "element_id": _ELEMENT_UUID,
                "page_id": _PAGE_UUID,
                "confirm": True,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "failed to delete" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_portal_element_has_destructive_hint(portal_session):
    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    delete_tool = tool_map["delete_portal_element"]
    assert delete_tool.annotations is not None
    assert delete_tool.annotations.destructiveHint is True
    assert delete_tool.annotations.readOnlyHint is not True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_duplicate_portal_element_success(
    portal_session, mock_portal_client, extract_payload
):
    duplicated = {
        "id": "el-copy",
        "uuid": "el-copy",
        "type": "text",
        "metadata": {},
    }
    mock_portal_client.duplicate_portal_element = AsyncMock(return_value=duplicated)

    async with portal_session as session:
        result = await session.call_tool(
            "duplicate_portal_element",
            {
                "element_id": _ELEMENT_UUID,
                "portal_uuid": _PORTAL_UUID,
                "page_id": _PAGE_UUID,
            },
        )

    assert result.isError is False
    mock_portal_client.duplicate_portal_element.assert_awaited_once_with(
        element_id=_ELEMENT_UUID,
        portal_uuid=_PORTAL_UUID,
        page_id=_PAGE_UUID,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["uuid"] == "el-copy"


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_duplicate_portal_element_rejects_blank_portal_uuid(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "duplicate_portal_element",
            {
                "element_id": _ELEMENT_UUID,
                "portal_uuid": "  ",
                "page_id": _PAGE_UUID,
            },
        )

    mock_portal_client.duplicate_portal_element.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "portal_uuid" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_element_write_tools_are_not_readonly(portal_session):
    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    for name in _ELEMENT_WRITE_TOOL_NAMES:
        tool = tool_map[name]
        assert tool.annotations is not None, f"{name} missing annotations"
        assert tool.annotations.readOnlyHint is not True, (
            f"{name} should not be readOnlyHint=True"
        )


# ---------------------------------------------------------------------------
# Sub-portal write tools (task 6.3 RED — tools registered in 6.4)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_sub_portal_success(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.create_sub_portal = AsyncMock(return_value=_CREATED_SUB_PORTAL)

    async with portal_session as session:
        result = await session.call_tool(
            "create_sub_portal",
            {
                "main_portal_uuid": _MAIN_PORTAL_UUID,
                "name": _SUB_PORTAL_NAME,
            },
        )

    assert result.isError is False
    mock_portal_client.create_sub_portal.assert_awaited_once_with(
        _MAIN_PORTAL_UUID,
        _SUB_PORTAL_NAME,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["uuid"] == _SUB_PORTAL_UUID
    assert payload["data"]["name"] == _SUB_PORTAL_NAME


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_sub_portal_rejects_blank_main_portal_uuid(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "create_sub_portal",
            {"main_portal_uuid": "  ", "name": _SUB_PORTAL_NAME},
        )

    mock_portal_client.create_sub_portal.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "main_portal_uuid" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_sub_portal_transport_error_not_permission_envelope(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.create_sub_portal = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "timeout"}])
    )

    async with portal_session as session:
        result = await session.call_tool(
            "create_sub_portal",
            {"main_portal_uuid": _MAIN_PORTAL_UUID},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload).lower()
    assert "timeout" in message
    assert "manage_portals" not in message


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_sub_portal_element_success(
    portal_session, mock_portal_client, extract_payload
):
    mutation_result = {"updateSubPortalElement": {"success": True}}
    mock_portal_client.update_sub_portal_element = AsyncMock(
        return_value=mutation_result
    )

    async with portal_session as session:
        result = await session.call_tool(
            "update_sub_portal_element",
            {
                "portal_uuid": _MAIN_PORTAL_UUID,
                "element_id": _FORMS_ELEMENT_ID,
                "sub_portal_uuid": _SUB_PORTAL_UUID,
            },
        )

    assert result.isError is False
    mock_portal_client.update_sub_portal_element.assert_awaited_once_with(
        _MAIN_PORTAL_UUID,
        _FORMS_ELEMENT_ID,
        _SUB_PORTAL_UUID,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["updateSubPortalElement"]["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_sub_portal_element_rejects_blank_sub_portal_uuid(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "update_sub_portal_element",
            {
                "portal_uuid": _MAIN_PORTAL_UUID,
                "element_id": _FORMS_ELEMENT_ID,
                "sub_portal_uuid": "  ",
            },
        )

    mock_portal_client.update_sub_portal_element.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "sub_portal_uuid" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_sub_portal_element_fails_when_success_false(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.update_sub_portal_element = AsyncMock(
        return_value={"updateSubPortalElement": {"success": False}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "update_sub_portal_element",
            {
                "portal_uuid": _MAIN_PORTAL_UUID,
                "element_id": _FORMS_ELEMENT_ID,
                "sub_portal_uuid": _SUB_PORTAL_UUID,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "failed" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_publish_sub_portal_success(
    portal_session, mock_portal_client, extract_payload
):
    mutation_result = {"updateSubPortalElement": {"success": True}}
    mock_portal_client.publish_sub_portal = AsyncMock(return_value=mutation_result)

    async with portal_session as session:
        result = await session.call_tool(
            "publish_sub_portal",
            {
                "portal_uuid": _MAIN_PORTAL_UUID,
                "element_id": _FORMS_ELEMENT_ID,
                "sub_portal_uuid": _SUB_PORTAL_UUID,
            },
        )

    assert result.isError is False
    mock_portal_client.publish_sub_portal.assert_awaited_once_with(
        _MAIN_PORTAL_UUID,
        _FORMS_ELEMENT_ID,
        _SUB_PORTAL_UUID,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["updateSubPortalElement"]["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_publish_sub_portal_rejects_blank_element_id(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "publish_sub_portal",
            {
                "portal_uuid": _MAIN_PORTAL_UUID,
                "element_id": "  ",
                "sub_portal_uuid": _SUB_PORTAL_UUID,
            },
        )

    mock_portal_client.publish_sub_portal.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "element_id" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_publish_sub_portal_fails_when_success_false(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.publish_sub_portal = AsyncMock(
        return_value={"updateSubPortalElement": {"success": False}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "publish_sub_portal",
            {
                "portal_uuid": _MAIN_PORTAL_UUID,
                "element_id": _FORMS_ELEMENT_ID,
                "sub_portal_uuid": _SUB_PORTAL_UUID,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "failed" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_publish_sub_portal_permission_denied_returns_actionable_error(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.publish_sub_portal = AsyncMock(
        side_effect=PortalPermissionError(_PORTAL_PERMISSION_DENIED_MSG)
    )

    async with portal_session as session:
        result = await session.call_tool(
            "publish_sub_portal",
            {
                "portal_uuid": _MAIN_PORTAL_UUID,
                "element_id": _FORMS_ELEMENT_ID,
                "sub_portal_uuid": _SUB_PORTAL_UUID,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload).lower()
    assert "create_portal" in message or "manage_portals" in message


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_unpublish_sub_portal_success(
    portal_session, mock_portal_client, extract_payload
):
    mutation_result = {"updateSubPortalElement": {"success": True}}
    mock_portal_client.unpublish_sub_portal = AsyncMock(return_value=mutation_result)

    async with portal_session as session:
        result = await session.call_tool(
            "unpublish_sub_portal",
            {
                "portal_uuid": _MAIN_PORTAL_UUID,
                "element_id": _FORMS_ELEMENT_ID,
            },
        )

    assert result.isError is False
    mock_portal_client.unpublish_sub_portal.assert_awaited_once_with(
        _MAIN_PORTAL_UUID,
        _FORMS_ELEMENT_ID,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["updateSubPortalElement"]["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_unpublish_sub_portal_rejects_blank_portal_uuid(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "unpublish_sub_portal",
            {
                "portal_uuid": "  ",
                "element_id": _FORMS_ELEMENT_ID,
            },
        )

    mock_portal_client.unpublish_sub_portal.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "portal_uuid" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_unpublish_sub_portal_fails_when_success_false(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.unpublish_sub_portal = AsyncMock(
        return_value={"updateSubPortalElement": {"success": False}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "unpublish_sub_portal",
            {
                "portal_uuid": _MAIN_PORTAL_UUID,
                "element_id": _FORMS_ELEMENT_ID,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "failed" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_sub_portal_element_preview_does_not_delete(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "delete_sub_portal_element",
            {
                "portal_uuid": _MAIN_PORTAL_UUID,
                "element_id": _FORMS_ELEMENT_ID,
            },
        )

    assert result.isError is False
    mock_portal_client.delete_sub_portal_element.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert _FORMS_ELEMENT_ID in payload["resource"]
    assert "confirm=True" in payload["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_sub_portal_element_success(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.delete_sub_portal_element = AsyncMock(
        return_value={"deleteSubPortalElement": {"success": True}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "delete_sub_portal_element",
            {
                "portal_uuid": _MAIN_PORTAL_UUID,
                "element_id": _FORMS_ELEMENT_ID,
                "confirm": True,
            },
        )

    assert result.isError is False
    mock_portal_client.delete_sub_portal_element.assert_awaited_once_with(
        _MAIN_PORTAL_UUID,
        _FORMS_ELEMENT_ID,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["deleteSubPortalElement"]["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_sub_portal_element_fails_when_success_false(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.delete_sub_portal_element = AsyncMock(
        return_value={"deleteSubPortalElement": {"success": False}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "delete_sub_portal_element",
            {
                "portal_uuid": _MAIN_PORTAL_UUID,
                "element_id": _FORMS_ELEMENT_ID,
                "confirm": True,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "failed" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_sub_portal_element_has_destructive_hint(portal_session):
    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    delete_tool = tool_map["delete_sub_portal_element"]
    assert delete_tool.annotations is not None
    assert delete_tool.annotations.destructiveHint is True
    assert delete_tool.annotations.readOnlyHint is not True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_sub_portal_preview_does_not_delete(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "delete_sub_portal",
            {"sub_portal_uuid": _SUB_PORTAL_UUID},
        )

    assert result.isError is False
    mock_portal_client.delete_sub_portal.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert _SUB_PORTAL_UUID in payload["resource"]
    assert "confirm=True" in payload["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_sub_portal_success(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.delete_sub_portal = AsyncMock(
        return_value={"deleteSubPortalInterface": {"success": True}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "delete_sub_portal",
            {"sub_portal_uuid": _SUB_PORTAL_UUID, "confirm": True},
        )

    assert result.isError is False
    mock_portal_client.delete_sub_portal.assert_awaited_once_with(_SUB_PORTAL_UUID)
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["deleteSubPortalInterface"]["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_sub_portal_fails_when_success_false(
    portal_session, mock_portal_client, extract_payload
):
    mock_portal_client.delete_sub_portal = AsyncMock(
        return_value={"deleteSubPortalInterface": {"success": False}}
    )

    async with portal_session as session:
        result = await session.call_tool(
            "delete_sub_portal",
            {"sub_portal_uuid": _SUB_PORTAL_UUID, "confirm": True},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "failed" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_sub_portal_rejects_blank_sub_portal_uuid(
    portal_session, mock_portal_client, extract_payload
):
    async with portal_session as session:
        result = await session.call_tool(
            "delete_sub_portal",
            {"sub_portal_uuid": "  ", "confirm": True},
        )

    mock_portal_client.delete_sub_portal.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "sub_portal_uuid" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_sub_portal_has_destructive_hint(portal_session):
    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    delete_tool = tool_map["delete_sub_portal"]
    assert delete_tool.annotations is not None
    assert delete_tool.annotations.destructiveHint is True
    assert delete_tool.annotations.readOnlyHint is not True


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_sub_portal_write_tools_are_not_readonly(portal_session):
    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    for name in _SUB_PORTAL_WRITE_TOOL_NAMES:
        tool = tool_map[name]
        assert tool.annotations is not None, f"{name} missing annotations"
        assert tool.annotations.readOnlyHint is not True, (
            f"{name} should not be readOnlyHint=True"
        )


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_create_sub_portal_docstring_mentions_publish_semantics(
    portal_session,
):
    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    description = (tool_map["create_sub_portal"].description or "").lower()
    assert "published" in description
    assert "update_portal" in description or "visibility" in description


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_update_sub_portal_element_docstring_mentions_publish_semantics(
    portal_session,
):
    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    description = (tool_map["update_sub_portal_element"].description or "").lower()
    assert "published" in description or "update_portal" in description


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_publish_sub_portal_docstring_mentions_subportals_published(
    portal_session,
):
    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    description = (tool_map["publish_sub_portal"].description or "").lower()
    assert "subportals" in description or "sub portals" in description
    assert "get_portal" in description
    assert "createelement" not in description.replace(" ", "")


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_unpublish_sub_portal_docstring_mentions_subportals_published(
    portal_session,
):
    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    description = (tool_map["unpublish_sub_portal"].description or "").lower()
    assert "subportals" in description or "sub portals" in description
    assert "get_portal" in description


@pytest.mark.anyio
@pytest.mark.parametrize("portal_session", [None], indirect=True)
async def test_delete_sub_portal_docstring_warns_irreversible(portal_session):
    async with portal_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    description = (tool_map["delete_sub_portal"].description or "").lower()
    assert "irreversible" in description
