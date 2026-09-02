"""Unit tests for PipeConfigService (pipe CRUD mutations)."""

from unittest.mock import AsyncMock

import pytest
from _shared.mock_clients import mock_executor
from graphql import print_ast
from pydantic import ValidationError

from pipefy_sdk import PipefyGraphQLError
from pipefy_sdk.graphql_inputs import (
    CreateFieldConditionInput,
    CreatePhaseFieldInput,
    UpdateFieldConditionInput,
    UpdateLabelInput,
    UpdatePhaseFieldInput,
    UpdatePhaseInput,
    UpdatePipeInput,
)
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


def _make_service(return_value: dict):
    executor = mock_executor(return_value)
    service = PipeConfigService(executor=executor, pipe_service=AsyncMock())
    return service, executor


def _make_service_with_pipe(return_value: dict, pipe_service: AsyncMock):
    executor = mock_executor(return_value)
    service = PipeConfigService(executor=executor, pipe_service=pipe_service)
    return service, executor


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipe_sends_input_and_returns_payload():
    service, executor = _make_service(
        {"createPipe": {"pipe": {"id": "1", "name": "Alpha"}}}
    )
    result = await service.create_pipe("Alpha", 9001)

    executor.execute_query.assert_awaited_once()
    query, variables = executor.execute_query.call_args[0]
    assert query is CREATE_PIPE_MUTATION
    assert variables == {
        "input": {"name": "Alpha", "organization_id": "9001"},
    }
    assert result == {"createPipe": {"pipe": {"id": "1", "name": "Alpha"}}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pipe_merges_id_and_non_none_attrs():
    service, executor = _make_service(
        {"updatePipe": {"pipe": {"id": "2", "name": "Beta"}}}
    )
    result = await service.update_pipe(
        UpdatePipeInput(id="2", name="Beta", icon="star", color=None)
    )

    query, variables = executor.execute_query.call_args[0]
    assert query is UPDATE_PIPE_MUTATION
    assert variables == {
        "input": {"id": "2", "name": "Beta", "icon": "star"},
    }
    assert result == {"updatePipe": {"pipe": {"id": "2", "name": "Beta"}}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pipe_accepts_alphanumeric_id():
    """Test update_pipe passes an alphanumeric ID through to GraphQL variables unchanged."""
    service, executor = _make_service(
        {"updatePipe": {"pipe": {"id": "Yr5RUVCi", "name": "X"}}}
    )
    await service.update_pipe(UpdatePipeInput(id="Yr5RUVCi", name="X"))

    variables = executor.execute_query.call_args[0][1]
    assert variables == {"input": {"id": "Yr5RUVCi", "name": "X"}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_pipe_sends_delete_input():
    service, executor = _make_service({"deletePipe": {"success": True}})
    result = await service.delete_pipe(42)

    query, variables = executor.execute_query.call_args[0]
    assert query is DELETE_PIPE_MUTATION
    assert variables == {"input": {"id": "42"}}
    assert result == {"deletePipe": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clone_pipe_sends_template_ids_only():
    service, executor = _make_service(
        {"clonePipes": {"pipes": [{"id": "9", "name": "Clone"}]}},
    )
    result = await service.clone_pipe(303)

    query, variables = executor.execute_query.call_args[0]
    assert query is CLONE_PIPE_MUTATION
    assert variables == {"input": {"pipe_template_ids": ["303"]}}
    assert result == {"clonePipes": {"pipes": [{"id": "9", "name": "Clone"}]}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clone_pipe_includes_organization_when_provided():
    service, executor = _make_service({"clonePipes": {"pipes": []}})
    await service.clone_pipe(1, organization_id=88)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {
        "input": {"pipe_template_ids": ["1"], "organization_id": "88"},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_phase_sends_pipe_id_name_done_and_optional_index():
    service, executor = _make_service(
        {"createPhase": {"phase": {"id": "1", "name": "Backlog", "done": False}}},
    )
    result = await service.create_phase(
        50,
        "Backlog",
        done=False,
        index=0,
        description="Incoming",
    )

    query, variables = executor.execute_query.call_args[0]
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
async def test_create_phase_omits_optional_fields_when_not_set():
    service, executor = _make_service(
        {"createPhase": {"phase": {"id": "2", "name": "Done", "done": True}}},
    )
    await service.create_phase(51, "Done", done=True)

    variables = executor.execute_query.call_args[0][1]
    assert variables == {
        "input": {"pipe_id": "51", "name": "Done", "done": True},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_phase_merges_id_and_attrs():
    service, executor = _make_service(
        {"updatePhase": {"phase": {"id": "3", "name": "Renamed", "done": True}}},
    )
    result = await service.update_phase(
        UpdatePhaseInput(id="3", name="Renamed", description=None, done=True)
    )

    query, variables = executor.execute_query.call_args[0]
    assert query is UPDATE_PHASE_MUTATION
    assert variables == {
        "input": {"id": "3", "name": "Renamed", "done": True},
    }
    assert result == {
        "updatePhase": {"phase": {"id": "3", "name": "Renamed", "done": True}},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_phase_sends_delete_input():
    service, executor = _make_service({"deletePhase": {"success": True}})
    result = await service.delete_phase(77)

    query, variables = executor.execute_query.call_args[0]
    assert query is DELETE_PHASE_MUTATION
    assert variables == {"input": {"id": "77"}}
    assert result == {"deletePhase": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_phase_field_sends_type_and_optional_attrs():
    service, executor = _make_service(
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
        CreatePhaseFieldInput(
            phase_id="10",
            label="Email",
            type="email",
            description="Work email",
            required=True,
        )
    )

    query, variables = executor.execute_query.call_args[0]
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
async def test_update_phase_field_merges_id_and_attrs():
    service, executor = _make_service(
        {
            "updatePhaseField": {
                "phase_field": {"id": "5", "label": "Renamed", "type": "short_text"},
            },
        },
    )
    result = await service.update_phase_field(
        UpdatePhaseFieldInput(id="5", label="Renamed", description=None)
    )

    query, variables = executor.execute_query.call_args[0]
    assert query is UPDATE_PHASE_FIELD_MUTATION
    assert variables == {"input": {"id": "5", "label": "Renamed"}}
    assert result == {
        "updatePhaseField": {
            "phase_field": {"id": "5", "label": "Renamed", "type": "short_text"},
        },
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_phase_field_accepts_string_slug():
    service, executor = _make_service(
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
    result = await service.update_phase_field(
        UpdatePhaseFieldInput(id="detalhe_mcp", label="Renamed")
    )

    _query, variables = executor.execute_query.call_args[0]
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
async def test_update_phase_field_resolves_slug_via_phase_id():
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
    service, executor = _make_service_with_pipe(
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
        UpdatePhaseFieldInput(id="priority", label="Priority", description="x"),
        phase_id="343162749",
    )
    pipe_svc.get_phase_fields.assert_awaited_once_with("343162749")
    pipe_svc.get_pipe.assert_not_called()
    _q, variables = executor.execute_query.call_args[0]
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
async def test_update_phase_field_resolves_slug_via_pipe_id():
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
    service, executor = _make_service_with_pipe(
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
        UpdatePhaseFieldInput(id="priority", label="Priority", description="x"),
        pipe_id="501",
    )
    _q, variables = executor.execute_query.call_args[0]
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
async def test_update_phase_field_ambiguous_slug_raises():
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
    service, executor = _make_service_with_pipe({}, pipe_svc)
    executor.execute_query = AsyncMock()
    with pytest.raises(ValueError, match="uuid"):
        await service.update_phase_field(
            UpdatePhaseFieldInput(id="status", label="L"), pipe_id="9"
        )
    executor.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_phase_field_parallel_phase_fetches_resolve_slug():
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
    service, executor = _make_service_with_pipe(
        {
            "updatePhaseField": {
                "phase_field": {"id": "priority", "label": "P", "type": "select"},
            },
        },
        pipe_svc,
    )
    await service.update_phase_field(
        UpdatePhaseFieldInput(id="priority", label="P"), pipe_id="1"
    )
    assert pipe_svc.get_phase_fields.await_count == 3
    _q, variables = executor.execute_query.call_args[0]
    assert variables == {
        "input": {
            "id": "priority",
            "uuid": "fffffff7-7777-7777-7777-777777777777",
            "label": "P",
        }
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_phase_field_slug_raises_when_any_phase_fetch_fails():
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
    service, executor = _make_service_with_pipe({}, pipe_svc)
    executor.execute_query = AsyncMock()
    with pytest.raises(ValueError, match="Could not load fields"):
        await service.update_phase_field(
            UpdatePhaseFieldInput(id="priority", label="L"), pipe_id="9"
        )
    executor.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_phase_field_slug_raises_when_zero_matches_and_partial_failure():
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
    service, executor = _make_service_with_pipe({}, pipe_svc)
    executor.execute_query = AsyncMock()
    with pytest.raises(ValueError, match="Could not load fields"):
        await service.update_phase_field(
            UpdatePhaseFieldInput(id="missing_slug", label="L"), pipe_id="9"
        )
    executor.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_phase_field_sends_delete_input():
    service, executor = _make_service({"deletePhaseField": {"success": True}})
    result = await service.delete_phase_field(99)

    query, variables = executor.execute_query.call_args[0]
    assert query is DELETE_PHASE_FIELD_MUTATION
    assert variables == {"input": {"id": "99"}}
    assert result == {"deletePhaseField": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_phase_field_accepts_string_slug():
    service, executor = _make_service({"deletePhaseField": {"success": True}})
    result = await service.delete_phase_field("prioridade")

    _query, variables = executor.execute_query.call_args[0]
    assert variables == {"input": {"id": "prioridade"}}
    assert result == {"deletePhaseField": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_phase_field_includes_pipe_uuid_when_provided():
    service, executor = _make_service({"deletePhaseField": {"success": True}})
    result = await service.delete_phase_field(
        "prioridade", pipe_uuid="b3bba313-6b99-44dc-b17e-f192dc00bb21"
    )

    _query, variables = executor.execute_query.call_args[0]
    assert variables == {
        "input": {
            "id": "prioridade",
            "pipeUuid": "b3bba313-6b99-44dc-b17e-f192dc00bb21",
        },
    }
    assert result == {"deletePhaseField": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_label_sends_pipe_name_color():
    service, executor = _make_service(
        {"createLabel": {"label": {"id": "1", "name": "Bug", "color": "#FF0000"}}},
    )
    result = await service.create_label(20, "Bug", "#FF0000")

    query, variables = executor.execute_query.call_args[0]
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
async def test_create_label_normalizes_color(raw_color, normalized_color):
    service, executor = _make_service({"createLabel": {"label": {"id": "1"}}})
    await service.create_label(20, "Bug", raw_color)

    variables = executor.execute_query.call_args[0][1]
    assert variables["input"]["color"] == normalized_color


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_label_rejects_non_hex_color():
    service, executor = _make_service({})

    with pytest.raises(ValueError, match="expected #RGB or #RRGGBB hex color"):
        await service.create_label(20, "Bug", "red")

    executor.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_label_normalizes_color():
    service, executor = _make_service({"updateLabel": {"label": {"id": "2"}}})
    await service.update_label(UpdateLabelInput(id="2", name="Feature", color="#abc"))

    variables = executor.execute_query.call_args[0][1]
    assert variables["input"]["color"] == "#AABBCC"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_label_rejects_non_hex_color():
    service, executor = _make_service({})

    with pytest.raises(ValueError, match="expected #RGB or #RRGGBB hex color"):
        await service.update_label(
            UpdateLabelInput(id="2", name="Feature", color="blue")
        )

    executor.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_label_sends_the_whole_input():
    service, executor = _make_service(
        {"updateLabel": {"label": {"id": "2", "name": "Feature", "color": "blue"}}},
    )
    result = await service.update_label(
        UpdateLabelInput(id="2", name="Feature", color="#abcdef")
    )

    query, variables = executor.execute_query.call_args[0]
    assert query is UPDATE_LABEL_MUTATION
    assert variables == {"input": {"id": "2", "name": "Feature", "color": "#ABCDEF"}}
    assert result == {
        "updateLabel": {"label": {"id": "2", "name": "Feature", "color": "blue"}},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_label_sends_delete_input():
    service, executor = _make_service({"deleteLabel": {"success": True}})
    result = await service.delete_label(3)

    query, variables = executor.execute_query.call_args[0]
    assert query is DELETE_LABEL_MUTATION
    assert variables == {"input": {"id": "3"}}
    assert result == {"deleteLabel": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipe_propagates_execute_query_errors():
    executor = mock_executor(side_effect=RuntimeError("upstream"))
    service = PipeConfigService(executor=executor, pipe_service=AsyncMock())

    with pytest.raises(RuntimeError, match="upstream"):
        await service.create_pipe("X", 1)

    executor.execute_query.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_field_condition_success():
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
    service, executor = _make_service(
        {
            "createFieldCondition": {
                "fieldCondition": {"id": "cond-1"},
            },
        },
    )
    result = await service.create_field_condition(
        CreateFieldConditionInput(
            phaseId="99",
            condition=expr,
            actions=act,
            name="Rule A",
            index=None,
        )
    )

    query, variables = executor.execute_query.call_args[0]
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
async def test_create_field_condition_normalizes_actions_and_condition():
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
    service, executor = _make_service(
        {"createFieldCondition": {"fieldCondition": {"id": "cond-norm"}}},
    )

    await service.create_field_condition(
        CreateFieldConditionInput(
            phaseId="99", condition=expr, actions=actions, name="R"
        )
    )

    _, variables = executor.execute_query.call_args[0]
    payload = variables["input"]
    assert payload["condition"]["expressions"][0].get("id") is None
    assert payload["condition"]["expressions"][0]["structure_id"] == 0
    assert payload["condition"]["expressions_structure"] == [[0]]
    assert payload["actions"][0]["actionId"] == "hide"
    # The caller's own dicts are untouched by the normalization.
    assert actions[0]["actionId"] == "hidden"
    assert expr["expressions_structure"] == [["0"]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_field_condition_takes_the_phase_from_the_input():
    """``phaseId`` is a field of the input, so there is no second source to disagree with it.

    The service used to take ``phase_id`` positionally and reject a ``phaseId``
    passed through ``**attrs``. One typed input leaves nothing to reconcile.
    """
    service, executor = _make_service(
        {"createFieldCondition": {"fieldCondition": {"id": "x"}}},
    )

    await service.create_field_condition(
        CreateFieldConditionInput(
            phaseId="99",
            condition={"expressions": []},
            actions=[{"phaseFieldId": "1"}],
            name="R",
        )
    )

    _, variables = executor.execute_query.call_args[0]
    assert variables["input"]["phaseId"] == "99"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_field_condition_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "invalid"}]))
    service = PipeConfigService(executor=executor, pipe_service=AsyncMock())
    with pytest.raises(PipefyGraphQLError):
        await service.create_field_condition(
            CreateFieldConditionInput(
                phaseId="pf-1",
                condition={"expressions": []},
                actions=[{"phaseFieldId": "x"}],
            )
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_field_condition_success():
    service, executor = _make_service(
        {
            "updateFieldCondition": {
                "fieldCondition": {"id": "cond-2"},
            },
        },
    )
    result = await service.update_field_condition(
        UpdateFieldConditionInput(id="cond-2", name="Updated label")
    )

    query, variables = executor.execute_query.call_args[0]
    assert query is UPDATE_FIELD_CONDITION_MUTATION
    assert variables == {
        "input": {"id": "cond-2", "name": "Updated label"},
    }
    assert result == {
        "updateFieldCondition": {"fieldCondition": {"id": "cond-2"}},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_field_condition_normalizes_actions():
    """Update normalizes ``actions`` (``hidden`` → ``hide``) when provided."""
    service, executor = _make_service(
        {"updateFieldCondition": {"fieldCondition": {"id": "c"}}},
    )

    await service.update_field_condition(
        UpdateFieldConditionInput(
            id="c", actions=[{"phaseFieldId": "1", "actionId": "hidden"}]
        )
    )

    _, variables = executor.execute_query.call_args[0]
    assert variables["input"]["actions"][0]["actionId"] == "hide"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_field_condition_rejects_an_unknown_field():
    """The input is built before the call, so a stray key never reaches the API."""
    service, executor = _make_service(
        {"updateFieldCondition": {"fieldCondition": {"id": "c"}}},
    )

    with pytest.raises(ValidationError):
        UpdateFieldConditionInput(id="c", conditon={"expressions": []})

    executor.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_field_condition_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "not found"}]))
    service = PipeConfigService(executor=executor, pipe_service=AsyncMock())
    with pytest.raises(PipefyGraphQLError):
        await service.update_field_condition(
            UpdateFieldConditionInput(id="missing-id", phase_id="88")
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_field_condition_success():
    service, executor = _make_service({"deleteFieldCondition": {"success": True}})
    result = await service.delete_field_condition("cond-9")

    query, variables = executor.execute_query.call_args[0]
    assert query is DELETE_FIELD_CONDITION_MUTATION
    assert variables == {"input": {"id": "cond-9"}}
    assert result == {"success": True}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_field_condition_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "forbidden"}]))
    service = PipeConfigService(executor=executor, pipe_service=AsyncMock())
    with pytest.raises(PipefyGraphQLError):
        await service.delete_field_condition("cond-x")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_field_conditions_success():
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
    service, executor = _make_service(api_payload)
    result = await service.get_field_conditions(404)

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_FIELD_CONDITIONS_QUERY
    assert "actionId" in print_ast(GET_FIELD_CONDITIONS_QUERY.document)
    assert variables == {"phaseId": "404"}
    assert result == api_payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_field_condition_success():
    api_payload = {
        "fieldCondition": {
            "id": "fc-2",
            "name": "Rule B",
            "phase": {"id": "88", "name": "Form"},
            "condition": {"expressions": []},
            "actions": [{"actionId": "hide", "phaseFieldId": "pf-9"}],
        },
    }
    service, executor = _make_service(api_payload)
    result = await service.get_field_condition("fc-2")

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_FIELD_CONDITION_QUERY
    assert "actionId" in print_ast(GET_FIELD_CONDITION_QUERY.document)
    assert variables == {"id": "fc-2"}
    assert result == api_payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_field_condition_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "not found"}]))
    service = PipeConfigService(executor=executor, pipe_service=AsyncMock())
    with pytest.raises(PipefyGraphQLError):
        await service.get_field_condition("missing")
