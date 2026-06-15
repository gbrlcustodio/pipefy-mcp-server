"""Unit tests for PipeConfigService (pipe CRUD mutations)."""

from unittest.mock import AsyncMock

import pytest
from gql.transport.exceptions import TransportQueryError
from graphql import print_ast
from pipefy_auth import StaticBearerAuth

from pipefy_sdk.queries.pipe_config_queries import (
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
    GET_FIELD_CONDITION_QUERY,
    GET_FIELD_CONDITIONS_QUERY,
    UPDATE_FIELD_CONDITION_MUTATION,
    UPDATE_LABEL_MUTATION,
    UPDATE_PHASE_FIELD_MUTATION,
    UPDATE_PHASE_MUTATION,
    UPDATE_PIPE_MUTATION,
)
from pipefy_sdk.services.pipe_config_service import PipeConfigService
from pipefy_sdk.settings import PipefySettings

_TEST_AUTH = StaticBearerAuth("test-bearer-token")


@pytest.fixture
def mock_settings():
    return PipefySettings(
        base_url="https://api.pipefy.com",
    )


def _make_service(mock_settings, return_value: dict):
    service = PipeConfigService(settings=mock_settings, auth=_TEST_AUTH)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


def _make_service_with_pipe(mock_settings, return_value: dict, pipe_service: AsyncMock):
    service = PipeConfigService(
        settings=mock_settings, auth=_TEST_AUTH, pipe_service=pipe_service
    )
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
        "input": {"name": "Alpha", "organization_id": "9001"},
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
        "input": {"id": "2", "name": "Beta", "icon": "star"},
    }
    assert result == {"updatePipe": {"pipe": {"id": "2", "name": "Beta"}}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pipe_accepts_alphanumeric_id(mock_settings):
    """Test update_pipe passes an alphanumeric ID through to GraphQL variables unchanged."""
    service = _make_service(
        mock_settings, {"updatePipe": {"pipe": {"id": "Yr5RUVCi", "name": "X"}}}
    )
    await service.update_pipe("Yr5RUVCi", name="X")

    variables = service.execute_query.call_args[0][1]
    assert variables == {"input": {"id": "Yr5RUVCi", "name": "X"}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_pipe_sends_delete_input(mock_settings):
    service = _make_service(mock_settings, {"deletePipe": {"success": True}})
    result = await service.delete_pipe(42)

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_PIPE_MUTATION
    assert variables == {"input": {"id": "42"}}
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
    assert variables == {"input": {"pipe_template_ids": ["303"]}}
    assert result == {"clonePipes": {"pipes": [{"id": "9", "name": "Clone"}]}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clone_pipe_includes_organization_when_provided(mock_settings):
    service = _make_service(mock_settings, {"clonePipes": {"pipes": []}})
    await service.clone_pipe(1, organization_id=88)

    variables = service.execute_query.call_args[0][1]
    assert variables == {
        "input": {"pipe_template_ids": ["1"], "organization_id": "88"},
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
            "pipe_id": "50",
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
        "input": {"pipe_id": "51", "name": "Done", "done": True},
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
        "input": {"id": "3", "name": "Renamed", "done": True},
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
    assert variables == {"input": {"id": "77"}}
    assert result == {"deletePhase": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_phase_field_sends_type_and_optional_attrs(mock_settings):
    service = _make_service(
        mock_settings,
        {
            "createPhaseField": {
                "phase_field": {
                    "id": "f1",
                    "internal_id": "99001",
                    "uuid": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                    "label": "Email",
                    "type": "email",
                },
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
            "phase_id": "10",
            "label": "Email",
            "type": "email",
            "description": "Work email",
            "required": True,
        },
    }
    assert result == {
        "createPhaseField": {
            "phase_field": {
                "id": "f1",
                "internal_id": "99001",
                "uuid": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                "label": "Email",
                "type": "email",
            },
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
    assert variables == {"input": {"id": "5", "label": "Renamed"}}
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
async def test_update_phase_field_resolves_slug_via_phase_id(mock_settings):
    """Narrow resolver: ``phase_id`` injects the field's ``uuid`` for slug disambiguation."""
    pipe_svc = AsyncMock()
    pipe_svc.get_phase_fields = AsyncMock(
        return_value={
            "fields": [
                {
                    "id": "priority",
                    "internal_id": "429358624",
                    "uuid": "08c3f133-6dae-4a35-9276-b6d0d63a7c24",
                    "label": "Priority",
                    "type": "select",
                },
            ],
        },
    )
    service = _make_service_with_pipe(
        mock_settings,
        {
            "updatePhaseField": {
                "phase_field": {
                    "id": "priority",
                    "label": "Priority",
                    "type": "select",
                },
            },
        },
        pipe_svc,
    )
    result = await service.update_phase_field(
        "priority",
        label="Priority",
        description="x",
        phase_id="343162749",
    )
    pipe_svc.get_phase_fields.assert_awaited_once_with("343162749")
    pipe_svc.get_pipe.assert_not_called()
    _q, variables = service.execute_query.call_args[0]
    assert variables == {
        "input": {
            "id": "priority",
            "uuid": "08c3f133-6dae-4a35-9276-b6d0d63a7c24",
            "label": "Priority",
            "description": "x",
        }
    }
    assert result["updatePhaseField"]["phase_field"]["id"] == "priority"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_phase_field_resolves_slug_via_pipe_id(mock_settings):
    """Pipe-wide resolver: unique slug across pipe injects the field's ``uuid``."""
    pipe_svc = AsyncMock()
    pipe_svc.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "phases": [
                    {
                        "id": "ph1",
                    },
                ],
                "start_form_fields": [],
            },
        },
    )
    pipe_svc.get_phase_fields = AsyncMock(
        return_value={
            "fields": [
                {
                    "id": "priority",
                    "internal_id": "429358624",
                    "uuid": "08c3f133-6dae-4a35-9276-b6d0d63a7c24",
                    "label": "Priority",
                    "type": "select",
                },
            ],
        },
    )
    service = _make_service_with_pipe(
        mock_settings,
        {
            "updatePhaseField": {
                "phase_field": {
                    "id": "priority",
                    "label": "Priority",
                    "type": "select",
                },
            },
        },
        pipe_svc,
    )
    result = await service.update_phase_field(
        "priority",
        label="Priority",
        description="x",
        pipe_id="501",
    )
    _q, variables = service.execute_query.call_args[0]
    assert variables == {
        "input": {
            "id": "priority",
            "uuid": "08c3f133-6dae-4a35-9276-b6d0d63a7c24",
            "label": "Priority",
            "description": "x",
        }
    }
    assert result["updatePhaseField"]["phase_field"]["id"] == "priority"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_phase_field_ambiguous_slug_raises(mock_settings):
    pipe_svc = AsyncMock()
    pipe_svc.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "phases": [{"id": "p1"}, {"id": "p2"}],
                "start_form_fields": [],
            },
        },
    )
    dup_field = {
        "id": "status",
        "internal_id": "111",
        "uuid": "aaaaaaaa-1111-1111-1111-111111111111",
        "label": "S",
        "type": "select",
    }
    dup_field_b = {
        "id": "status",
        "internal_id": "222",
        "uuid": "bbbbbbbb-2222-2222-2222-222222222222",
        "label": "S2",
        "type": "select",
    }

    async def _gf(phase_id, required_only=False):
        _ = required_only
        if str(phase_id) == "p1":
            return {"fields": [dup_field]}
        return {"fields": [dup_field_b]}

    pipe_svc.get_phase_fields = AsyncMock(side_effect=_gf)
    service = _make_service_with_pipe(mock_settings, {}, pipe_svc)
    service.execute_query = AsyncMock()
    with pytest.raises(ValueError, match="uuid"):
        await service.update_phase_field("status", label="L", pipe_id="9")
    service.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_phase_field_parallel_phase_fetches_resolve_slug(mock_settings):
    """``get_phase_fields`` runs concurrently for each phase (``asyncio.gather``)."""
    pipe_svc = AsyncMock()
    pipe_svc.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "phases": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                "start_form_fields": [],
            },
        },
    )

    async def _gf(phase_id, required_only=False):
        _ = required_only
        if str(phase_id) == "b":
            return {
                "fields": [
                    {
                        "id": "priority",
                        "internal_id": "777",
                        "uuid": "fffffff7-7777-7777-7777-777777777777",
                        "label": "P",
                        "type": "select",
                    },
                ],
            }
        return {"fields": []}

    pipe_svc.get_phase_fields = AsyncMock(side_effect=_gf)
    service = _make_service_with_pipe(
        mock_settings,
        {
            "updatePhaseField": {
                "phase_field": {"id": "priority", "label": "P", "type": "select"},
            },
        },
        pipe_svc,
    )
    await service.update_phase_field("priority", label="P", pipe_id="1")
    assert pipe_svc.get_phase_fields.await_count == 3
    _q, variables = service.execute_query.call_args[0]
    assert variables == {
        "input": {
            "id": "priority",
            "uuid": "fffffff7-7777-7777-7777-777777777777",
            "label": "P",
        }
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_phase_field_slug_raises_when_any_phase_fetch_fails(mock_settings):
    """Do not inject a single uuid if another phase's fields could not be loaded."""
    pipe_svc = AsyncMock()
    pipe_svc.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "phases": [{"id": "p1"}, {"id": "p2"}],
                "start_form_fields": [],
            },
        },
    )

    async def _gf(phase_id, required_only=False):
        _ = required_only
        if str(phase_id) == "p1":
            return {
                "fields": [
                    {
                        "id": "priority",
                        "internal_id": "111",
                        "uuid": "aaaaaaaa-1111-1111-1111-111111111111",
                        "label": "P",
                        "type": "select",
                    },
                ],
            }
        raise RuntimeError("network")

    pipe_svc.get_phase_fields = AsyncMock(side_effect=_gf)
    service = _make_service_with_pipe(mock_settings, {}, pipe_svc)
    service.execute_query = AsyncMock()
    with pytest.raises(ValueError, match="Could not load fields"):
        await service.update_phase_field("priority", label="L", pipe_id="9")
    service.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_phase_field_slug_raises_when_zero_matches_and_partial_failure(
    mock_settings,
):
    """Zero matches + at least one failed phase fetch is still ambiguous, not "not found"."""
    pipe_svc = AsyncMock()
    pipe_svc.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "phases": [{"id": "p1"}, {"id": "p2"}],
                "start_form_fields": [],
            },
        },
    )

    async def _gf(phase_id, required_only=False):
        _ = required_only
        if str(phase_id) == "p1":
            return {"fields": [{"id": "other", "internal_id": "111"}]}
        raise RuntimeError("network")

    pipe_svc.get_phase_fields = AsyncMock(side_effect=_gf)
    service = _make_service_with_pipe(mock_settings, {}, pipe_svc)
    service.execute_query = AsyncMock()
    with pytest.raises(ValueError, match="Could not load fields"):
        await service.update_phase_field("missing_slug", label="L", pipe_id="9")
    service.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_phase_field_sends_delete_input(mock_settings):
    service = _make_service(mock_settings, {"deletePhaseField": {"success": True}})
    result = await service.delete_phase_field(99)

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_PHASE_FIELD_MUTATION
    assert variables == {"input": {"id": "99"}}
    assert result == {"deletePhaseField": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_phase_field_accepts_string_slug(mock_settings):
    service = _make_service(mock_settings, {"deletePhaseField": {"success": True}})
    result = await service.delete_phase_field("prioridade")

    _query, variables = service.execute_query.call_args[0]
    assert variables == {"input": {"id": "prioridade"}}
    assert result == {"deletePhaseField": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_phase_field_includes_pipe_uuid_when_provided(mock_settings):
    service = _make_service(mock_settings, {"deletePhaseField": {"success": True}})
    result = await service.delete_phase_field(
        "prioridade", pipe_uuid="b3bba313-6b99-44dc-b17e-f192dc00bb21"
    )

    _query, variables = service.execute_query.call_args[0]
    assert variables == {
        "input": {
            "id": "prioridade",
            "pipeUuid": "b3bba313-6b99-44dc-b17e-f192dc00bb21",
        },
    }
    assert result == {"deletePhaseField": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_label_sends_pipe_name_color(mock_settings):
    service = _make_service(
        mock_settings,
        {"createLabel": {"label": {"id": "1", "name": "Bug", "color": "#FF0000"}}},
    )
    result = await service.create_label(20, "Bug", "#FF0000")

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_LABEL_MUTATION
    assert variables == {
        "input": {"pipe_id": "20", "name": "Bug", "color": "#FF0000"},
    }
    assert result == {
        "createLabel": {"label": {"id": "1", "name": "Bug", "color": "#FF0000"}},
    }


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_color", "normalized_color"),
    [("#abc", "#AABBCC"), ("#ff0000", "#FF0000")],
)
async def test_create_label_normalizes_color(
    mock_settings, raw_color, normalized_color
):
    service = _make_service(mock_settings, {"createLabel": {"label": {"id": "1"}}})
    await service.create_label(20, "Bug", raw_color)

    variables = service.execute_query.call_args[0][1]
    assert variables["input"]["color"] == normalized_color


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_label_rejects_non_hex_color(mock_settings):
    service = _make_service(mock_settings, {})

    with pytest.raises(ValueError, match="expected #RGB or #RRGGBB hex color"):
        await service.create_label(20, "Bug", "red")

    service.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_label_normalizes_color(mock_settings):
    service = _make_service(mock_settings, {"updateLabel": {"label": {"id": "2"}}})
    await service.update_label(2, name="Feature", color="#abc")

    variables = service.execute_query.call_args[0][1]
    assert variables["input"]["color"] == "#AABBCC"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_label_rejects_non_hex_color(mock_settings):
    service = _make_service(mock_settings, {})

    with pytest.raises(ValueError, match="expected #RGB or #RRGGBB hex color"):
        await service.update_label(2, name="Feature", color="blue")

    service.execute_query.assert_not_called()


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
    assert variables == {"input": {"id": "2", "name": "Feature"}}
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
    assert variables == {"input": {"id": "3"}}
    assert result == {"deleteLabel": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipe_propagates_execute_query_errors(mock_settings):
    service = PipeConfigService(settings=mock_settings, auth=_TEST_AUTH)
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
async def test_create_field_condition_normalizes_actions_and_condition(mock_settings):
    """Service normalizes both legacy ``actionId: hidden`` and structural ids before sending."""
    expr = {
        "expressions": [
            {
                "id": "client-token",
                "field_address": "a",
                "operation": "equals",
                "value": "yes",
                "structure_id": "0",
            },
        ],
        "expressions_structure": [["0"]],
    }
    actions = [{"phaseFieldId": "1", "actionId": "hidden"}]
    service = _make_service(
        mock_settings,
        {"createFieldCondition": {"fieldCondition": {"id": "cond-norm"}}},
    )

    await service.create_field_condition(99, expr, actions, name="R")

    _, variables = service.execute_query.call_args[0]
    payload = variables["input"]
    assert payload["condition"]["expressions"][0].get("id") is None
    assert payload["condition"]["expressions"][0]["structure_id"] == 0
    assert payload["condition"]["expressions_structure"] == [[0]]
    assert payload["actions"][0]["actionId"] == "hide"
    assert payload["actions"] is not actions
    assert payload["actions"][0] is not actions[0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_field_condition_rejects_reserved_phaseId_attr(mock_settings):
    """``phaseId`` via ``**attrs`` raises instead of silently overriding the positional phase_id.

    Snake-case ``phase_id``, ``condition``, and ``actions`` cannot reach ``**attrs``
    at all — Python's call binding raises :class:`TypeError` first because those
    names collide with the explicit positional parameters.
    """
    service = _make_service(
        mock_settings,
        {"createFieldCondition": {"fieldCondition": {"id": "x"}}},
    )

    with pytest.raises(ValueError, match="phaseId"):
        await service.create_field_condition(
            "99",
            {"expressions": []},
            [{"phaseFieldId": "1"}],
            name="R",
            phaseId="override",
        )

    service.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_field_condition_transport_error(mock_settings):
    service = PipeConfigService(settings=mock_settings, auth=_TEST_AUTH)
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
async def test_update_field_condition_normalizes_actions(mock_settings):
    """Update normalizes ``actions`` (``hidden`` → ``hide``) when provided."""
    service = _make_service(
        mock_settings,
        {"updateFieldCondition": {"fieldCondition": {"id": "c"}}},
    )

    await service.update_field_condition(
        "c",
        actions=[{"phaseFieldId": "1", "actionId": "hidden"}],
    )

    _, variables = service.execute_query.call_args[0]
    assert variables["input"]["actions"][0]["actionId"] == "hide"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_field_condition_rejects_reserved_id_attr(mock_settings):
    """The ``id`` key must come via the positional ``condition_id`` argument."""
    service = _make_service(
        mock_settings,
        {"updateFieldCondition": {"fieldCondition": {"id": "c"}}},
    )

    with pytest.raises(ValueError, match="id"):
        await service.update_field_condition("c", id="other-id")

    service.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_field_condition_transport_error(mock_settings):
    service = PipeConfigService(settings=mock_settings, auth=_TEST_AUTH)
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
    service = PipeConfigService(settings=mock_settings, auth=_TEST_AUTH)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "forbidden"}])
    )
    with pytest.raises(TransportQueryError):
        await service.delete_field_condition("cond-x")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_field_conditions_success(mock_settings):
    api_payload = {
        "phase": {
            "fieldConditions": [
                {
                    "id": "fc-1",
                    "name": "Rule A",
                    "condition": {
                        "expressions": [
                            {
                                "field_address": "x",
                                "operation": "equals",
                                "value": "1",
                            },
                        ],
                    },
                    "actions": [{"actionId": "hide", "phaseFieldId": "pf-9"}],
                },
            ],
        },
    }
    service = _make_service(mock_settings, api_payload)
    result = await service.get_field_conditions(404)

    query, variables = service.execute_query.call_args[0]
    assert query is GET_FIELD_CONDITIONS_QUERY
    assert "actionId" in print_ast(GET_FIELD_CONDITIONS_QUERY.document)
    assert variables == {"phaseId": "404"}
    assert result == api_payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_field_condition_success(mock_settings):
    api_payload = {
        "fieldCondition": {
            "id": "fc-2",
            "name": "Rule B",
            "phase": {"id": "88", "name": "Form"},
            "condition": {"expressions": []},
            "actions": [{"actionId": "hide", "phaseFieldId": "pf-9"}],
        },
    }
    service = _make_service(mock_settings, api_payload)
    result = await service.get_field_condition("fc-2")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_FIELD_CONDITION_QUERY
    assert "actionId" in print_ast(GET_FIELD_CONDITION_QUERY.document)
    assert variables == {"id": "fc-2"}
    assert result == api_payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_field_condition_transport_error(mock_settings):
    service = PipeConfigService(settings=mock_settings, auth=_TEST_AUTH)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "not found"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_field_condition("missing")
