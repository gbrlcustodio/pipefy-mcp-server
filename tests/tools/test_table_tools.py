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
    assert "not found" in payload["error"]


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
    table_session, mock_table_client, extract_payload
):
    mock_table_client.get_table_records.return_value = {
        "table_records": {
            "edges": [],
            "pageInfo": {"hasNextPage": True, "endCursor": "n1"},
        }
    }

    async with table_session as session:
        result = await session.call_tool(
            "get_table_records",
            {"table_id": "t1", "first": 50},
        )

    mock_table_client.get_table_records.assert_awaited_once_with(
        "t1", first=50, after=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["pagination"]["hasNextPage"] is True
    assert payload["pagination"]["endCursor"] == "n1"


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
    assert "extra_input" in payload["error"]
    assert "dict" in payload["error"].lower()


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
        assert "extra_input" in payload["error"]


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
    assert "extra_input" in payload["error"]


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
    assert "extra_input" in payload["error"]


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
    assert "extra_input" in payload["error"]


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
    assert "title" in payload["error"]
    assert "due_date" in payload["error"]


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
    assert "index 0" in payload["error"]
    assert "field_value" in payload["error"]


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
    assert "index 0" in payload["error"]


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
    mock_table_client.search_tables.assert_awaited_once_with(None)


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_search_tables_with_name_passes_it_to_client(
    table_session, mock_table_client
):
    mock_table_client.search_tables.return_value = {"organizations": []}

    async with table_session as session:
        result = await session.call_tool("search_tables", {"table_name": "Clients"})

    assert result.isError is False
    mock_table_client.search_tables.assert_awaited_once_with("Clients")


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_search_tables_returns_client_response(
    table_session, mock_table_client, extract_payload
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


# ---------------------------------------------------------------------------
# Input validation: get_table
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
@pytest.mark.parametrize("bad_id", [0, ""])
async def test_get_table_invalid_table_id(
    table_session, mock_table_client, extract_payload, bad_id
):
    async with table_session as session:
        result = await session.call_tool("get_table", {"table_id": bad_id})

    mock_table_client.get_table.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "table_id" in payload["error"]


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
    assert "table_ids" in payload["error"]


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
    assert "table_id" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_records_first_too_small(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "get_table_records", {"table_id": "t1", "first": 0}
        )

    mock_table_client.get_table_records.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "first" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_get_table_records_first_too_large(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "get_table_records", {"table_id": "t1", "first": 201}
        )

    mock_table_client.get_table_records.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "first" in payload["error"]


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
    assert "record_id" in payload["error"]


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
    assert "table_id" in payload["error"]


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
    assert "field_id" in payload["error"]


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
    assert "record_id" in payload["error"]


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
    assert "record_id" in payload["error"]


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
    assert "record_id" in payload["error"]


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
    assert "field_id" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("table_session", [None], indirect=True)
async def test_set_table_record_field_value_blank_field_id(
    table_session, mock_table_client, extract_payload
):
    async with table_session as session:
        result = await session.call_tool(
            "set_table_record_field_value",
            {"record_id": "1", "field_id": "", "value": "x"},
        )

    mock_table_client.set_table_record_field_value.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "field_id" in payload["error"]


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
    assert "table_id" in payload["error"]


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
    assert "label" in payload["error"]


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
    assert "field_type" in payload["error"]


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
    assert "field_id" in payload["error"]


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
    assert "field_id" in payload["error"]


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
    assert "fields" in payload["error"]


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
    assert "fields" in payload["error"]


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
    assert "name" in payload["error"]


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
    assert "organization_id" in payload["error"]


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
    assert "table_id" in payload["error"]


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
    assert "at least one" in payload["error"]


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
    assert "table_id" in payload["error"]


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
    assert "table_id" in payload["error"]


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
    assert "value" in payload["error"]


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
    assert "each" in payload["error"].lower() or "Each" in payload["error"]


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
    assert "at least one" in payload["error"].lower() or "table_id" in payload["error"]


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
