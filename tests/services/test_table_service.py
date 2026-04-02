"""Unit tests for TableService.search_tables."""

from unittest.mock import AsyncMock

import pytest

from pipefy_mcp.services.pipefy.table_service import TableService
from pipefy_mcp.settings import PipefySettings


@pytest.fixture
def mock_settings() -> PipefySettings:
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings: PipefySettings, return_value: dict) -> TableService:
    service = TableService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


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
async def test_without_name_returns_all_tables(mock_settings, mock_organizations):
    """search_tables with no name returns every table across all organizations."""
    service = _make_service(mock_settings, {"organizations": mock_organizations})
    result = await service.search_tables()

    assert len(result["organizations"]) == 2
    assert result["organizations"][0]["id"] == "org1"
    assert len(result["organizations"][0]["tables"]) == 2
    assert result["organizations"][1]["id"] == "org2"
    assert len(result["organizations"][1]["tables"]) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fuzzy_match_filters_tables(mock_settings, mock_organizations):
    """search_tables with a name returns only tables that meet the threshold."""
    service = _make_service(mock_settings, {"organizations": mock_organizations})
    result = await service.search_tables(table_name="Clients")

    # "Clients" must match "Clients" (exact) and likely "Clientes VIP" (partial)
    org_ids = [o["id"] for o in result["organizations"]]
    assert "org1" in org_ids

    org1 = next(o for o in result["organizations"] if o["id"] == "org1")
    assert any(t["name"] == "Clients" for t in org1["tables"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_match_returns_empty_organizations(mock_settings, mock_organizations):
    """search_tables returns empty list when nothing matches the query."""
    service = _make_service(mock_settings, {"organizations": mock_organizations})
    result = await service.search_tables(table_name="XyzNonExistent999")

    assert result == {"organizations": []}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_matched_tables_include_match_score(mock_settings, mock_organizations):
    """Matched tables include a match_score field."""
    service = _make_service(mock_settings, {"organizations": mock_organizations})
    result = await service.search_tables(table_name="Products")

    assert len(result["organizations"]) >= 1
    for org in result["organizations"]:
        for table in org["tables"]:
            assert "match_score" in table


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tables_sorted_by_score_descending(mock_settings):
    """Tables within an organization are sorted by match_score descending."""
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
async def test_empty_organizations(mock_settings):
    """search_tables handles an empty organizations list gracefully."""
    service = _make_service(mock_settings, {"organizations": []})

    result = await service.search_tables()
    assert result == {"organizations": []}

    result = await service.search_tables(table_name="anything")
    assert result == {"organizations": []}
