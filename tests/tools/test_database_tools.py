"""Unit tests for DatabaseTools.

Tests validate the MCP tool layer for database (table) read operations using
a real FastMCP server backed by a mocked PipefyClient.
"""

import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.database_tools import DatabaseTools


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_pipefy_client():
    client = MagicMock(PipefyClient)
    client.search_tables = AsyncMock()
    client.get_table = AsyncMock()
    client.get_table_records = AsyncMock()
    client.get_table_record = AsyncMock()
    return client


@pytest.fixture
def mcp_server(mock_pipefy_client):
    mcp = FastMCP("Pipefy MCP Test Server")
    DatabaseTools.register(mcp, mock_pipefy_client)
    return mcp


@pytest.fixture
def client_session(mcp_server):
    return create_client_session(
        mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )


def _extract_payload(result) -> dict:
    """Extract tool payload from CallToolResult across MCP SDK versions."""
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        if isinstance(structured, dict) and "result" in structured:
            payload = structured.get("result")
            if isinstance(payload, dict):
                return payload
        if isinstance(structured, dict):
            return structured

    content = getattr(result, "content", None) or []
    for item in content:
        if getattr(item, "type", None) == "text":
            text = getattr(item, "text", "")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload

    raise AssertionError("Could not extract tool payload from CallToolResult")


# =============================================================================
# search_tables
# =============================================================================


@pytest.mark.anyio
class TestSearchTablesTool:
    async def test_without_name_calls_client_with_none(
        self, client_session, mock_pipefy_client
    ):
        expected = {"organizations": [{"id": "org1", "name": "Acme", "tables": []}]}
        mock_pipefy_client.search_tables.return_value = expected

        async with client_session as session:
            result = await session.call_tool("search_tables", {})

        assert result.isError is False
        mock_pipefy_client.search_tables.assert_awaited_once_with(None)

    async def test_with_name_passes_it_to_client(
        self, client_session, mock_pipefy_client
    ):
        expected = {"organizations": []}
        mock_pipefy_client.search_tables.return_value = expected

        async with client_session as session:
            result = await session.call_tool("search_tables", {"table_name": "Clients"})

        assert result.isError is False
        mock_pipefy_client.search_tables.assert_awaited_once_with("Clients")

    async def test_returns_client_response(self, client_session, mock_pipefy_client):
        expected = {
            "organizations": [
                {
                    "id": "org1",
                    "name": "Acme",
                    "tables": [{"id": "T1", "name": "Clients", "match_score": 100.0}],
                }
            ]
        }
        mock_pipefy_client.search_tables.return_value = expected

        async with client_session as session:
            result = await session.call_tool("search_tables", {"table_name": "Clients"})

        payload = _extract_payload(result)
        assert payload == expected


# =============================================================================
# get_table
# =============================================================================


@pytest.mark.anyio
class TestGetTableTool:
    async def test_passes_table_id_to_client(self, client_session, mock_pipefy_client):
        table_id = "EX5gLJtH"
        mock_pipefy_client.get_table.return_value = {
            "table": {"id": table_id, "name": "Clients", "description": None, "table_fields": []}
        }

        async with client_session as session:
            result = await session.call_tool("get_table", {"table_id": table_id})

        assert result.isError is False
        mock_pipefy_client.get_table.assert_awaited_once_with(table_id)

    async def test_returns_client_response(self, client_session, mock_pipefy_client):
        expected = {
            "table": {
                "id": "T1",
                "name": "Products",
                "description": "Product catalog",
                "table_fields": [
                    {"id": "name", "label": "Name", "type": "short_text", "required": True, "options": None}
                ],
            }
        }
        mock_pipefy_client.get_table.return_value = expected

        async with client_session as session:
            result = await session.call_tool("get_table", {"table_id": "T1"})

        payload = _extract_payload(result)
        assert payload == expected


# =============================================================================
# get_table_records
# =============================================================================


@pytest.mark.anyio
class TestGetTableRecordsTool:
    async def test_passes_required_args_to_client(
        self, client_session, mock_pipefy_client
    ):
        mock_pipefy_client.get_table_records.return_value = {
            "records": [], "total_count": 0, "has_next_page": False, "end_cursor": None
        }

        async with client_session as session:
            result = await session.call_tool("get_table_records", {"table_id": "T1"})

        assert result.isError is False
        mock_pipefy_client.get_table_records.assert_awaited_once_with("T1", 50, None)

    async def test_passes_pagination_args_to_client(
        self, client_session, mock_pipefy_client
    ):
        cursor = "cursor_abc"
        mock_pipefy_client.get_table_records.return_value = {
            "records": [], "total_count": 0, "has_next_page": False, "end_cursor": None
        }

        async with client_session as session:
            result = await session.call_tool(
                "get_table_records",
                {"table_id": "T1", "first": 10, "after": cursor},
            )

        assert result.isError is False
        mock_pipefy_client.get_table_records.assert_awaited_once_with("T1", 10, cursor)

    async def test_returns_client_response(self, client_session, mock_pipefy_client):
        expected = {
            "records": [
                {"id": "R1", "title": "Record 1", "record_fields": [{"name": "Name", "value": "Foo", "array_value": None}]}
            ],
            "total_count": 1,
            "has_next_page": False,
            "end_cursor": None,
        }
        mock_pipefy_client.get_table_records.return_value = expected

        async with client_session as session:
            result = await session.call_tool("get_table_records", {"table_id": "T1"})

        payload = _extract_payload(result)
        assert payload == expected


# =============================================================================
# get_table_record
# =============================================================================


@pytest.mark.anyio
class TestGetTableRecordTool:
    async def test_passes_record_id_to_client(self, client_session, mock_pipefy_client):
        record_id = "TR_abc123"
        mock_pipefy_client.get_table_record.return_value = {
            "id": record_id, "title": "Some record", "record_fields": []
        }

        async with client_session as session:
            result = await session.call_tool("get_table_record", {"record_id": record_id})

        assert result.isError is False
        mock_pipefy_client.get_table_record.assert_awaited_once_with(record_id)

    async def test_returns_client_response(self, client_session, mock_pipefy_client):
        expected = {
            "id": "TR_1",
            "title": "Record Title",
            "created_at": "2024-01-01",
            "updated_at": "2024-01-02",
            "status": {"id": "1", "name": "Active"},
            "record_fields": [{"name": "Color", "value": "Blue", "array_value": None}],
        }
        mock_pipefy_client.get_table_record.return_value = expected

        async with client_session as session:
            result = await session.call_tool("get_table_record", {"record_id": "TR_1"})

        payload = _extract_payload(result)
        assert payload == expected
