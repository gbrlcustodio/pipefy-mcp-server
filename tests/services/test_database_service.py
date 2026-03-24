"""Unit tests for DatabaseService.

Tests validate database (table) read operations without requiring real API credentials.
"""

from unittest.mock import AsyncMock

import pytest

from pipefy_mcp.services.pipefy.database_service import DatabaseService
from pipefy_mcp.settings import PipefySettings


@pytest.fixture
def mock_settings() -> PipefySettings:
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings: PipefySettings, return_value: dict) -> DatabaseService:
    service = DatabaseService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


# ============================================================================
# get_table
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_passes_id_variable(mock_settings):
    """Test get_table sends table id in GraphQL variables."""
    table_id = "EX5gLJtH"
    mock_response = {
        "table": {
            "id": table_id,
            "name": "Clients",
            "description": "Client database",
            "table_fields": [],
        }
    }

    service = _make_service(mock_settings, mock_response)
    result = await service.get_table(table_id)

    service.execute_query.assert_called_once()
    variables = service.execute_query.call_args[0][1]
    assert variables == {"id": table_id}
    assert result == mock_response


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_returns_raw_response(mock_settings):
    """Test get_table returns the raw GraphQL response."""
    table_id = "ABC123"
    mock_response = {
        "table": {
            "id": table_id,
            "name": "Products",
            "description": None,
            "table_fields": [
                {"id": "name", "label": "Name", "type": "short_text", "required": True, "options": None},
                {"id": "price", "label": "Price", "type": "number", "required": False, "options": None},
            ],
        }
    }

    service = _make_service(mock_settings, mock_response)
    result = await service.get_table(table_id)

    assert result == mock_response


# ============================================================================
# get_table_records
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_records_without_cursor(mock_settings):
    """Test get_table_records sends correct variables without an after cursor."""
    table_id = "EX5gLJtH"
    mock_raw = {
        "table_records": {
            "totalCount": 2,
            "nodes": [
                {"id": "1", "title": "Record A", "created_at": "2024-01-01", "updated_at": "2024-01-02", "status": None, "record_fields": []},
                {"id": "2", "title": "Record B", "created_at": "2024-01-03", "updated_at": "2024-01-04", "status": None, "record_fields": []},
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }
    }

    service = _make_service(mock_settings, mock_raw)
    result = await service.get_table_records(table_id)

    service.execute_query.assert_called_once()
    variables = service.execute_query.call_args[0][1]
    assert variables == {"table_id": table_id, "first": 50}
    assert result["total_count"] == 2
    assert len(result["records"]) == 2
    assert result["has_next_page"] is False
    assert result["end_cursor"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_records_with_cursor(mock_settings):
    """Test get_table_records includes after cursor when provided."""
    table_id = "EX5gLJtH"
    cursor = "eyJpZCI6MTAwfQ=="
    mock_raw = {
        "table_records": {
            "totalCount": 100,
            "nodes": [{"id": "51", "title": "Record 51", "created_at": "2024-01-01", "updated_at": "2024-01-01", "status": None, "record_fields": []}],
            "pageInfo": {"hasNextPage": True, "endCursor": "eyJpZCI6MTUwfQ=="},
        }
    }

    service = _make_service(mock_settings, mock_raw)
    result = await service.get_table_records(table_id, first=1, after=cursor)

    variables = service.execute_query.call_args[0][1]
    assert variables == {"table_id": table_id, "first": 1, "after": cursor}
    assert result["has_next_page"] is True
    assert result["end_cursor"] == "eyJpZCI6MTUwfQ=="


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_records_custom_first(mock_settings):
    """Test get_table_records respects custom first parameter."""
    table_id = "T1"
    service = _make_service(mock_settings, {"table_records": {"totalCount": 0, "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}})
    await service.get_table_records(table_id, first=10)

    variables = service.execute_query.call_args[0][1]
    assert variables["first"] == 10


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_records_empty(mock_settings):
    """Test get_table_records handles empty result set."""
    service = _make_service(mock_settings, {"table_records": {"totalCount": 0, "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}})
    result = await service.get_table_records("T1")

    assert result == {"records": [], "total_count": 0, "has_next_page": False, "end_cursor": None}


# ============================================================================
# get_table_record
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_record_passes_id_variable(mock_settings):
    """Test get_table_record sends record id in GraphQL variables."""
    record_id = "TR_abc123"
    mock_raw = {
        "table_record": {
            "id": record_id,
            "title": "Some record",
            "created_at": "2024-01-01",
            "updated_at": "2024-01-02",
            "status": {"id": "1", "name": "Active"},
            "record_fields": [{"name": "Name", "value": "Foo", "array_value": None}],
        }
    }

    service = _make_service(mock_settings, mock_raw)
    result = await service.get_table_record(record_id)

    service.execute_query.assert_called_once()
    variables = service.execute_query.call_args[0][1]
    assert variables == {"id": record_id}
    assert result["id"] == record_id
    assert result["title"] == "Some record"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_record_extracts_table_record_key(mock_settings):
    """Test get_table_record unwraps the table_record key from the response."""
    inner = {"id": "TR_1", "title": "R1", "created_at": "x", "updated_at": "x", "status": None, "record_fields": []}
    service = _make_service(mock_settings, {"table_record": inner})
    result = await service.get_table_record("TR_1")

    assert result == inner


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_record_returns_empty_dict_when_missing(mock_settings):
    """Test get_table_record returns empty dict when API response lacks the key."""
    service = _make_service(mock_settings, {})
    result = await service.get_table_record("missing")

    assert result == {}


# ============================================================================
# search_tables
# ============================================================================


@pytest.fixture
def mock_organizations() -> list[dict]:
    return [
        {
            "id": "org1",
            "name": "Acme Corp",
            "tables": {
                "nodes": [
                    {"id": "T1", "name": "Clients", "description": "Client list"},
                    {"id": "T2", "name": "Products", "description": "Product catalog"},
                ]
            },
        },
        {
            "id": "org2",
            "name": "Globo",
            "tables": {
                "nodes": [
                    {"id": "T3", "name": "Fornecedores", "description": "Supplier database"},
                    {"id": "T4", "name": "Clientes VIP", "description": None},
                ]
            },
        },
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_tables_without_name_returns_all(mock_settings, mock_organizations):
    """Test search_tables returns all tables when no name filter is provided."""
    service = _make_service(mock_settings, {"organizations": mock_organizations})
    result = await service.search_tables()

    assert len(result["organizations"]) == 2
    assert result["organizations"][0]["id"] == "org1"
    assert len(result["organizations"][0]["tables"]) == 2
    assert result["organizations"][1]["id"] == "org2"
    assert len(result["organizations"][1]["tables"]) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_tables_fuzzy_match_returns_matching_tables(mock_settings, mock_organizations):
    """Test search_tables with name returns only tables above match threshold."""
    service = _make_service(mock_settings, {"organizations": mock_organizations})
    result = await service.search_tables(table_name="Clients")

    # "Clients" should match "Clients" (exact) and "Clientes VIP" (partial)
    org_ids = [o["id"] for o in result["organizations"]]
    assert "org1" in org_ids

    org1 = next(o for o in result["organizations"] if o["id"] == "org1")
    table_names = [t["name"] for t in org1["tables"]]
    assert "Clients" in table_names


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_tables_no_match_returns_empty(mock_settings, mock_organizations):
    """Test search_tables returns empty organizations when nothing matches."""
    service = _make_service(mock_settings, {"organizations": mock_organizations})
    result = await service.search_tables(table_name="XyzNonExistent999")

    assert result == {"organizations": []}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_tables_results_have_match_score(mock_settings, mock_organizations):
    """Test search_tables includes match_score on each matched table."""
    service = _make_service(mock_settings, {"organizations": mock_organizations})
    result = await service.search_tables(table_name="Products")

    assert len(result["organizations"]) >= 1
    for org in result["organizations"]:
        for table in org["tables"]:
            assert "match_score" in table


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_tables_sorted_by_score_descending(mock_settings):
    """Test search_tables returns tables sorted by match_score descending."""
    orgs = [
        {
            "id": "org1",
            "name": "Org",
            "tables": {
                "nodes": [
                    {"id": "T1", "name": "Client Records", "description": None},
                    {"id": "T2", "name": "Clients", "description": None},
                    {"id": "T3", "name": "Client Database", "description": None},
                ]
            },
        }
    ]

    service = _make_service(mock_settings, {"organizations": orgs})
    result = await service.search_tables(table_name="Clients")

    tables = result["organizations"][0]["tables"]
    scores = [t["match_score"] for t in tables]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_tables_empty_organizations(mock_settings):
    """Test search_tables handles empty organizations list."""
    service = _make_service(mock_settings, {"organizations": []})

    result = await service.search_tables()
    assert result == {"organizations": []}

    result = await service.search_tables(table_name="anything")
    assert result == {"organizations": []}
