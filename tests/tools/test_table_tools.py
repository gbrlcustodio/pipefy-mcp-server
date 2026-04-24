"""Tests for database table MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.table_tools import TableTools
from pipefy_mcp.tools.tool_error_envelope import tool_error_message
from tests.pagination_test_defaults import DEFAULT_FIRST
from tests.tools.conftest import assert_invalid_arguments_envelope


@pytest.fixture
def mock_table_client():
    client = MagicMock(PipefyClient)
    client.get_table = AsyncMock()
    client.get_tables = AsyncMock()
    client.get_table_records = AsyncMock()
    client.get_table_record = AsyncMock()
    client.find_records = AsyncMock()
    client.create_table = AsyncMock()
    client.update_table = AsyncMock()
    client.delete_table = AsyncMock()
    client.create_table_record = AsyncMock()
    client.update_table_record = AsyncMock()
    client.delete_table_record = AsyncMock()
    client.set_table_record_field_value = AsyncMock()
    client.create_table_field = AsyncMock()
    client.update_table_field = AsyncMock()
    client.delete_table_field = AsyncMock()
    client.search_tables = AsyncMock()
    return client


@pytest.fixture
def table_mcp_server(mock_table_client):
    mcp = FastMCP("Table Tools Test")
    TableTools.register(mcp, mock_table_client)
    return mcp


@pytest.fixture
def table_session(table_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        table_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_success(table_session, mock_table_client, extract_payload):
    mock_table_client.get_table.return_value = {
        "table": {"id": "1", "name": "Catalog"},
    }

    async with table_session as session:
        result = await session.call_tool("get_table", {"table_id": 1})

    assert result.isError is False
    mock_table_client.get_table.assert_awaited_once_with("1")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["table"]["name"] == "Catalog"


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.get_table.side_effect = TransportQueryError(
        "failed", errors=[{"message": "not found"}]
    )

    async with table_session as session:
        result = await session.call_tool("get_table", {"table_id": 9})

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_tables_success(table_session, mock_table_client, extract_payload):
    mock_table_client.get_tables.return_value = {"tables": []}

    async with table_session as session:
        result = await session.call_tool("get_tables", {"table_ids": [1, 2]})

    assert result.isError is False
    mock_table_client.get_tables.assert_awaited_once_with(["1", "2"])
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_tables_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.get_tables.side_effect = TransportQueryError(
        "failed", errors=[{"message": "boom"}]
    )

    async with table_session as session:
        result = await session.call_tool("get_tables", {"table_ids": ["a"]})

    payload = extract_payload(result)
    assert payload["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_records_success_and_pagination(
    table_session, mock_table_client, extract_payload, legacy_envelope
):
    """Flag=false — legacy pagination shape (pageInfo camelCase)."""
    mock_table_client.get_table_records.return_value = {
        "table_records": {
            "edges": [],
            "pageInfo": {"hasNextPage": True, "endCursor": "n1"},
        }
    }

    async with table_session as session:
        result = await session.call_tool(
            "get_table_records",
            {"table_id": "t1", "first": DEFAULT_FIRST},
        )

    mock_table_client.get_table_records.assert_awaited_once_with(
        "t1", first=DEFAULT_FIRST, after=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["pagination"]["hasNextPage"] is True
    assert payload["pagination"]["endCursor"] == "n1"


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_records_unified_envelope_pagination(
    table_session, mock_table_client, extract_payload, unified_envelope
):
    """Flag=true — pagination block uses snake_case keys and includes page_size."""
    mock_table_client.get_table_records.return_value = {
        "table_records": {
            "edges": [],
            "pageInfo": {"hasNextPage": True, "endCursor": "n1"},
        }
    }
    async with table_session as session:
        result = await session.call_tool(
            "get_table_records",
            {"table_id": "t1", "first": DEFAULT_FIRST},
        )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["pagination"] == {
        "has_more": True,
        "end_cursor": "n1",
        "page_size": DEFAULT_FIRST,
    }
    assert "data" in payload
    assert "table_records" in payload["data"]


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_records_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.get_table_records.side_effect = TransportQueryError(
        "failed", errors=[{"message": "bad"}]
    )

    async with table_session as session:
        result = await session.call_tool(
            "get_table_records",
            {"table_id": 1, "first": 10},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_record_success(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.get_table_record.return_value = {
        "table_record": {"id": "r1"},
    }

    async with table_session as session:
        result = await session.call_tool("get_table_record", {"record_id": "r1"})

    mock_table_client.get_table_record.assert_awaited_once_with("r1")
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_record_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.get_table_record.side_effect = TransportQueryError(
        "failed", errors=[{"message": "missing"}]
    )

    async with table_session as session:
        result = await session.call_tool("get_table_record", {"record_id": 5})

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_find_records_success(table_session, mock_table_client, extract_payload):
    mock_table_client.find_records.return_value = {
        "findRecords": {
            "edges": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }
    }

    async with table_session as session:
        result = await session.call_tool(
            "find_records",
            {"table_id": 3, "field_id": "f", "field_value": "x"},
        )

    mock_table_client.find_records.assert_awaited_once_with(
        "3", "f", "x", first=None, after=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["pagination"]["hasNextPage"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_find_records_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.find_records.side_effect = TransportQueryError(
        "failed", errors=[{"message": "search failed"}]
    )

    async with table_session as session:
        result = await session.call_tool(
            "find_records",
            {"table_id": 1, "field_id": "id", "field_value": "v"},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
@pytest.mark.parametrize("bad_extra", [[], "not-an-object", 99])
async def test_create_table_rejects_non_object_extra_input(
    table_session, mock_table_client, extract_payload, bad_extra
):
    async with table_session as session:
        result = await session.call_tool(
            "create_table",
            {"name": "T", "organization_id": 1, "extra_input": bad_extra},
        )

    mock_table_client.create_table.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "extra_input" in tool_error_message(payload)
    assert "dict" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
@pytest.mark.parametrize("bad_extra", [{}, "bad", [1]])
async def test_update_table_rejects_non_object_extra_input(
    table_session, mock_table_client, extract_payload, bad_extra
):
    async with table_session as session:
        result = await session.call_tool(
            "update_table",
            {
                "table_id": 1,
                "name": "N",
                "extra_input": bad_extra,
            },
        )

    payload = extract_payload(result)
    if bad_extra == {}:
        mock_table_client.update_table.assert_awaited_once_with("1", name="N")
        assert payload["success"] is True
    else:
        mock_table_client.update_table.assert_not_called()
        assert payload["success"] is False
        assert "extra_input" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
@pytest.mark.parametrize("bad_extra", ["x", []])
async def test_create_table_record_rejects_non_object_extra_input(
    table_session, mock_table_client, extract_payload, bad_extra
):
    async with table_session as session:
        result = await session.call_tool(
            "create_table_record",
            {
                "table_id": 10,
                "fields": {"f1": "a"},
                "extra_input": bad_extra,
            },
        )

    mock_table_client.create_table_record.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "extra_input" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
@pytest.mark.parametrize("bad_extra", [1, "extra", ["a"]])
async def test_create_table_field_rejects_non_object_extra_input(
    table_session, mock_table_client, extract_payload, bad_extra
):
    async with table_session as session:
        result = await session.call_tool(
            "create_table_field",
            {
                "table_id": 1,
                "label": "Code",
                "field_type": "short_text",
                "extra_input": bad_extra,
            },
        )

    mock_table_client.create_table_field.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "extra_input" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_field_omitted_extra_input_ok(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.update_table_field.return_value = {
        "updateTableField": {"table_field": {}},
    }

    async with table_session as session:
        result = await session.call_tool(
            "update_table_field",
            {"field_id": "slug-1", "table_id": 123, "label": "New"},
        )

    mock_table_client.update_table_field.assert_awaited_once_with(
        "slug-1", table_id="123", label="New"
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
@pytest.mark.parametrize("bad_extra", ["bad", []])
async def test_update_table_field_rejects_non_object_extra_input(
    table_session, mock_table_client, extract_payload, bad_extra
):
    async with table_session as session:
        result = await session.call_tool(
            "update_table_field",
            {
                "field_id": "slug-1",
                "label": "New",
                "extra_input": bad_extra,
            },
        )

    mock_table_client.update_table_field.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "extra_input" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_record_rejects_unsupported_field_keys_only(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "update_table_record",
            {"record_id": 8, "fields": {"unknown": "v", "other": 1}},
        )

    mock_table_client.update_table_record.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "title" in tool_error_message(payload)
    assert "due_date" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_record_rejects_list_entry_missing_field_keys(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "create_table_record",
            {"table_id": 10, "fields": [{"field_id": "f1"}]},
        )

    mock_table_client.create_table_record.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "index 0" in tool_error_message(payload)
    assert "field_value" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_record_rejects_non_dict_list_entry(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "create_table_record",
            {"table_id": 10, "fields": ["not-a-dict"]},
        )

    mock_table_client.create_table_record.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "index 0" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_success(table_session, mock_table_client, extract_payload):
    mock_table_client.create_table.return_value = {
        "createTable": {"table": {"id": "9", "name": "T"}},
    }

    async with table_session as session:
        result = await session.call_tool(
            "create_table",
            {"name": "T", "organization_id": 100},
        )

    mock_table_client.create_table.assert_awaited_once_with("T", "100")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "createTable" in payload["result"]


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.create_table.side_effect = TransportQueryError(
        "failed", errors=[{"message": "reject"}]
    )

    async with table_session as session:
        result = await session.call_tool(
            "create_table",
            {"name": "X", "organization_id": 1},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_success(table_session, mock_table_client, extract_payload):
    mock_table_client.update_table.return_value = {"updateTable": {"table": {}}}

    async with table_session as session:
        result = await session.call_tool(
            "update_table",
            {"table_id": 3, "name": "New"},
        )

    mock_table_client.update_table.assert_awaited_once_with("3", name="New")
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.update_table.side_effect = TransportQueryError(
        "failed", errors=[{"message": "fail"}]
    )

    async with table_session as session:
        result = await session.call_tool(
            "update_table",
            {"table_id": 1, "description": "D"},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_preview(table_session, mock_table_client, extract_payload):
    mock_table_client.get_table.return_value = {
        "table": {"id": "5", "name": "Cat", "table_fields": []},
    }

    async with table_session as session:
        result = await session.call_tool(
            "delete_table",
            {"table_id": 5, "confirm": False},
        )

    mock_table_client.delete_table.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert payload["resource"] == "table 'Cat' (ID: 5)"


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_confirm_success(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.get_table.return_value = {"table": {"id": "5", "name": "Cat"}}
    mock_table_client.delete_table.return_value = {"deleteTable": {"success": True}}

    async with table_session as session:
        result = await session.call_tool(
            "delete_table",
            {"table_id": 5, "confirm": True},
        )

    mock_table_client.delete_table.assert_awaited_once_with("5")
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_graphql_error_on_confirm(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.get_table.return_value = {"table": {"id": "1", "name": "X"}}
    mock_table_client.delete_table.side_effect = TransportQueryError(
        "failed", errors=[{"message": "cannot"}]
    )

    async with table_session as session:
        result = await session.call_tool(
            "delete_table",
            {"table_id": 1, "confirm": True},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_record_success(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.create_table_record.return_value = {
        "createTableRecord": {"table_record": {"id": "r1"}},
    }

    async with table_session as session:
        result = await session.call_tool(
            "create_table_record",
            {"table_id": 10, "fields": {"f1": "a"}},
        )

    mock_table_client.create_table_record.assert_awaited_once()
    call_kw = mock_table_client.create_table_record.call_args
    assert call_kw[0][0] == "10"
    assert call_kw[0][1] == {"f1": "a"}
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_record_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.create_table_record.side_effect = TransportQueryError(
        "failed", errors=[{"message": "bad"}]
    )

    async with table_session as session:
        result = await session.call_tool(
            "create_table_record",
            {"table_id": 1, "fields": {"x": "y"}},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_record_success(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.update_table_record.return_value = {
        "updateTableRecord": {"table_record": {}},
    }

    async with table_session as session:
        result = await session.call_tool(
            "update_table_record",
            {"record_id": 8, "fields": {"title": "Z"}},
        )

    mock_table_client.update_table_record.assert_awaited_once_with("8", {"title": "Z"})
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_record_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.update_table_record.side_effect = TransportQueryError(
        "failed", errors=[{"message": "e"}]
    )

    async with table_session as session:
        result = await session.call_tool(
            "update_table_record",
            {"record_id": 1, "fields": {"title": "t"}},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_record_success(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.delete_table_record.return_value = {
        "deleteTableRecord": {"success": True},
    }

    async with table_session as session:
        result = await session.call_tool(
            "delete_table_record",
            {"record_id": 99, "confirm": True},
        )

    mock_table_client.delete_table_record.assert_awaited_once_with("99")
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_record_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.delete_table_record.side_effect = TransportQueryError(
        "failed", errors=[{"message": "no"}]
    )

    async with table_session as session:
        result = await session.call_tool(
            "delete_table_record", {"record_id": 1, "confirm": True}
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_set_table_record_field_value_success(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.set_table_record_field_value.return_value = {
        "setTableRecordFieldValue": {},
    }

    async with table_session as session:
        result = await session.call_tool(
            "set_table_record_field_value",
            {"record_id": 1, "field_id": "f", "value": "x"},
        )

    mock_table_client.set_table_record_field_value.assert_awaited_once_with(
        "1", "f", "x"
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_set_table_record_field_value_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.set_table_record_field_value.side_effect = TransportQueryError(
        "failed", errors=[{"message": "err"}]
    )

    async with table_session as session:
        result = await session.call_tool(
            "set_table_record_field_value",
            {"record_id": 1, "field_id": "f", "value": 1},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_field_success(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.create_table_field.return_value = {
        "createTableField": {"table_field": {"id": "f1"}},
    }

    async with table_session as session:
        result = await session.call_tool(
            "create_table_field",
            {"table_id": 1, "label": "Code", "field_type": "short_text"},
        )

    mock_table_client.create_table_field.assert_awaited_once_with(
        "1", "Code", "short_text"
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_field_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.create_table_field.side_effect = TransportQueryError(
        "failed", errors=[{"message": "bad"}]
    )

    async with table_session as session:
        result = await session.call_tool(
            "create_table_field",
            {"table_id": 1, "label": "L", "field_type": "t"},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_field_success(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.update_table_field.return_value = {
        "updateTableField": {"table_field": {}},
    }

    async with table_session as session:
        result = await session.call_tool(
            "update_table_field",
            {"field_id": "slug-1", "table_id": 123, "label": "New"},
        )

    mock_table_client.update_table_field.assert_awaited_once_with(
        "slug-1", table_id="123", label="New"
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_field_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.update_table_field.side_effect = TransportQueryError(
        "failed", errors=[{"message": "e"}]
    )

    async with table_session as session:
        result = await session.call_tool(
            "update_table_field",
            {"field_id": 1, "description": "D"},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_field_success(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.delete_table_field.return_value = {
        "deleteTableField": {"success": True},
    }

    async with table_session as session:
        result = await session.call_tool(
            "delete_table_field", {"field_id": 88, "table_id": "tbl_1", "confirm": True}
        )

    mock_table_client.delete_table_field.assert_awaited_once_with("88", "tbl_1")
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_field_graphql_error(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.delete_table_field.side_effect = TransportQueryError(
        "failed", errors=[{"message": "nope"}]
    )

    async with table_session as session:
        result = await session.call_tool(
            "delete_table_field",
            {"field_id": "x", "table_id": "tbl_1", "confirm": True},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_search_tables_without_name_calls_client_with_none(
    table_session, mock_table_client
):
    mock_table_client.search_tables.return_value = {
        "organizations": [{"id": "org1", "name": "Acme", "tables": []}]
    }

    async with table_session as session:
        result = await session.call_tool("search_tables", {})

    assert result.isError is False
    mock_table_client.search_tables.assert_awaited_once_with(None, first=100)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_search_tables_with_name_passes_it_to_client(
    table_session, mock_table_client
):
    mock_table_client.search_tables.return_value = {"organizations": []}

    async with table_session as session:
        result = await session.call_tool("search_tables", {"table_name": "Clients"})

    assert result.isError is False
    mock_table_client.search_tables.assert_awaited_once_with("Clients", first=100)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_search_tables_returns_client_response(
    table_session, mock_table_client, extract_payload, legacy_envelope
):
    expected = {
        "organizations": [
            {
                "id": "org1",
                "name": "Acme",
                "tables": [{"id": "T1", "name": "Clients", "match_score": 100.0}],
            }
        ]
    }
    mock_table_client.search_tables.return_value = expected

    async with table_session as session:
        result = await session.call_tool("search_tables", {"table_name": "Clients"})

    payload = extract_payload(result)
    assert payload == expected


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_search_tables_unified_envelope(
    table_session, mock_table_client, extract_payload, unified_envelope
):
    """Flag=true — raw GraphQL wraps under ``data`` and top-level pagination is added."""
    expected = {
        "organizations": [
            {"id": "org1", "name": "Acme", "tables": []},
        ],
        "search_limits": {"tables_first": 100, "tables_has_next_page": False},
    }
    mock_table_client.search_tables.return_value = expected

    async with table_session as session:
        result = await session.call_tool("search_tables", {"table_name": "Clients"})

    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"] == expected
    assert payload["pagination"] == {
        "has_more": False,
        "end_cursor": None,
        "page_size": 100,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_search_tables_unified_has_more_stays_false_even_with_aggregate_has_next_page(
    table_session, mock_table_client, extract_payload, unified_envelope
):
    """Flag=true, aggregate ``tables_has_next_page=True`` — top-level ``has_more`` stays False.

    The outer tool does not accept ``after`` and is therefore not paginable;
    publishing ``has_more=True`` with ``end_cursor=None`` would mislead agents
    into looping on a null cursor. Per-org cursors inside ``data`` carry the
    real signal (see DD-02).
    """
    response = {
        "organizations": [
            {
                "id": "org1",
                "name": "Acme",
                "tables": [],
                "tables_has_next_page": True,
                "tables_page_end_cursor": "org1-cursor-abc",
            }
        ],
        "search_limits": {"tables_first": 100, "tables_has_next_page": True},
    }
    mock_table_client.search_tables.return_value = response
    async with table_session as session:
        result = await session.call_tool("search_tables", {"table_name": "Clients"})
    payload = extract_payload(result)
    assert payload["pagination"]["has_more"] is False
    assert payload["pagination"]["end_cursor"] is None
    # Per-org cursors are preserved inside ``data`` for agents that need them.
    assert payload["data"]["search_limits"]["tables_has_next_page"] is True
    assert (
        payload["data"]["organizations"][0]["tables_page_end_cursor"]
        == "org1-cursor-abc"
    )


# ---------------------------------------------------------------------------
# Input validation: get_table
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_invalid_table_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool("get_table", {"table_id": 0})

    mock_table_client.get_table.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "table_id" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_empty_table_id(table_session, mock_table_client):
    async with table_session as session:
        result = await session.call_tool("get_table", {"table_id": ""})

    mock_table_client.get_table.assert_not_called()
    assert_invalid_arguments_envelope(result)


# ---------------------------------------------------------------------------
# Input validation: get_tables
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_tables_empty_list(table_session, mock_table_client, extract_payload):
    async with table_session as session:
        result = await session.call_tool("get_tables", {"table_ids": []})

    mock_table_client.get_tables.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "table_ids" in tool_error_message(payload)


# ---------------------------------------------------------------------------
# Input validation: get_table_records
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_records_invalid_table_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "get_table_records", {"table_id": 0, "first": 10}
        )

    mock_table_client.get_table_records.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "table_id" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_records_first_too_small(
    table_session, mock_table_client, extract_payload, envelope_flag
):
    async with table_session as session:
        result = await session.call_tool(
            "get_table_records", {"table_id": "t1", "first": 0}
        )

    mock_table_client.get_table_records.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert payload["error"]["details"] == {"min": 1, "max": 200, "provided": 0}


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_records_first_too_large(
    table_session, mock_table_client, extract_payload, envelope_flag
):
    async with table_session as session:
        result = await session.call_tool(
            "get_table_records", {"table_id": "t1", "first": 201}
        )

    mock_table_client.get_table_records.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    # table_records uses the API-imposed max of 200 (not the default 500).
    assert payload["error"]["details"] == {"min": 1, "max": 200, "provided": 201}


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_search_tables_out_of_bounds_returns_invalid_arguments(
    table_session, mock_table_client, extract_payload, envelope_flag
):
    async with table_session as session:
        result = await session.call_tool("search_tables", {"first": 99999})
    mock_table_client.search_tables.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert payload["error"]["details"] == {"min": 1, "max": 500, "provided": 99999}


# ---------------------------------------------------------------------------
# Input validation: get_table_record
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_record_invalid_record_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool("get_table_record", {"record_id": 0})

    mock_table_client.get_table_record.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "record_id" in tool_error_message(payload)


# ---------------------------------------------------------------------------
# Input validation: find_records
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_find_records_invalid_table_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "find_records",
            {"table_id": 0, "field_id": "f", "field_value": "v"},
        )

    mock_table_client.find_records.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "table_id" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_find_records_blank_field_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "find_records",
            {"table_id": "t1", "field_id": "", "field_value": "v"},
        )

    mock_table_client.find_records.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "field_id" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_find_records_blank_field_value(
    table_session, mock_table_client, extract_payload
):
    """field_value is typed as str — empty string is valid per the tool (not blank-checked)."""
    mock_table_client.find_records.return_value = {
        "findRecords": {
            "edges": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }
    }

    async with table_session as session:
        result = await session.call_tool(
            "find_records",
            {"table_id": "t1", "field_id": "f", "field_value": ""},
        )

    # Empty string is accepted — the tool only checks isinstance(field_value, str)
    mock_table_client.find_records.assert_awaited_once()
    payload = extract_payload(result)
    assert payload["success"] is True


# ---------------------------------------------------------------------------
# Input validation: update_table_record
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_record_invalid_record_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "update_table_record",
            {"record_id": 0, "fields": {"title": "x"}},
        )

    mock_table_client.update_table_record.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "record_id" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_record_empty_fields(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "update_table_record",
            {"record_id": 1, "fields": {}},
        )

    mock_table_client.update_table_record.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# Input validation: delete_table_record
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_record_invalid_record_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "delete_table_record",
            {"record_id": 0, "confirm": True},
        )

    mock_table_client.delete_table_record.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "record_id" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_record_preview_without_confirm(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "delete_table_record",
            {"record_id": 99, "confirm": False},
        )

    mock_table_client.delete_table_record.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload.get("requires_confirmation") is True


# ---------------------------------------------------------------------------
# Input validation: set_table_record_field_value
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_set_table_record_field_value_invalid_record_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "set_table_record_field_value",
            {"record_id": 0, "field_id": "f", "value": "x"},
        )

    mock_table_client.set_table_record_field_value.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "record_id" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_set_table_record_field_value_invalid_field_id_zero(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "set_table_record_field_value",
            {"record_id": "1", "field_id": 0, "value": "x"},
        )

    mock_table_client.set_table_record_field_value.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "field_id" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_set_table_record_field_value_blank_field_id(
    table_session, mock_table_client
):
    async with table_session as session:
        result = await session.call_tool(
            "set_table_record_field_value",
            {"record_id": "1", "field_id": "", "value": "x"},
        )

    mock_table_client.set_table_record_field_value.assert_not_called()
    assert_invalid_arguments_envelope(result)


# ---------------------------------------------------------------------------
# Input validation: create_table_field
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_field_invalid_table_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "create_table_field",
            {"table_id": 0, "label": "Name", "field_type": "short_text"},
        )

    mock_table_client.create_table_field.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "table_id" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_field_empty_label(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "create_table_field",
            {"table_id": "1", "label": "", "field_type": "short_text"},
        )

    mock_table_client.create_table_field.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "label" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_field_empty_field_type(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "create_table_field",
            {"table_id": "1", "label": "x", "field_type": ""},
        )

    mock_table_client.create_table_field.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "field_type" in tool_error_message(payload)


# ---------------------------------------------------------------------------
# Input validation: update_table_field
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_field_invalid_field_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "update_table_field",
            {"field_id": 0, "table_id": 1, "label": "L"},
        )

    mock_table_client.update_table_field.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "field_id" in tool_error_message(payload)


# ---------------------------------------------------------------------------
# Input validation: delete_table_field
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_field_invalid_field_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "delete_table_field",
            {"field_id": 0, "table_id": "tbl_1", "confirm": True},
        )

    mock_table_client.delete_table_field.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "field_id" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_field_preview_without_confirm(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "delete_table_field",
            {"field_id": "slug-1", "table_id": "tbl_1", "confirm": False},
        )

    mock_table_client.delete_table_field.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload.get("requires_confirmation") is True


# ---------------------------------------------------------------------------
# Input validation: create_table_record — empty fields
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_record_empty_dict_fields(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "create_table_record",
            {"table_id": 10, "fields": {}},
        )

    mock_table_client.create_table_record.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "fields" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_record_empty_list_fields(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "create_table_record",
            {"table_id": 10, "fields": []},
        )

    mock_table_client.create_table_record.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "fields" in tool_error_message(payload)


# ---------------------------------------------------------------------------
# Input validation: create_table — blank name, invalid org_id
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_blank_name(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "create_table",
            {"name": "", "organization_id": 1},
        )

    mock_table_client.create_table.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "name" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_invalid_organization_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "create_table",
            {"name": "T", "organization_id": 0},
        )

    mock_table_client.create_table.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "organization_id" in tool_error_message(payload)


# ---------------------------------------------------------------------------
# Input validation: update_table — invalid table_id, no changes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_invalid_table_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "update_table",
            {"table_id": 0, "name": "N"},
        )

    mock_table_client.update_table.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "table_id" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_no_changes(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "update_table",
            {"table_id": 1},
        )

    mock_table_client.update_table.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "at least one" in tool_error_message(payload)


# ---------------------------------------------------------------------------
# Input validation: delete_table — invalid table_id
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_invalid_table_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "delete_table",
            {"table_id": 0, "confirm": True},
        )

    mock_table_client.get_table.assert_not_called()
    mock_table_client.delete_table.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "table_id" in tool_error_message(payload)


# ---------------------------------------------------------------------------
# Input validation: create_table_record — invalid table_id
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_create_table_record_invalid_table_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "create_table_record",
            {"table_id": 0, "fields": {"f": "v"}},
        )

    mock_table_client.create_table_record.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "table_id" in tool_error_message(payload)


# ---------------------------------------------------------------------------
# Input validation: set_table_record_field_value — null value
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_set_table_record_field_value_null_value(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "set_table_record_field_value",
            {"record_id": "1", "field_id": "f", "value": None},
        )

    mock_table_client.set_table_record_field_value.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "value" in tool_error_message(payload)


# ---------------------------------------------------------------------------
# delete_table — GraphQL error during get_table lookup
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_graphql_error_on_lookup(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.get_table.side_effect = TransportQueryError(
        "failed", errors=[{"message": "table gone"}]
    )

    async with table_session as session:
        result = await session.call_tool(
            "delete_table",
            {"table_id": 99, "confirm": True},
        )

    mock_table_client.delete_table.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# delete_table — confirm True but delete returns success=False
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_delete_table_confirm_returns_false(
    table_session, mock_table_client, extract_payload
):
    mock_table_client.get_table.return_value = {"table": {"id": "5", "name": "T"}}
    mock_table_client.delete_table.return_value = {"deleteTable": {"success": False}}

    async with table_session as session:
        result = await session.call_tool(
            "delete_table",
            {"table_id": 5, "confirm": True},
        )

    payload = extract_payload(result)
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# get_tables — invalid ID inside list
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_tables_invalid_id_in_list(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool("get_tables", {"table_ids": [1, 0]})

    mock_table_client.get_tables.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "each" in tool_error_message(
        payload
    ).lower() or "Each" in tool_error_message(payload)


# ---------------------------------------------------------------------------
# update_table_field — no updates and no table_id
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_update_table_field_no_updates_no_table_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "update_table_field",
            {"field_id": "slug-1"},
        )

    mock_table_client.update_table_field.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "at least one" in tool_error_message(
        payload
    ).lower() or "table_id" in tool_error_message(payload)


@pytest.mark.anyio
class TestPipefyIdCoercion:
    """PipefyId coerces int IDs to str at the tool boundary."""

    @pytest.mark.parametrize("table_session", [None], indirect=True)
    async def test_get_table_coerces_int_table_id(
        self, table_session, mock_table_client, extract_payload
    ):
        mock_table_client.get_table = AsyncMock(
            return_value={"table": {"id": "42", "name": "Test Table"}}
        )
        async with table_session as session:
            result = await session.call_tool("get_table", {"table_id": 42})
        assert result.isError is False
        mock_table_client.get_table.assert_awaited_once_with("42")
