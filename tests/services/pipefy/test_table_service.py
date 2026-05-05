"""Unit tests for TableService (database table reads and mutations)."""

from unittest.mock import AsyncMock

import pytest
from gql.transport.exceptions import TransportQueryError

from pipefy_mcp.services.pipefy.queries.table_queries import (
    CREATE_TABLE_FIELD_MUTATION,
    CREATE_TABLE_MUTATION,
    CREATE_TABLE_RECORD_MUTATION,
    DELETE_TABLE_FIELD_MUTATION,
    DELETE_TABLE_MUTATION,
    DELETE_TABLE_RECORD_MUTATION,
    FIND_RECORDS_QUERY,
    GET_TABLE_QUERY,
    GET_TABLE_RECORD_QUERY,
    GET_TABLE_RECORDS_QUERY,
    GET_TABLES_QUERY,
    SET_TABLE_RECORD_FIELD_VALUE_MUTATION,
    UPDATE_TABLE_FIELD_MUTATION,
    UPDATE_TABLE_MUTATION,
    UPDATE_TABLE_RECORD_MUTATION,
)
from pipefy_mcp.services.pipefy.table_service import TableService
from pipefy_mcp.settings import PipefySettings
from tests.pagination_test_defaults import DEFAULT_FIRST


@pytest.fixture
def mock_settings():
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings, return_value: dict):
    service = TableService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_sends_id_and_returns_payload(mock_settings):
    service = _make_service(
        mock_settings,
        {"table": {"id": "t1", "name": "Refs", "table_fields": []}},
    )
    result = await service.get_table("101")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is GET_TABLE_QUERY
    assert variables == {"id": "101"}
    assert result["table"]["name"] == "Refs"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_accepts_alphanumeric_id(mock_settings):
    service = _make_service(
        mock_settings,
        {"table": {"id": "Yr5RUVCi", "name": "Alpha", "table_fields": []}},
    )
    result = await service.get_table("Yr5RUVCi")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_TABLE_QUERY
    assert variables == {"id": "Yr5RUVCi"}
    assert result["table"]["name"] == "Alpha"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_tables_sends_ids_list(mock_settings):
    service = _make_service(
        mock_settings,
        {"tables": [{"id": "a"}, {"id": "b"}]},
    )
    result = await service.get_tables(["101", "102"])

    query, variables = service.execute_query.call_args[0]
    assert query is GET_TABLES_QUERY
    assert variables == {"ids": ["101", "102"]}
    assert len(result["tables"]) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_records_default_first_and_pagination_passthrough(
    mock_settings,
):
    page = {
        "table_records": {
            "edges": [],
            "pageInfo": {"hasNextPage": True, "endCursor": "c2"},
        }
    }
    service = _make_service(mock_settings, page)
    result = await service.get_table_records(99)

    query, variables = service.execute_query.call_args[0]
    assert query is GET_TABLE_RECORDS_QUERY
    assert variables == {"tableId": "99", "first": DEFAULT_FIRST}
    assert result["table_records"]["pageInfo"]["hasNextPage"] is True
    assert result["table_records"]["pageInfo"]["endCursor"] == "c2"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_records_includes_after_when_provided(mock_settings):
    service = _make_service(mock_settings, {"table_records": {"edges": []}})
    await service.get_table_records("201", first=10, after="c1")

    variables = service.execute_query.call_args[0][1]
    assert variables == {"tableId": "201", "first": 10, "after": "c1"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_record_sends_record_id(mock_settings):
    service = _make_service(
        mock_settings,
        {"table_record": {"id": "r1", "title": "Row", "record_fields": []}},
    )
    result = await service.get_table_record(7001)

    query, variables = service.execute_query.call_args[0]
    assert query is GET_TABLE_RECORD_QUERY
    assert variables == {"id": "7001"}
    assert result["table_record"]["title"] == "Row"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_records_sends_search_variables_and_coerces_table_id(
    mock_settings,
):
    service = _make_service(
        mock_settings,
        {"findRecords": {"edges": [], "pageInfo": {"hasNextPage": False}}},
    )
    result = await service.find_records(42, "fid", "acme")

    query, variables = service.execute_query.call_args[0]
    assert query is FIND_RECORDS_QUERY
    assert variables == {
        "tableId": "42",
        "fieldId": "fid",
        "fieldValue": "acme",
    }
    assert result["findRecords"]["edges"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_records_optional_pagination_vars(mock_settings):
    service = _make_service(mock_settings, {"findRecords": {"edges": []}})
    await service.find_records("t", "f", "v", first=25, after="cur")

    variables = service.execute_query.call_args[0][1]
    assert variables == {
        "tableId": "t",
        "fieldId": "f",
        "fieldValue": "v",
        "first": 25,
        "after": "cur",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_table_sends_create_table_input(mock_settings):
    service = _make_service(
        mock_settings,
        {"createTable": {"table": {"id": "t1", "name": "N"}}},
    )
    result = await service.create_table("N", 88, description="D")

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_TABLE_MUTATION
    assert variables == {
        "input": {"name": "N", "organization_id": "88", "description": "D"},
    }
    assert result["createTable"]["table"]["id"] == "t1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_table_raises_transport_query_error(mock_settings):
    service = TableService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("x", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.create_table("A", 1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_table_merges_id_and_attrs(mock_settings):
    service = _make_service(
        mock_settings,
        {"updateTable": {"table": {"id": "1", "name": "X"}}},
    )
    await service.update_table("1", name="X", public=None)

    query, variables = service.execute_query.call_args[0]
    assert query is UPDATE_TABLE_MUTATION
    assert variables == {"input": {"id": "1", "name": "X"}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_table_raises_transport_query_error(mock_settings):
    service = TableService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("x", errors=[{"message": "bad"}])
    )
    with pytest.raises(TransportQueryError):
        await service.update_table(1, name="Z")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_table_sends_delete_input(mock_settings):
    service = _make_service(mock_settings, {"deleteTable": {"success": True}})
    result = await service.delete_table(42)

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_TABLE_MUTATION
    assert variables == {"input": {"id": "42"}}
    assert result["deleteTable"]["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_table_raises_transport_query_error(mock_settings):
    service = TableService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("x", errors=[{"message": "nope"}])
    )
    with pytest.raises(TransportQueryError):
        await service.delete_table(1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_table_record_converts_dict_fields(mock_settings):
    service = _make_service(
        mock_settings,
        {"createTableRecord": {"table_record": {"id": "r1", "title": "T"}}},
    )
    await service.create_table_record(9, {"f1": "v1"}, title="T")

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_TABLE_RECORD_MUTATION
    inp = variables["input"]
    assert inp["table_id"] == "9"
    assert inp["title"] == "T"
    assert len(inp["fields_attributes"]) == 1
    assert inp["fields_attributes"][0]["field_id"] == "f1"
    assert inp["fields_attributes"][0]["field_value"] == "v1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_table_record_raises_transport_query_error(mock_settings):
    service = TableService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("x", errors=[{"message": "err"}])
    )
    with pytest.raises(TransportQueryError):
        await service.create_table_record(1, {"a": "b"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_table_record_raises_when_no_supported_attributes(
    mock_settings,
):
    service = _make_service(mock_settings, {"updateTableRecord": {}})
    with pytest.raises(ValueError, match="Invalid 'fields'"):
        await service.update_table_record("100", {"unknown": "x"})

    service.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_table_record_maps_status_id(mock_settings):
    service = _make_service(
        mock_settings,
        {"updateTableRecord": {"table_record": {"id": "1"}}},
    )
    await service.update_table_record(
        "901",
        {"title": "Hi", "status_id": "st1"},
    )

    query, variables = service.execute_query.call_args[0]
    assert query is UPDATE_TABLE_RECORD_MUTATION
    assert variables == {
        "input": {"id": "901", "title": "Hi", "statusId": "st1"},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_table_record_raises_transport_query_error(mock_settings):
    service = TableService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("x", errors=[{"message": "x"}])
    )
    with pytest.raises(TransportQueryError):
        await service.update_table_record(1, {"title": "a"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_table_record_sends_id(mock_settings):
    service = _make_service(mock_settings, {"deleteTableRecord": {"success": True}})
    await service.delete_table_record("301")

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_TABLE_RECORD_MUTATION
    assert variables == {"input": {"id": "301"}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_table_record_raises_transport_query_error(mock_settings):
    service = TableService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("x", errors=[{"message": "x"}])
    )
    with pytest.raises(TransportQueryError):
        await service.delete_table_record(1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_table_record_field_value_wraps_scalar(mock_settings):
    service = _make_service(
        mock_settings,
        {"setTableRecordFieldValue": {"table_record": {"id": "1"}}},
    )
    await service.set_table_record_field_value("401", "f1", "text")

    query, variables = service.execute_query.call_args[0]
    assert query is SET_TABLE_RECORD_FIELD_VALUE_MUTATION
    assert variables == {
        "input": {
            "table_record_id": "401",
            "field_id": "f1",
            "value": ["text"],
        },
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_table_record_field_value_raises_transport_query_error(
    mock_settings,
):
    service = TableService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("x", errors=[{"message": "x"}])
    )
    with pytest.raises(TransportQueryError):
        await service.set_table_record_field_value(1, 2, "v")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_table_field_sends_input(mock_settings):
    service = _make_service(
        mock_settings,
        {
            "createTableField": {
                "table_field": {"id": "f1", "label": "Code", "type": "short_text"},
            },
        },
    )
    result = await service.create_table_field(
        "501",
        "Code",
        "short_text",
        required=True,
    )

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_TABLE_FIELD_MUTATION
    assert variables == {
        "input": {
            "table_id": "501",
            "label": "Code",
            "type": "short_text",
            "required": True,
        },
    }
    assert result["createTableField"]["table_field"]["id"] == "f1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_table_field_raises_transport_query_error(mock_settings):
    service = TableService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("x", errors=[{"message": "e"}])
    )
    with pytest.raises(TransportQueryError):
        await service.create_table_field(1, "L", "t")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_table_field_merges_id_and_attrs(mock_settings):
    service = _make_service(
        mock_settings,
        {"updateTableField": {"table_field": {"id": "f1"}}},
    )
    await service.update_table_field("f1", label="New", public=None)

    query, variables = service.execute_query.call_args[0]
    assert query is UPDATE_TABLE_FIELD_MUTATION
    assert variables == {"input": {"id": "f1", "label": "New"}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_table_field_raises_transport_query_error(mock_settings):
    service = TableService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("x", errors=[{"message": "e"}])
    )
    with pytest.raises(TransportQueryError):
        await service.update_table_field(1, label="x")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_table_field_sends_id(mock_settings):
    service = _make_service(mock_settings, {"deleteTableField": {"success": True}})
    result = await service.delete_table_field("fld", "tbl_123")

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_TABLE_FIELD_MUTATION
    assert variables == {"input": {"id": "fld", "table_id": "tbl_123"}}
    assert result["deleteTableField"]["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_table_field_raises_transport_query_error(mock_settings):
    service = TableService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("x", errors=[{"message": "e"}])
    )
    with pytest.raises(TransportQueryError):
        await service.delete_table_field(1, "tbl_123")
