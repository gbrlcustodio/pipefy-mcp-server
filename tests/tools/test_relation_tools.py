"""Tests for relation MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.relation_tools import RelationTools


@pytest.fixture
def mock_relation_client():
    client = MagicMock(PipefyClient)
    client.get_pipe_relations = AsyncMock()
    client.get_table_relations = AsyncMock()
    client.create_pipe_relation = AsyncMock()
    client.update_pipe_relation = AsyncMock()
    client.delete_pipe_relation = AsyncMock()
    client.create_card_relation = AsyncMock()
    return client


@pytest.fixture
def relation_mcp_server(mock_relation_client):
    mcp = FastMCP("Relation Tools Test")
    RelationTools.register(mcp, mock_relation_client)
    return mcp


@pytest.fixture
def relation_session(relation_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        relation_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_get_pipe_relations_success(
    relation_session, mock_relation_client, extract_payload
):
    mock_relation_client.get_pipe_relations.return_value = {
        "pipe": {
            "id": "1",
            "parentsRelations": [],
            "childrenRelations": [{"id": "x", "name": "Child"}],
        }
    }

    async with relation_session as session:
        result = await session.call_tool("get_pipe_relations", {"pipe_id": 1})

    assert result.isError is False
    mock_relation_client.get_pipe_relations.assert_awaited_once_with(1)
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["pipe"]["childrenRelations"][0]["name"] == "Child"


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_get_pipe_relations_graphql_error(
    relation_session, mock_relation_client, extract_payload
):
    mock_relation_client.get_pipe_relations.side_effect = TransportQueryError(
        "failed", errors=[{"message": "not allowed"}]
    )

    async with relation_session as session:
        result = await session.call_tool("get_pipe_relations", {"pipe_id": 9})

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not allowed" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_get_pipe_relations_invalid_pipe_id(
    relation_session, mock_relation_client, extract_payload
):
    async with relation_session as session:
        result = await session.call_tool("get_pipe_relations", {"pipe_id": ""})

    assert result.isError is False
    mock_relation_client.get_pipe_relations.assert_not_called()
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_get_pipe_relations_rejects_pipe_id_zero(
    relation_session, mock_relation_client, extract_payload
):
    async with relation_session as session:
        result = await session.call_tool("get_pipe_relations", {"pipe_id": 0})

    assert result.isError is False
    mock_relation_client.get_pipe_relations.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "pipe_id" in p["error"].lower()


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_get_table_relations_success(
    relation_session, mock_relation_client, extract_payload
):
    mock_relation_client.get_table_relations.return_value = {
        "table_relations": [{"id": "r1", "name": "T"}],
    }

    async with relation_session as session:
        result = await session.call_tool(
            "get_table_relations", {"relation_ids": ["r1"]}
        )

    assert result.isError is False
    mock_relation_client.get_table_relations.assert_awaited_once_with(["r1"])
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["table_relations"][0]["id"] == "r1"


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_get_table_relations_graphql_error(
    relation_session, mock_relation_client, extract_payload
):
    mock_relation_client.get_table_relations.side_effect = TransportQueryError(
        "failed", errors=[{"message": "boom"}]
    )

    async with relation_session as session:
        result = await session.call_tool("get_table_relations", {"relation_ids": [1]})

    assert result.isError is False
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_get_table_relations_invalid_relation_ids(
    relation_session, mock_relation_client, extract_payload
):
    async with relation_session as session:
        result = await session.call_tool("get_table_relations", {"relation_ids": []})

    assert result.isError is False
    mock_relation_client.get_table_relations.assert_not_called()
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_create_pipe_relation_success(
    relation_session, mock_relation_client, extract_payload
):
    mock_relation_client.create_pipe_relation.return_value = {
        "createPipeRelation": {"pipeRelation": {"id": "r1", "name": "L"}},
    }

    async with relation_session as session:
        result = await session.call_tool(
            "create_pipe_relation",
            {"parent_id": 1, "child_id": 2, "name": "L"},
        )

    assert result.isError is False
    mock_relation_client.create_pipe_relation.assert_awaited_once_with(
        1, 2, "L", extra_input=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["createPipeRelation"]["pipeRelation"]["id"] == "r1"


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_create_pipe_relation_graphql_error(
    relation_session, mock_relation_client, extract_payload
):
    mock_relation_client.create_pipe_relation.side_effect = TransportQueryError(
        "failed", errors=[{"message": "reject"}]
    )

    async with relation_session as session:
        result = await session.call_tool(
            "create_pipe_relation",
            {"parent_id": 1, "child_id": 2, "name": "x"},
        )

    assert extract_payload(result)["success"] is False
    assert "reject" in extract_payload(result)["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_create_pipe_relation_invalid_name(
    relation_session, mock_relation_client, extract_payload
):
    async with relation_session as session:
        result = await session.call_tool(
            "create_pipe_relation",
            {"parent_id": 1, "child_id": 2, "name": "   "},
        )

    mock_relation_client.create_pipe_relation.assert_not_called()
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_update_pipe_relation_success(
    relation_session, mock_relation_client, extract_payload
):
    mock_relation_client.update_pipe_relation.return_value = {
        "updatePipeRelation": {"pipeRelation": {"id": "9", "name": "N"}},
    }

    async with relation_session as session:
        result = await session.call_tool(
            "update_pipe_relation",
            {"relation_id": 9, "name": "N"},
        )

    assert result.isError is False
    mock_relation_client.update_pipe_relation.assert_awaited_once_with(
        9, "N", extra_input=None
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_update_pipe_relation_graphql_error(
    relation_session, mock_relation_client, extract_payload
):
    mock_relation_client.update_pipe_relation.side_effect = TransportQueryError(
        "failed", errors=[{"message": "fail"}]
    )

    async with relation_session as session:
        result = await session.call_tool(
            "update_pipe_relation",
            {"relation_id": 1, "name": "x"},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_delete_pipe_relation_success(
    relation_session, mock_relation_client, extract_payload
):
    mock_relation_client.delete_pipe_relation.return_value = {
        "deletePipeRelation": {"success": True},
    }

    async with relation_session as session:
        result = await session.call_tool(
            "delete_pipe_relation",
            {"relation_id": 100, "confirm": True},
        )

    assert result.isError is False
    mock_relation_client.delete_pipe_relation.assert_awaited_once_with(100)
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_delete_pipe_relation_graphql_error(
    relation_session, mock_relation_client, extract_payload
):
    mock_relation_client.delete_pipe_relation.side_effect = TransportQueryError(
        "failed", errors=[{"message": "denied"}]
    )

    async with relation_session as session:
        result = await session.call_tool(
            "delete_pipe_relation",
            {"relation_id": 1, "confirm": True},
        )

    assert extract_payload(result)["success"] is False
    assert "denied" in extract_payload(result)["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_delete_pipe_relation_has_destructive_hint(relation_session):
    async with relation_session as session:
        listed = await session.list_tools()
    delete_tool = next(t for t in listed.tools if t.name == "delete_pipe_relation")
    assert delete_tool.annotations is not None
    assert delete_tool.annotations.destructiveHint is True
    assert delete_tool.annotations.readOnlyHint is False


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_create_card_relation_success(
    relation_session, mock_relation_client, extract_payload
):
    mock_relation_client.create_card_relation.return_value = {
        "createCardRelation": {"cardRelation": {"id": "x"}},
    }

    async with relation_session as session:
        result = await session.call_tool(
            "create_card_relation",
            {"parent_id": 10, "child_id": 20, "source_id": 30},
        )

    assert result.isError is False
    mock_relation_client.create_card_relation.assert_awaited_once_with(
        10, 20, 30, extra_input=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["createCardRelation"]["cardRelation"]["id"] == "x"


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_create_card_relation_graphql_error(
    relation_session, mock_relation_client, extract_payload
):
    mock_relation_client.create_card_relation.side_effect = TransportQueryError(
        "failed", errors=[{"message": "invalid link"}]
    )

    async with relation_session as session:
        result = await session.call_tool(
            "create_card_relation",
            {"parent_id": 1, "child_id": 2, "source_id": 3},
        )

    p = extract_payload(result)
    assert p["success"] is False
    assert "invalid link" in p["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_create_card_relation_invalid_source_id(
    relation_session, mock_relation_client, extract_payload
):
    async with relation_session as session:
        result = await session.call_tool(
            "create_card_relation",
            {"parent_id": 1, "child_id": 2, "source_id": ""},
        )

    mock_relation_client.create_card_relation.assert_not_called()
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_create_pipe_relation_rejects_non_dict_extra_input(
    relation_session, mock_relation_client, extract_payload
):
    async with relation_session as session:
        result = await session.call_tool(
            "create_pipe_relation",
            {
                "parent_id": 1,
                "child_id": 2,
                "name": "L",
                "extra_input": "not-a-dict",
            },
        )

    mock_relation_client.create_pipe_relation.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "extra_input" in p["error"]
    assert "dict" in p["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_update_pipe_relation_rejects_non_dict_extra_input(
    relation_session, mock_relation_client, extract_payload
):
    async with relation_session as session:
        result = await session.call_tool(
            "update_pipe_relation",
            {"relation_id": 1, "name": "N", "extra_input": []},
        )

    mock_relation_client.update_pipe_relation.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "extra_input" in p["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("relation_session", [None], indirect=True)
async def test_create_card_relation_rejects_non_dict_extra_input(
    relation_session, mock_relation_client, extract_payload
):
    async with relation_session as session:
        result = await session.call_tool(
            "create_card_relation",
            {
                "parent_id": 1,
                "child_id": 2,
                "source_id": 3,
                "extra_input": 123,
            },
        )

    mock_relation_client.create_card_relation.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "extra_input" in p["error"]
