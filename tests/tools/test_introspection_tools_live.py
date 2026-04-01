"""Live MCP calls for introspection tools (real PipefyClient + GraphQL).

Exercises the same path Pipeclaw uses: FastMCP tool handlers → PipefyClient →
SchemaIntrospectionService. Skips when PIPEFY_* credentials are missing.

Run:
    uv run pytest tests/tools/test_introspection_tools_live.py -m integration -v
"""

from datetime import timedelta

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.introspection_tools import IntrospectionTools


def _pipefy_live_configured() -> bool:
    p = settings.pipefy
    return bool(
        p.graphql_url
        and str(p.graphql_url).startswith(("http://", "https://"))
        and p.oauth_url
        and str(p.oauth_url).startswith(("http://", "https://"))
        and p.oauth_client
        and p.oauth_secret
    )


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def live_pipefy_client():
    if not _pipefy_live_configured():
        pytest.skip(
            "Pipefy credentials not configured (PIPEFY_GRAPHQL_URL + OAuth in .env)"
        )
    return PipefyClient(settings=settings.pipefy)


@pytest.fixture
def live_introspection_mcp(live_pipefy_client):
    mcp = FastMCP("Introspection tools live")
    IntrospectionTools.register(mcp, live_pipefy_client)
    return mcp


@pytest.fixture
def live_introspection_session(live_introspection_mcp, request):
    return create_client_session(
        live_introspection_mcp,
        read_timeout_seconds=timedelta(seconds=60),
        raise_exceptions=True,
        elicitation_callback=getattr(request, "param", None),
    )


@pytest.mark.integration
@pytest.mark.anyio
@pytest.mark.parametrize("live_introspection_session", [None], indirect=True)
async def test_live_mcp_introspect_type_query(
    live_introspection_session, extract_payload
):
    async with live_introspection_session as session:
        result = await session.call_tool("introspect_type", {"type_name": "Query"})
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "Query" in payload["result"]
    assert "OBJECT" in payload["result"]


@pytest.mark.integration
@pytest.mark.anyio
@pytest.mark.parametrize("live_introspection_session", [None], indirect=True)
async def test_live_mcp_introspect_mutation_create_card(
    live_introspection_session, extract_payload
):
    async with live_introspection_session as session:
        result = await session.call_tool(
            "introspect_mutation",
            {"mutation_name": "createCard"},
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "createCard" in payload["result"]
    assert "input" in payload["result"].lower()


@pytest.mark.integration
@pytest.mark.anyio
@pytest.mark.parametrize("live_introspection_session", [None], indirect=True)
async def test_live_mcp_search_schema_card(live_introspection_session, extract_payload):
    async with live_introspection_session as session:
        result = await session.call_tool("search_schema", {"keyword": "Card"})
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "Card" in payload["result"]


@pytest.mark.integration
@pytest.mark.anyio
@pytest.mark.parametrize("live_introspection_session", [None], indirect=True)
async def test_live_mcp_execute_graphql_typename(
    live_introspection_session, extract_payload
):
    async with live_introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "query T { __typename }", "variables": None},
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "Query" in payload["result"]
