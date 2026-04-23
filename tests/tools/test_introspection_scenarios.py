"""End-to-end style scenarios for introspection tools (mocked client, real helpers)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.introspection_tools import IntrospectionTools
from pipefy_mcp.tools.tool_error_envelope import tool_error_message


@pytest.fixture
def scenario_client():
    client = MagicMock(PipefyClient)
    client.introspect_type = AsyncMock()
    client.introspect_mutation = AsyncMock()
    client.search_schema = AsyncMock()
    client.execute_graphql = AsyncMock()
    return client


@pytest.fixture
def scenario_mcp(scenario_client):
    mcp = FastMCP("Introspection scenarios")
    IntrospectionTools.register(mcp, scenario_client)
    return mcp


@pytest.fixture
def scenario_session(scenario_mcp, request):
    return create_client_session(
        scenario_mcp,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=getattr(request, "param", None),
    )


@pytest.mark.anyio
@pytest.mark.parametrize("scenario_session", [None], indirect=True)
async def test_scenario_discover_input_shape_then_execute_mutation_path(
    scenario_session, scenario_client, extract_payload
):
    """Agent flow: introspect mutation -> introspect input type -> execute_graphql (mocked)."""
    scenario_client.introspect_mutation = AsyncMock(
        return_value={
            "name": "createLabel",
            "description": "Creates a label",
            "args": [
                {
                    "name": "input",
                    "type": {
                        "kind": "NON_NULL",
                        "name": None,
                        "ofType": {"name": "CreateLabelInput", "kind": "INPUT_OBJECT"},
                    },
                    "defaultValue": None,
                }
            ],
            "type": {"name": "CreateLabelPayload", "kind": "OBJECT"},
        }
    )
    scenario_client.introspect_type = AsyncMock(
        return_value={
            "name": "CreateLabelInput",
            "kind": "INPUT_OBJECT",
            "inputFields": [
                {
                    "name": "pipe_id",
                    "description": None,
                    "type": {
                        "name": None,
                        "kind": "NON_NULL",
                        "ofType": {"name": "ID", "kind": "SCALAR"},
                    },
                },
                {
                    "name": "name",
                    "description": None,
                    "type": {
                        "name": None,
                        "kind": "NON_NULL",
                        "ofType": {"name": "String", "kind": "SCALAR"},
                    },
                },
            ],
        }
    )
    scenario_client.execute_graphql = AsyncMock(
        return_value={"createLabel": {"label": {"id": "lbl_1"}}}
    )

    async with scenario_session as session:
        m1 = await session.call_tool(
            "introspect_mutation", {"mutation_name": "createLabel"}
        )
        t1 = await session.call_tool(
            "introspect_type", {"type_name": "CreateLabelInput"}
        )
        ex = await session.call_tool(
            "execute_graphql",
            {
                "query": "mutation M($input: CreateLabelInput!) { createLabel(input: $input) { label { id } } }",
                "variables": {"input": {"pipe_id": "1", "name": "From agent"}},
            },
        )

    assert m1.isError is False
    assert t1.isError is False
    assert ex.isError is False

    p1 = extract_payload(m1)
    p2 = extract_payload(t1)
    p3 = extract_payload(ex)
    assert p1["success"] and "createLabel" in p1["result"]
    assert p2["success"] and "CreateLabelInput" in p2["result"]
    assert p3["success"] and "lbl_1" in p3["result"]

    scenario_client.execute_graphql.assert_awaited_once()
    call_query, call_vars = scenario_client.execute_graphql.call_args[0]
    assert "createLabel" in call_query
    assert call_vars["input"]["name"] == "From agent"


@pytest.mark.anyio
@pytest.mark.parametrize("scenario_session", [None], indirect=True)
async def test_scenario_search_then_introspect_type(
    scenario_session, scenario_client, extract_payload
):
    scenario_client.search_schema = AsyncMock(
        return_value={
            "types": [
                {"name": "Card", "kind": "OBJECT", "description": "A card"},
            ]
        }
    )
    scenario_client.introspect_type = AsyncMock(
        return_value={"name": "Card", "kind": "OBJECT", "fields": [{"name": "id"}]}
    )

    async with scenario_session as session:
        s = await session.call_tool("search_schema", {"keyword": "Card"})
        t = await session.call_tool("introspect_type", {"type_name": "Card"})

    assert extract_payload(s)["success"]
    assert extract_payload(t)["success"]
    scenario_client.search_schema.assert_awaited_once_with("Card", kind=None)
    scenario_client.introspect_type.assert_awaited_once_with("Card", max_depth=1)


@pytest.mark.anyio
@pytest.mark.parametrize("scenario_session", [None], indirect=True)
async def test_scenario_execute_graphql_error_surfaces_to_agent(
    scenario_session, scenario_client, extract_payload
):
    scenario_client.execute_graphql = AsyncMock(
        return_value={"errors": [{"message": "Permission denied for this field"}]}
    )
    async with scenario_session as session:
        r = await session.call_tool(
            "execute_graphql",
            {"query": "query X { __typename }", "variables": {}},
        )
    payload = extract_payload(r)
    assert payload["success"] is False
    assert "permission" in tool_error_message(payload).lower()
