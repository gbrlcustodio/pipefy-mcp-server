"""Unit tests for RelationService (relation reads)."""

import pytest
from _shared.mock_clients import mock_executor

from pipefy_sdk import PipefyGraphQLError
from pipefy_sdk.queries.relation_queries import (
    CREATE_CARD_RELATION_MUTATION,
    CREATE_PIPE_RELATION_MUTATION,
    DELETE_PIPE_RELATION_MUTATION,
    GET_PIPE_RELATIONS_QUERY,
    GET_TABLE_RELATIONS_QUERY,
    INTERNAL_DELETE_CARD_RELATION_MUTATION,
    UPDATE_PIPE_RELATION_MUTATION,
)
from pipefy_sdk.services.relation_service import RelationService


def _make_service(return_value: dict | None = None, *, side_effect=None):
    """Build a RelationService whose public GraphQL executor is faked.

    These tests never touch the internal executor, so it gets a stand-in; the
    constructor requires one. Pass ``side_effect`` for the error-path tests.
    """
    executor = mock_executor(return_value, side_effect=side_effect)
    service = RelationService(executor=executor, internal_executor=mock_executor())
    return service, executor


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_relations_sends_pipe_id():
    payload = {
        "pipe": {
            "id": "p1",
            "parentsRelations": [{"id": "r1", "name": "Up"}],
            "childrenRelations": [],
        }
    }
    service, executor = _make_service(payload)
    result = await service.get_pipe_relations("701")

    executor.execute_query.assert_awaited_once()
    query, variables = executor.execute_query.call_args[0]
    assert query is GET_PIPE_RELATIONS_QUERY
    assert variables == {"pipeId": "701"}
    assert result["pipe"]["parentsRelations"][0]["name"] == "Up"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_relations_transport_error():
    service, _ = _make_service(
        side_effect=PipefyGraphQLError([{"message": "denied"}]),
    )
    with pytest.raises(PipefyGraphQLError):
        await service.get_pipe_relations(1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_relations_sends_ids_list():
    rows = [{"id": "t1", "name": "Link"}]
    service, executor = _make_service({"table_relations": rows})
    result = await service.get_table_relations(["801", "802"])

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_TABLE_RELATIONS_QUERY
    assert variables == {"ids": ["801", "802"]}
    assert result["table_relations"] == rows


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_table_relations_transport_error():
    service, _ = _make_service(
        side_effect=PipefyGraphQLError([{"message": "missing"}]),
    )
    with pytest.raises(PipefyGraphQLError):
        await service.get_table_relations([99])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipe_relation_builds_input_and_returns_payload():
    created = {"createPipeRelation": {"pipeRelation": {"id": "r1", "name": "L"}}}
    service, executor = _make_service(created)
    result = await service.create_pipe_relation(10, 20, "Link")

    query, variables = executor.execute_query.call_args[0]
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
async def test_create_pipe_relation_merges_attrs():
    service, executor = _make_service({"createPipeRelation": {}})
    await service.create_pipe_relation(
        1,
        2,
        "N",
        **{"canCreateNewItems": False, "ownFieldMaps": []},
    )
    inp = executor.execute_query.call_args[0][1]["input"]
    assert inp["canCreateNewItems"] is False
    assert inp["ownFieldMaps"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipe_relation_transport_error():
    service, _ = _make_service(
        side_effect=PipefyGraphQLError([{"message": "bad"}]),
    )
    with pytest.raises(PipefyGraphQLError):
        await service.create_pipe_relation(1, 2, "x")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pipe_relation_builds_input():
    updated = {"updatePipeRelation": {"pipeRelation": {"id": "r9", "name": "New"}}}
    service, executor = _make_service(updated)
    result = await service.update_pipe_relation("r9", "New")

    query, variables = executor.execute_query.call_args[0]
    assert query is UPDATE_PIPE_RELATION_MUTATION
    assert variables["input"]["id"] == "r9"
    assert variables["input"]["name"] == "New"
    assert variables["input"]["canConnectExistingItems"] is True
    assert result == updated


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pipe_relation_merges_attrs():
    service, executor = _make_service({"updatePipeRelation": {}})
    await service.update_pipe_relation(
        "r1",
        "N",
        **{"canConnectExistingItems": False},
    )
    inp = executor.execute_query.call_args[0][1]["input"]
    assert inp["canConnectExistingItems"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pipe_relation_transport_error():
    service, _ = _make_service(
        side_effect=PipefyGraphQLError([{"message": "nope"}]),
    )
    with pytest.raises(PipefyGraphQLError):
        await service.update_pipe_relation(5, "X")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_pipe_relation_sends_id():
    deleted = {"deletePipeRelation": {"success": True}}
    service, executor = _make_service(deleted)
    result = await service.delete_pipe_relation(777)

    query, variables = executor.execute_query.call_args[0]
    assert query is DELETE_PIPE_RELATION_MUTATION
    assert variables["input"] == {"id": "777"}
    assert result == deleted


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_pipe_relation_transport_error():
    service, _ = _make_service(
        side_effect=PipefyGraphQLError([{"message": "gone"}]),
    )
    with pytest.raises(PipefyGraphQLError):
        await service.delete_pipe_relation(1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_relation_builds_input():
    created = {"createCardRelation": {"cardRelation": {"id": "cr1"}}}
    service, executor = _make_service(created)
    result = await service.create_card_relation(100, 200, 300)

    query, variables = executor.execute_query.call_args[0]
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
async def test_create_card_relation_allows_source_type_override():
    service, executor = _make_service({"createCardRelation": {}})
    await service.create_card_relation(1, 2, 3, sourceType="Field")
    inp = executor.execute_query.call_args[0][1]["input"]
    assert inp["sourceType"] == "Field"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_relation_transport_error():
    service, _ = _make_service(
        side_effect=PipefyGraphQLError([{"message": "nope"}]),
    )
    with pytest.raises(PipefyGraphQLError):
        await service.create_card_relation(1, 2, 3)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_card_relation_routes_through_internal_executor():
    """delete_card_relation uses the injected internal GraphQL executor, not the public
    one, because the mutation only exists on the internal schema."""
    internal = mock_executor({"deleteCardRelation": {"success": True}})
    service = RelationService(executor=mock_executor(), internal_executor=internal)

    result = await service.delete_card_relation("c1", "p2", "src-3")

    internal.execute_query.assert_awaited_once_with(
        INTERNAL_DELETE_CARD_RELATION_MUTATION,
        {"childId": "c1", "parentId": "p2", "sourceId": "src-3"},
    )
    assert result == {"deleteCardRelation": {"success": True}}
