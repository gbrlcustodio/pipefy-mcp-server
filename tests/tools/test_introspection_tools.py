"""Tests for GraphQL introspection MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.introspection_tools import IntrospectionTools


@pytest.fixture
def mock_introspection_client():
    client = MagicMock(PipefyClient)
    client.introspect_type = AsyncMock()
    client.introspect_mutation = AsyncMock()
    client.introspect_query = AsyncMock()
    client.search_schema = AsyncMock()
    client.execute_graphql = AsyncMock()
    return client


@pytest.fixture
def introspection_mcp_server(mock_introspection_client):
    mcp = FastMCP("Pipefy Introspection Tools Test")
    IntrospectionTools.register(mcp, mock_introspection_client)
    return mcp


@pytest.fixture
def introspection_session(introspection_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        introspection_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_introspect_type_success(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_type = AsyncMock(
        return_value={"name": "Card", "kind": "OBJECT", "fields": []}
    )
    async with introspection_session as session:
        result = await session.call_tool("introspect_type", {"type_name": "Card"})
    assert result.isError is False
    mock_introspection_client.introspect_type.assert_awaited_once_with(
        "Card", max_depth=1
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "Card" in payload["result"]
    assert "OBJECT" in payload["result"]


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_introspect_type_with_max_depth_passes_through(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_type = AsyncMock(
        return_value={"name": "Card", "kind": "OBJECT", "fields": []}
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "introspect_type", {"type_name": "Card", "max_depth": 2}
        )
    assert result.isError is False
    mock_introspection_client.introspect_type.assert_awaited_once_with(
        "Card", max_depth=2
    )


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_introspect_type_not_found_returns_error_payload(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_type = AsyncMock(
        return_value={"error": "GraphQL type 'Nope' was not found."}
    )
    async with introspection_session as session:
        result = await session.call_tool("introspect_type", {"type_name": "Nope"})
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in payload["error"].lower()


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_introspect_type_transport_error_returns_structured_error(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_type = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "timeout"}])
    )
    async with introspection_session as session:
        result = await session.call_tool("introspect_type", {"type_name": "Card"})
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert isinstance(payload.get("error"), str)


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_introspect_mutation_success(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_mutation = AsyncMock(
        return_value={
            "name": "createCard",
            "description": "Creates a card",
            "args": [],
            "type": {"name": "CardPayload", "kind": "OBJECT"},
        }
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "introspect_mutation", {"mutation_name": "createCard"}
        )
    assert result.isError is False
    mock_introspection_client.introspect_mutation.assert_awaited_once_with(
        "createCard", max_depth=1
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "createCard" in payload["result"]


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_introspect_mutation_with_max_depth_passes_through(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_mutation = AsyncMock(
        return_value={
            "name": "createCard",
            "description": "Creates a card",
            "args": [],
            "type": {"name": "CardPayload", "kind": "OBJECT"},
        }
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "introspect_mutation", {"mutation_name": "createCard", "max_depth": 2}
        )
    assert result.isError is False
    mock_introspection_client.introspect_mutation.assert_awaited_once_with(
        "createCard", max_depth=2
    )


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_introspect_query_with_max_depth_passes_through(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_query = AsyncMock(
        return_value={
            "name": "pipe",
            "description": "Lookup a pipe",
            "args": [],
            "type": {"name": "Pipe", "kind": "OBJECT"},
        }
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "introspect_query", {"query_name": "pipe", "max_depth": 3}
        )
    assert result.isError is False
    mock_introspection_client.introspect_query.assert_awaited_once_with(
        "pipe", max_depth=3
    )


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_introspect_mutation_not_found_returns_error_payload(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_mutation = AsyncMock(
        return_value={"error": "Mutation 'missing' was not found."}
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "introspect_mutation", {"mutation_name": "missing"}
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in payload["error"].lower()


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_introspect_query_success(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_query = AsyncMock(
        return_value={
            "name": "pipe",
            "description": "Lookup a pipe by its ID",
            "args": [
                {
                    "name": "id",
                    "type": {
                        "name": None,
                        "kind": "NON_NULL",
                        "ofType": {"name": "ID", "kind": "SCALAR"},
                    },
                    "defaultValue": None,
                }
            ],
            "type": {"name": "Pipe", "kind": "OBJECT"},
        }
    )
    async with introspection_session as session:
        result = await session.call_tool("introspect_query", {"query_name": "pipe"})
    assert result.isError is False
    mock_introspection_client.introspect_query.assert_awaited_once_with(
        "pipe", max_depth=1
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "pipe" in payload["result"]


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_introspect_query_not_found_returns_error_payload(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_query = AsyncMock(
        return_value={"error": "Query 'missing' was not found."}
    )
    async with introspection_session as session:
        result = await session.call_tool("introspect_query", {"query_name": "missing"})
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in payload["error"].lower()


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_search_schema_returns_matching_types(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.search_schema = AsyncMock(
        return_value={
            "types": [
                {
                    "name": "Pipe",
                    "kind": "OBJECT",
                    "description": "A pipe",
                }
            ]
        }
    )
    async with introspection_session as session:
        result = await session.call_tool("search_schema", {"keyword": "pipe"})
    assert result.isError is False
    mock_introspection_client.search_schema.assert_awaited_once_with("pipe", kind=None)
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "Pipe" in payload["result"]


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_search_schema_empty_returns_success_with_empty_types(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.search_schema = AsyncMock(return_value={"types": []})
    async with introspection_session as session:
        result = await session.call_tool("search_schema", {"keyword": "zzznothing"})
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "[]" in payload["result"] or '"types": []' in payload["result"]


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_search_schema_with_kind_passes_through(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.search_schema = AsyncMock(
        return_value={
            "types": [
                {"name": "CardStatus", "kind": "ENUM", "description": "Status values"}
            ]
        }
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "search_schema", {"keyword": "card", "kind": "ENUM"}
        )
    assert result.isError is False
    mock_introspection_client.search_schema.assert_awaited_once_with(
        "card", kind="ENUM"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "CardStatus" in payload["result"]


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_execute_graphql_success(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.execute_graphql = AsyncMock(
        return_value={"__typename": "Query"}
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "query Q { __typename }", "variables": None},
        )
    assert result.isError is False
    mock_introspection_client.execute_graphql.assert_awaited_once_with(
        "query Q { __typename }", None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "Query" in payload["result"]


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_execute_graphql_graphql_errors_surface_as_failure(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.execute_graphql = AsyncMock(
        return_value={
            "errors": [{"message": "Field `nope` does not exist", "extensions": {}}]
        }
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "query Q { __typename }", "variables": {}},
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert (
        "nope" in payload["error"].lower()
        or "nope" in payload.get("result", "").lower()
    )


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_execute_graphql_syntax_error_returns_error_payload(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.execute_graphql = AsyncMock(
        return_value={"error": "Syntax Error: Expected Name, found <EOF>."}
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "query { z"},
        )
    assert result.isError is False
    mock_introspection_client.execute_graphql.assert_awaited_once()
    payload = extract_payload(result)
    assert payload["success"] is False
    err = payload["error"].lower()
    assert "syntax" in err or "invalid" in err or "unexpected" in err


@pytest.mark.anyio
@pytest.mark.parametrize("introspection_session", [None], indirect=True)
async def test_execute_graphql_transport_error_returns_error_payload(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.execute_graphql = AsyncMock(
        side_effect=RuntimeError("Connection refused")
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "query Q { __typename }"},
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Connection refused" in payload["error"]
