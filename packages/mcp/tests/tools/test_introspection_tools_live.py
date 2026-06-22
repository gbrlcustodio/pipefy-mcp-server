"""Live MCP calls for introspection tools (real PipefyClient + GraphQL).

Exercises the same path Pipeclaw uses: FastMCP tool handlers → PipefyClient →
SchemaIntrospectionService. Skips when PIPEFY_* credentials are missing.

Run:
    uv run pytest tests/tools/test_introspection_tools_live.py -m integration -v
"""

from datetime import timedelta

import pytest
from _shared.live_settings import (
    live_pipefy_settings,
    live_resolved_auth,
    require_live_creds,
)
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import PipefyClient

from pipefy_mcp.tools.introspection_tools import IntrospectionTools
from tools.conftest import build_tool_test_server


@pytest.fixture
def live_pipefy_client():
    require_live_creds()
    return PipefyClient(settings=live_pipefy_settings(), auth=live_resolved_auth())


@pytest.fixture
def live_introspection_mcp(live_pipefy_client):
    return build_tool_test_server(
        "Introspection tools live",
        IntrospectionTools.register,
        live_pipefy_client,
    )


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
