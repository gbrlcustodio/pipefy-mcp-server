"""Unit tests for TableService.search_tables."""

import pytest
from _shared.mock_clients import mock_executor
from _shared.pagination_test_defaults import DEFAULT_FIRST

from pipefy_sdk.queries.table_queries import SEARCH_TABLES_QUERY
from pipefy_sdk.services.table_service import TableService


def _table_connection(
    nodes: list[dict],
    *,
    has_next: bool = False,
    end_cursor: str | None = None,
) -> dict:
    return {
        "nodes": nodes,
        "pageInfo": {
            "hasNextPage": has_next,
            "endCursor": end_cursor,
        },
    }


def _make_service(return_value: dict):
    executor = mock_executor(return_value)
    return TableService(executor=executor), executor


@pytest.fixture
def mock_organizations() -> list[dict]:
    return [
        {
            "id": "org1",
            "name": "Acme Corp",
            "tables": _table_connection(
                [
                    {"id": "T1", "name": "Clients", "description": "Client list"},
                    {"id": "T2", "name": "Products", "description": "Product catalog"},
                ]
            ),
        },
        {
            "id": "org2",
            "name": "Globo",
            "tables": _table_connection(
                [
                    {
                        "id": "T3",
                        "name": "Fornecedores",
                        "description": "Supplier database",
                    },
                    {"id": "T4", "name": "Clientes VIP", "description": None},
                ]
            ),
        },
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_without_name_returns_all_tables(mock_organizations):
    """search_tables with no name returns every table across all organizations."""
    service, executor = _make_service({"organizations": mock_organizations})
    result = await service.search_tables()

    executor.execute_query.assert_awaited_once_with(SEARCH_TABLES_QUERY, {"first": 100})
    assert result["search_limits"]["tables_first"] == 100
    assert result["search_limits"]["tables_has_next_page"] is False
    assert len(result["organizations"]) == 2
    assert result["organizations"][0]["id"] == "org1"
    assert len(result["organizations"][0]["tables"]) == 2
    assert result["organizations"][1]["id"] == "org2"
    assert len(result["organizations"][1]["tables"]) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fuzzy_match_filters_tables(mock_organizations):
    """search_tables with a name returns only tables that meet the threshold."""
    service, _ = _make_service({"organizations": mock_organizations})
    result = await service.search_tables(table_name="Clients")

    # "Clients" must match "Clients" (exact) and likely "Clientes VIP" (partial)
    org_ids = [o["id"] for o in result["organizations"]]
    assert "org1" in org_ids

    org1 = next(o for o in result["organizations"] if o["id"] == "org1")
    assert any(t["name"] == "Clients" for t in org1["tables"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_match_returns_empty_organizations(mock_organizations):
    """search_tables returns empty list when nothing matches the query."""
    service, _ = _make_service({"organizations": mock_organizations})
    result = await service.search_tables(table_name="XyzNonExistent999")

    assert result["organizations"] == []
    assert "search_limits" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_matched_tables_include_match_score(mock_organizations):
    """Matched tables include a match_score field."""
    service, _ = _make_service({"organizations": mock_organizations})
    result = await service.search_tables(table_name="Products")

    assert len(result["organizations"]) >= 1
    for org in result["organizations"]:
        for table in org["tables"]:
            assert "match_score" in table


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tables_sorted_by_score_descending():
    """Tables within an organization are sorted by match_score descending."""
    orgs = [
        {
            "id": "org1",
            "name": "Org",
            "tables": _table_connection(
                [
                    {"id": "T1", "name": "Client Records", "description": None},
                    {"id": "T2", "name": "Clients", "description": None},
                    {"id": "T3", "name": "Client Database", "description": None},
                ]
            ),
        }
    ]
    service, _ = _make_service({"organizations": orgs})
    result = await service.search_tables(table_name="Clients")

    tables = result["organizations"][0]["tables"]
    scores = [t["match_score"] for t in tables]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_organizations():
    """search_tables handles an empty organizations list gracefully."""
    service, _ = _make_service({"organizations": []})

    result = await service.search_tables()
    assert result["organizations"] == []

    result = await service.search_tables(table_name="anything")
    assert result["organizations"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_tables_propagates_has_next_page():
    orgs = [
        {
            "id": "org1",
            "name": "Org",
            "tables": _table_connection(
                [{"id": "T1", "name": "A", "description": None}],
                has_next=True,
                end_cursor="c1",
            ),
        }
    ]
    service, executor = _make_service({"organizations": orgs})
    result = await service.search_tables(first=DEFAULT_FIRST)

    assert result["search_limits"]["tables_has_next_page"] is True
    assert result["organizations"][0]["tables_has_next_page"] is True
    assert result["organizations"][0]["tables_page_end_cursor"] == "c1"
    executor.execute_query.assert_awaited_once_with(
        SEARCH_TABLES_QUERY, {"first": DEFAULT_FIRST}
    )
