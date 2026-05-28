"""Tests for portal MCP tool helpers."""

from __future__ import annotations

import pytest
from gql.transport.exceptions import TransportQueryError
from pipefy_sdk.exceptions import PortalPermissionError

from pipefy_mcp.tools.portal_tool_helpers import (
    map_portal_error_to_message,
    validate_portal_page_index,
    validate_sort_page_ids_no_duplicates,
)

_PORTAL_PERMISSION_MSG = (
    "Permission denied. Request organization permissions such as "
    "`create_portal` or `manage_portals` from your admin."
)


@pytest.mark.unit
def test_map_portal_error_returns_portal_permission_message() -> None:
    """Pre-mapped SDK permission errors are returned without substring heuristics."""
    exc = PortalPermissionError(_PORTAL_PERMISSION_MSG)
    assert map_portal_error_to_message(exc) == _PORTAL_PERMISSION_MSG


@pytest.mark.unit
def test_map_portal_error_permission_denied_transport_query_error() -> None:
    """GraphQL PERMISSION_DENIED codes map to portal permission guidance."""
    exc = TransportQueryError("forbidden")
    exc.errors = [{"extensions": {"code": "PERMISSION_DENIED"}}]
    assert "create_portal" in map_portal_error_to_message(exc)
    assert "manage_portals" in map_portal_error_to_message(exc)


@pytest.mark.unit
def test_map_portal_error_permission_denied_internal_api_value_error() -> None:
    """internal_api ValueError with [code=PERMISSION_DENIED] maps to guidance."""
    exc = ValueError("User denied [code=PERMISSION_DENIED] [correlation_id=abc-123]")
    message = map_portal_error_to_message(exc)
    assert "create_portal" in message or "manage_portals" in message


@pytest.mark.unit
def test_map_portal_error_non_permission_internal_api_value_error_strips_markers() -> (
    None
):
    """Non-permission internal_api ValueError returns marker-free text."""
    exc = ValueError("Bad request [code=BAD_REQUEST] [correlation_id=abc-123]")
    assert map_portal_error_to_message(exc) == "Bad request"


@pytest.mark.unit
@pytest.mark.parametrize("index", [-1, True])
def test_validate_portal_page_index_rejects_invalid(index: int | bool) -> None:
    err = validate_portal_page_index(index)  # type: ignore[arg-type]
    assert err is not None
    assert err["error"]["code"] == "INVALID_ARGUMENTS"
    assert "index" in str(err["error"]["message"]).lower()


@pytest.mark.unit
def test_validate_portal_page_index_accepts_zero_and_none() -> None:
    assert validate_portal_page_index(None) is None
    assert validate_portal_page_index(0) is None


@pytest.mark.unit
def test_validate_sort_page_ids_no_duplicates_rejects_dupes() -> None:
    err = validate_sort_page_ids_no_duplicates(["a", "a"])
    assert err is not None
    assert "duplicate" in str(err["error"]["message"]).lower()
