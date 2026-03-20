"""Unit tests for PipeConfigService (pipe CRUD mutations)."""

from unittest.mock import AsyncMock

import pytest
from gql.transport.exceptions import TransportQueryError

from pipefy_mcp.services.pipefy.pipe_config_service import PipeConfigService
from pipefy_mcp.services.pipefy.queries.pipe_config_queries import (
    CLONE_PIPE_MUTATION,
    CREATE_FIELD_CONDITION_MUTATION,
    CREATE_LABEL_MUTATION,
    CREATE_PHASE_FIELD_MUTATION,
    CREATE_PHASE_MUTATION,
    CREATE_PIPE_MUTATION,
    DELETE_FIELD_CONDITION_MUTATION,
    DELETE_LABEL_MUTATION,
    DELETE_PHASE_FIELD_MUTATION,
    DELETE_PHASE_MUTATION,
    DELETE_PIPE_MUTATION,
    UPDATE_FIELD_CONDITION_MUTATION,
    UPDATE_LABEL_MUTATION,
    UPDATE_PHASE_FIELD_MUTATION,
    UPDATE_PHASE_MUTATION,
    UPDATE_PIPE_MUTATION,
)
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
    service = PipeConfigService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipe_sends_input_and_returns_payload(mock_settings):
    service = _make_service(
        mock_settings, {"createPipe": {"pipe": {"id": "1", "name": "Alpha"}}}
    )
    result = await service.create_pipe("Alpha", 9001)

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_PIPE_MUTATION
    assert variables == {
        "input": {"name": "Alpha", "organization_id": 9001},
    }
    assert result == {"createPipe": {"pipe": {"id": "1", "name": "Alpha"}}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pipe_merges_id_and_non_none_attrs(mock_settings):
    service = _make_service(
        mock_settings, {"updatePipe": {"pipe": {"id": "2", "name": "Beta"}}}
    )
    result = await service.update_pipe(2, name="Beta", icon="star", color=None)

    query, variables = service.execute_query.call_args[0]
    assert query is UPDATE_PIPE_MUTATION
    assert variables == {
        "input": {"id": 2, "name": "Beta", "icon": "star"},
    }
    assert result == {"updatePipe": {"pipe": {"id": "2", "name": "Beta"}}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_pipe_sends_delete_input(mock_settings):
    service = _make_service(mock_settings, {"deletePipe": {"success": True}})
    result = await service.delete_pipe(42)

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_PIPE_MUTATION
    assert variables == {"input": {"id": 42}}
    assert result == {"deletePipe": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clone_pipe_sends_template_ids_only(mock_settings):
    service = _make_service(
        mock_settings,
        {"clonePipes": {"pipes": [{"id": "9", "name": "Clone"}]}},
    )
    result = await service.clone_pipe(303)

    query, variables = service.execute_query.call_args[0]
    assert query is CLONE_PIPE_MUTATION
    assert variables == {"input": {"pipe_template_ids": [303]}}
    assert result == {"clonePipes": {"pipes": [{"id": "9", "name": "Clone"}]}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clone_pipe_includes_organization_when_provided(mock_settings):
    service = _make_service(mock_settings, {"clonePipes": {"pipes": []}})
    await service.clone_pipe(1, organization_id=88)

    variables = service.execute_query.call_args[0][1]
    assert variables == {
        "input": {"pipe_template_ids": [1], "organization_id": 88},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_phase_sends_pipe_id_name_done_and_optional_index(
    mock_settings,
):
    service = _make_service(
        mock_settings,
        {"createPhase": {"phase": {"id": "1", "name": "Backlog", "done": False}}},
    )
    result = await service.create_phase(
        50,
        "Backlog",
        done=False,
        index=0,
        description="Incoming",
    )

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_PHASE_MUTATION
    assert variables == {
        "input": {
            "pipe_id": 50,
            "name": "Backlog",
            "done": False,
            "index": 0.0,
            "description": "Incoming",
        },
    }
    assert result == {
        "createPhase": {"phase": {"id": "1", "name": "Backlog", "done": False}},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_phase_omits_optional_fields_when_not_set(mock_settings):
    service = _make_service(
        mock_settings,
        {"createPhase": {"phase": {"id": "2", "name": "Done", "done": True}}},
    )
    await service.create_phase(51, "Done", done=True)

    variables = service.execute_query.call_args[0][1]
    assert variables == {
        "input": {"pipe_id": 51, "name": "Done", "done": True},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_phase_merges_id_and_attrs(mock_settings):
    service = _make_service(
        mock_settings,
        {"updatePhase": {"phase": {"id": "3", "name": "Renamed", "done": True}}},
    )
    result = await service.update_phase(3, name="Renamed", description=None, done=True)

    query, variables = service.execute_query.call_args[0]
    assert query is UPDATE_PHASE_MUTATION
    assert variables == {
        "input": {"id": 3, "name": "Renamed", "done": True},
    }
    assert result == {
        "updatePhase": {"phase": {"id": "3", "name": "Renamed", "done": True}},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_phase_sends_delete_input(mock_settings):
    service = _make_service(mock_settings, {"deletePhase": {"success": True}})
    result = await service.delete_phase(77)

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_PHASE_MUTATION
    assert variables == {"input": {"id": 77}}
    assert result == {"deletePhase": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_phase_field_sends_type_and_optional_attrs(mock_settings):
    service = _make_service(
        mock_settings,
        {
            "createPhaseField": {
                "phase_field": {"id": "f1", "label": "Email", "type": "email"},
            },
        },
    )
    result = await service.create_phase_field(
        10,
        "Email",
        "email",
        description="Work email",
        required=True,
    )

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_PHASE_FIELD_MUTATION
    assert variables == {
        "input": {
            "phase_id": 10,
            "label": "Email",
            "type": "email",
            "description": "Work email",
            "required": True,
        },
    }
    assert result == {
        "createPhaseField": {
            "phase_field": {"id": "f1", "label": "Email", "type": "email"},
        },
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_phase_field_merges_id_and_attrs(mock_settings):
    service = _make_service(
        mock_settings,
        {
            "updatePhaseField": {
                "phase_field": {"id": "5", "label": "Renamed", "type": "short_text"},
            },
        },
    )
    result = await service.update_phase_field(5, label="Renamed", description=None)

    query, variables = service.execute_query.call_args[0]
    assert query is UPDATE_PHASE_FIELD_MUTATION
    assert variables == {"input": {"id": 5, "label": "Renamed"}}
    assert result == {
        "updatePhaseField": {
            "phase_field": {"id": "5", "label": "Renamed", "type": "short_text"},
        },
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_phase_field_accepts_string_slug(mock_settings):
    service = _make_service(
        mock_settings,
        {
            "updatePhaseField": {
                "phase_field": {
                    "id": "detalhe_mcp",
                    "label": "Renamed",
                    "type": "short_text",
                },
            },
        },
    )
    result = await service.update_phase_field("detalhe_mcp", label="Renamed")

    _query, variables = service.execute_query.call_args[0]
    assert variables == {"input": {"id": "detalhe_mcp", "label": "Renamed"}}
    assert result == {
        "updatePhaseField": {
            "phase_field": {
                "id": "detalhe_mcp",
                "label": "Renamed",
                "type": "short_text",
            },
        },
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_phase_field_sends_delete_input(mock_settings):
    service = _make_service(mock_settings, {"deletePhaseField": {"success": True}})
    result = await service.delete_phase_field(99)

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_PHASE_FIELD_MUTATION
    assert variables == {"input": {"id": 99}}
    assert result == {"deletePhaseField": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_phase_field_accepts_string_slug(mock_settings):
    service = _make_service(mock_settings, {"deletePhaseField": {"success": True}})
    result = await service.delete_phase_field("detalhe_mcp")

    _query, variables = service.execute_query.call_args[0]
    assert variables == {"input": {"id": "detalhe_mcp"}}
    assert result == {"deletePhaseField": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_label_sends_pipe_name_color(mock_settings):
    service = _make_service(
        mock_settings,
        {"createLabel": {"label": {"id": "1", "name": "Bug", "color": "red"}}},
    )
    result = await service.create_label(20, "Bug", "red")

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_LABEL_MUTATION
    assert variables == {
        "input": {"pipe_id": 20, "name": "Bug", "color": "red"},
    }
    assert result == {
        "createLabel": {"label": {"id": "1", "name": "Bug", "color": "red"}},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_label_merges_id_and_attrs(mock_settings):
    service = _make_service(
        mock_settings,
        {"updateLabel": {"label": {"id": "2", "name": "Feature", "color": "blue"}}},
    )
    result = await service.update_label(2, name="Feature", color=None)

    query, variables = service.execute_query.call_args[0]
    assert query is UPDATE_LABEL_MUTATION
    assert variables == {"input": {"id": 2, "name": "Feature"}}
    assert result == {
        "updateLabel": {"label": {"id": "2", "name": "Feature", "color": "blue"}},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_label_sends_delete_input(mock_settings):
    service = _make_service(mock_settings, {"deleteLabel": {"success": True}})
    result = await service.delete_label(3)

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_LABEL_MUTATION
    assert variables == {"input": {"id": 3}}
    assert result == {"deleteLabel": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipe_propagates_execute_query_errors(mock_settings):
    service = PipeConfigService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=RuntimeError("upstream"))

    with pytest.raises(RuntimeError, match="upstream"):
        await service.create_pipe("X", 1)

    service.execute_query.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_field_condition_success(mock_settings):
    expr = {
        "expressions": [
            {
                "field_address": "trigger_field",
                "operation": "equals",
                "value": "yes",
            },
        ],
    }
    act = [{"phaseFieldId": "308821043", "whenEvaluator": True}]
    service = _make_service(
        mock_settings,
        {
            "createFieldCondition": {
                "fieldCondition": {"id": "cond-1"},
            },
        },
    )
    result = await service.create_field_condition(
        99,
        expr,
        act,
        name="Rule A",
        index=None,
    )

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_FIELD_CONDITION_MUTATION
    assert variables == {
        "input": {
            "phaseId": "99",
            "condition": expr,
            "actions": act,
            "name": "Rule A",
        },
    }
    assert result == {
        "createFieldCondition": {"fieldCondition": {"id": "cond-1"}},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_field_condition_transport_error(mock_settings):
    service = PipeConfigService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "invalid"}])
    )
    with pytest.raises(TransportQueryError):
        await service.create_field_condition(
            "pf-1",
            {"expressions": []},
            [{"phaseFieldId": "x"}],
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_field_condition_success(mock_settings):
    service = _make_service(
        mock_settings,
        {
            "updateFieldCondition": {
                "fieldCondition": {"id": "cond-2"},
            },
        },
    )
    result = await service.update_field_condition(
        "cond-2",
        name="Updated label",
        ignored=None,
    )

    query, variables = service.execute_query.call_args[0]
    assert query is UPDATE_FIELD_CONDITION_MUTATION
    assert variables == {
        "input": {"id": "cond-2", "name": "Updated label"},
    }
    assert result == {
        "updateFieldCondition": {"fieldCondition": {"id": "cond-2"}},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_field_condition_transport_error(mock_settings):
    service = PipeConfigService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "not found"}])
    )
    with pytest.raises(TransportQueryError):
        await service.update_field_condition("missing-id", name=None, phase_id="88")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_field_condition_success(mock_settings):
    service = _make_service(mock_settings, {"deleteFieldCondition": {"success": True}})
    result = await service.delete_field_condition("cond-9")

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_FIELD_CONDITION_MUTATION
    assert variables == {"input": {"id": "cond-9"}}
    assert result == {"success": True}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_field_condition_transport_error(mock_settings):
    service = PipeConfigService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "forbidden"}])
    )
    with pytest.raises(TransportQueryError):
        await service.delete_field_condition("cond-x")
