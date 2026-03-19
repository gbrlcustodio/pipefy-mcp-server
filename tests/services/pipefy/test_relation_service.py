"""Unit tests for RelationService (relation reads)."""

from unittest.mock import AsyncMock

import pytest
from gql.transport.exceptions import TransportQueryError

from pipefy_mcp.services.pipefy.queries.relation_queries import (
    CREATE_CARD_RELATION_MUTATION,
    CREATE_PIPE_RELATION_MUTATION,
    DELETE_PIPE_RELATION_MUTATION,
    GET_PIPE_RELATIONS_QUERY,
    GET_TABLE_RELATIONS_QUERY,
    UPDATE_PIPE_RELATION_MUTATION,
)
from pipefy_mcp.services.pipefy.relation_service import RelationService
from pipefy_mcp.settings import PipefySettings


@pytest.fixture
def mock_settings():
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings, return_value: dict):
    service = RelationService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_relations_sends_pipe_id(mock_settings):
    payload = {
        "pipe": {
            "id": "p1",
            "parentsRelations": [{"id": "r1", "name": "Up"}],
            "childrenRelations": [],
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_pipe_relations("p1")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is GET_PIPE_RELATIONS_QUERY
    assert variables == {"pipeId": "p1"}
    assert result["pipe"]["parentsRelations"][0]["name"] == "Up"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_relations_transport_error(mock_settings):
    service = RelationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_pipe_relations(1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_relations_sends_ids_list(mock_settings):
    rows = [{"id": "t1", "name": "Link"}]
    service = _make_service(mock_settings, {"table_relations": rows})
    result = await service.get_table_relations(["a", "b"])

    query, variables = service.execute_query.call_args[0]
    assert query is GET_TABLE_RELATIONS_QUERY
    assert variables == {"ids": ["a", "b"]}
    assert result["table_relations"] == rows


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_relations_transport_error(mock_settings):
    service = RelationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "missing"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_table_relations([99])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipe_relation_builds_input_and_returns_payload(mock_settings):
    created = {"createPipeRelation": {"pipeRelation": {"id": "r1", "name": "L"}}}
    service = _make_service(mock_settings, created)
    result = await service.create_pipe_relation(10, 20, "Link")

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_PIPE_RELATION_MUTATION
    inp = variables["input"]
    assert inp["parentId"] == "10"
    assert inp["childId"] == "20"
    assert inp["name"] == "Link"
    assert inp["canCreateNewItems"] is True
    assert inp["autoFillFieldEnabled"] is False
    assert result == created


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipe_relation_merges_attrs(mock_settings):
    service = _make_service(mock_settings, {"createPipeRelation": {}})
    await service.create_pipe_relation(
        1,
        2,
        "N",
        **{"canCreateNewItems": False, "ownFieldMaps": []},
    )
    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["canCreateNewItems"] is False
    assert inp["ownFieldMaps"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipe_relation_transport_error(mock_settings):
    service = RelationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "bad"}])
    )
    with pytest.raises(TransportQueryError):
        await service.create_pipe_relation(1, 2, "x")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pipe_relation_builds_input(mock_settings):
    updated = {"updatePipeRelation": {"pipeRelation": {"id": "r9", "name": "New"}}}
    service = _make_service(mock_settings, updated)
    result = await service.update_pipe_relation("r9", "New")

    query, variables = service.execute_query.call_args[0]
    assert query is UPDATE_PIPE_RELATION_MUTATION
    assert variables["input"]["id"] == "r9"
    assert variables["input"]["name"] == "New"
    assert variables["input"]["canConnectExistingItems"] is True
    assert result == updated


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pipe_relation_merges_attrs(mock_settings):
    service = _make_service(mock_settings, {"updatePipeRelation": {}})
    await service.update_pipe_relation(
        "r1",
        "N",
        **{"canConnectExistingItems": False},
    )
    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["canConnectExistingItems"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pipe_relation_transport_error(mock_settings):
    service = RelationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "nope"}])
    )
    with pytest.raises(TransportQueryError):
        await service.update_pipe_relation(5, "X")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_pipe_relation_sends_id(mock_settings):
    deleted = {"deletePipeRelation": {"success": True}}
    service = _make_service(mock_settings, deleted)
    result = await service.delete_pipe_relation(777)

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_PIPE_RELATION_MUTATION
    assert variables["input"] == {"id": "777"}
    assert result == deleted


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_pipe_relation_transport_error(mock_settings):
    service = RelationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "gone"}])
    )
    with pytest.raises(TransportQueryError):
        await service.delete_pipe_relation(1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_relation_builds_input(mock_settings):
    created = {"createCardRelation": {"cardRelation": {"id": "cr1"}}}
    service = _make_service(mock_settings, created)
    result = await service.create_card_relation(100, 200, 300)

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_CARD_RELATION_MUTATION
    inp = variables["input"]
    assert inp == {
        "parentId": "100",
        "childId": "200",
        "sourceId": "300",
        "sourceType": "PipeRelation",
    }
    assert result == created


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_relation_allows_source_type_override(mock_settings):
    service = _make_service(mock_settings, {"createCardRelation": {}})
    await service.create_card_relation(1, 2, 3, sourceType="Field")
    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["sourceType"] == "Field"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_relation_transport_error(mock_settings):
    service = RelationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "nope"}])
    )
    with pytest.raises(TransportQueryError):
        await service.create_card_relation(1, 2, 3)
