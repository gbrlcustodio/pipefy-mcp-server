"""Tests for pipe configuration MCP tools (mocked PipefyClient)."""

import asyncio
from datetime import timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from _mcp_compat import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import PipefyClient, PipefyGraphQLError

from pipefy_mcp.core.tool_error_envelope import tool_error, tool_error_message
from pipefy_mcp.tools.field_condition_tools import FieldConditionTools
from pipefy_mcp.tools.pipe_config_tool_helpers import (
    DeletePipeErrorPayload,
    build_field_condition_delete_payload,
    build_field_condition_success_payload,
    field_condition_phase_field_id_looks_like_slug,
    normalize_phase_allowed_move_targets,
    normalize_phase_cards_list,
)
from pipefy_mcp.tools.pipe_config_tools import PipeConfigTools
from tools.conftest import assert_invalid_arguments_envelope, build_tool_test_server


@pytest.mark.unit
def test_build_field_condition_payload_helpers__no_integration():
    created = build_field_condition_success_payload("c1", "created")
    assert created["success"] is True
    assert created["condition_id"] == "c1"
    assert created["action"] == "created"
    assert "c1" in created["message"]
    assert "verified" not in created
    assert "warning" not in created

    updated = build_field_condition_success_payload("c2", "updated")
    assert updated["action"] == "updated"

    verified = build_field_condition_success_payload("c3", "created", verified=True)
    assert verified["verified"] is True
    assert "warning" not in verified

    warned = build_field_condition_success_payload(
        "c4", "created", warning="could not verify"
    )
    assert warned["warning"] == "could not verify"
    assert "verified" not in warned

    ok_del = build_field_condition_delete_payload(True)
    assert ok_del["success"] is True
    assert ok_del["message"]

    fail_del = build_field_condition_delete_payload(False)
    assert fail_del["success"] is False
    assert fail_del["message"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "looks_like_slug"),
    [
        ("308821043", False),
        ("my_custom_field", True),
        (99, False),
        ("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11", False),
        ("", False),
        ("___", False),
    ],
)
def test_field_condition_phase_field_id_slug_heuristic__no_integration(
    value, looks_like_slug
):
    assert field_condition_phase_field_id_looks_like_slug(value) is looks_like_slug


@pytest.fixture
def mock_pipe_config_client():
    client = MagicMock(PipefyClient)
    client.create_pipe = AsyncMock()
    client.update_pipe = AsyncMock()
    client.delete_pipe = AsyncMock()
    client.clone_pipe = AsyncMock()
    client.get_pipe = AsyncMock()
    client.create_phase = AsyncMock()
    client.update_phase = AsyncMock()
    client.delete_phase = AsyncMock()
    client.get_phase_fields = AsyncMock(return_value={"fields": []})
    client.create_phase_field = AsyncMock()
    client.update_phase_field = AsyncMock()
    client.delete_phase_field = AsyncMock()
    client.create_label = AsyncMock()
    client.update_label = AsyncMock()
    client.delete_label = AsyncMock()
    client.get_cards = AsyncMock()
    client.get_phase_allowed_move_targets = AsyncMock()
    client.get_phase_cards_count = AsyncMock()
    client.get_phase = AsyncMock()
    client.get_phase_cards = AsyncMock()
    client.create_field_condition = AsyncMock()
    client.update_field_condition = AsyncMock()
    client.delete_field_condition = AsyncMock()
    client.get_field_conditions = AsyncMock()
    client.get_field_condition = AsyncMock()
    client.get_automations = AsyncMock()
    client.get_automation = AsyncMock()
    return client


@pytest.fixture
def pipe_config_mcp_server(mock_pipe_config_client):
    mcp = build_tool_test_server(
        "Pipe Config Tools Test",
        PipeConfigTools.register,
        mock_pipe_config_client,
    )
    FieldConditionTools.register(mcp)
    return mcp


@pytest.fixture
def pipe_config_session(pipe_config_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        pipe_config_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
async def test_create_pipe_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_pipe.return_value = {
        "createPipe": {"pipe": {"id": "1", "name": "N"}}
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_pipe",
            {"name": "N", "organization_id": 10},
        )

    assert result.is_error is False
    mock_pipe_config_client.create_pipe.assert_awaited_once_with("N", "10")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "createPipe" in payload["result"]


@pytest.mark.anyio
async def test_create_pipe_rejects_blank_name(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_pipe",
            {"name": "  ", "organization_id": 1},
        )
    mock_pipe_config_client.create_pipe.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False


@pytest.mark.anyio
async def test_update_pipe_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_pipe.return_value = {
        "updatePipe": {"pipe": {"id": "2", "name": "X"}}
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_pipe",
            {"pipe_id": 2, "name": "X"},
        )

    assert result.is_error is False
    mock_pipe_config_client.update_pipe.assert_awaited_once_with(
        "2", name="X", icon=None, color=None, preferences=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
async def test_update_pipe_requires_at_least_one_field(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_pipe",
            {"pipe_id": 1},
        )
    mock_pipe_config_client.update_pipe.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False


@pytest.mark.anyio
async def test_delete_pipe_preview_does_not_delete(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_pipe.return_value = {
        "pipe": {"id": "9", "name": "P1", "phases": []},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_pipe",
            {"pipe_id": 9},
        )

    assert result.is_error is False
    mock_pipe_config_client.get_pipe.assert_awaited_once_with("9")
    mock_pipe_config_client.delete_pipe.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True


@pytest.mark.anyio
async def test_delete_pipe_confirm_calls_mutation(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_pipe.return_value = {
        "pipe": {"id": "9", "name": "P1", "phases": []},
    }
    mock_pipe_config_client.delete_pipe.return_value = {"deletePipe": {"success": True}}

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_pipe",
            {"pipe_id": 9, "confirm": True},
        )

    assert result.is_error is False
    mock_pipe_config_client.delete_pipe.assert_awaited_once_with("9")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["pipe_id"] == "9"


@pytest.mark.anyio
async def test_delete_pipe_invalid_id(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_pipe",
            {"pipe_id": 0, "confirm": True},
        )
    mock_pipe_config_client.get_pipe.assert_not_called()
    payload = extract_payload(result)
    expected = cast(
        DeletePipeErrorPayload,
        tool_error("Invalid 'pipe_id': provide a positive integer."),
    )
    assert payload == expected


@pytest.mark.anyio
async def test_delete_pipe_maps_not_found_on_get_pipe(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    error = PipefyGraphQLError(
        [
            {
                "message": "Pipe not found",
                "extensions": {"code": "RESOURCE_NOT_FOUND"},
            }
        ]
    )
    mock_pipe_config_client.get_pipe.side_effect = error

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_pipe",
            {"pipe_id": 999, "confirm": True},
        )

    mock_pipe_config_client.delete_pipe.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_clone_pipe_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.clone_pipe.return_value = {
        "clonePipes": {"pipes": [{"id": "3", "name": "C"}]},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "clone_pipe",
            {"pipe_template_id": 100},
        )

    mock_pipe_config_client.clone_pipe.assert_awaited_once_with(
        "100", organization_id=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
async def test_create_phase_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_phase.return_value = {
        "createPhase": {"phase": {"id": "10", "name": "Todo", "done": False}},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_phase",
            {"pipe_id": 1, "name": "Todo", "done": False, "index": 1},
        )

    assert result.is_error is False
    mock_pipe_config_client.create_phase.assert_awaited_once_with(
        "1",
        "Todo",
        done=False,
        index=1,
        description=None,
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
async def test_update_phase_with_explicit_name(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_phase.return_value = {
        "updatePhase": {"phase": {"id": "10", "name": "New", "done": False}},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_phase",
            {"phase_id": 10, "name": "New"},
        )

    mock_pipe_config_client.get_phase_fields.assert_not_called()
    mock_pipe_config_client.update_phase.assert_awaited_once_with(
        "10",
        name="New",
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
async def test_update_phase_resolves_name_from_get_phase_fields(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_phase_fields.return_value = {
        "phase_id": "10",
        "phase_name": "Old",
        "fields": [{"id": "f1"}],
    }
    mock_pipe_config_client.update_phase.return_value = {
        "updatePhase": {"phase": {"id": "10", "name": "Old", "done": True}},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_phase",
            {"phase_id": 10, "done": True},
        )

    mock_pipe_config_client.get_phase_fields.assert_awaited_once_with("10")
    mock_pipe_config_client.update_phase.assert_awaited_once_with(
        "10",
        name="Old",
        done=True,
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_update_phase_requires_at_least_one_attr(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_phase",
            {"phase_id": 10},
        )
    mock_pipe_config_client.update_phase.assert_not_called()
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
async def test_delete_phase_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_phase.return_value = {
        "deletePhase": {"success": True},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase", {"phase_id": 55, "confirm": True}
        )

    mock_pipe_config_client.delete_phase.assert_awaited_once_with("55")
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_delete_phase_preview_does_not_delete(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool("delete_phase", {"phase_id": 55})

    assert result.is_error is False
    mock_pipe_config_client.delete_phase.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert payload["resource"] == "phase (ID: 55)"
    assert "⚠️" in payload["message"]
    assert "confirm=True" in payload["message"]


@pytest.mark.anyio
async def test_delete_phase_without_pipe_id_skips_dependent_lookups(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase", {"phase_id": 55, "confirm": False}
        )

    assert extract_payload(result)["success"] is False
    mock_pipe_config_client.get_field_conditions.assert_not_called()
    mock_pipe_config_client.get_automations.assert_not_called()
    mock_pipe_config_client.get_phase_cards_count.assert_not_called()
    mock_pipe_config_client.get_automation.assert_not_called()
    mock_pipe_config_client.get_phase_fields.assert_not_called()


@pytest.mark.anyio
async def test_delete_phase_confirm_true_skips_dependent_lookups(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_phase.return_value = {
        "deletePhase": {"success": True},
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase",
            {"phase_id": 55, "pipe_id": 1, "confirm": True},
        )
    assert extract_payload(result)["success"] is True
    mock_pipe_config_client.get_field_conditions.assert_not_called()
    mock_pipe_config_client.get_automations.assert_not_called()
    mock_pipe_config_client.get_phase_cards_count.assert_not_called()
    mock_pipe_config_client.get_automation.assert_not_called()
    mock_pipe_config_client.get_phase_fields.assert_not_called()


@pytest.mark.anyio
async def test_delete_phase_preview_all_sublookups_succeed(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_field_conditions.return_value = {
        "phase": {
            "fieldConditions": [
                {"id": "c1", "name": "Cond A", "actions": []},
            ]
        }
    }
    mock_pipe_config_client.get_automations.return_value = [
        {"id": "a1", "name": "Move to phase", "active": True, "action_id": "x"},
    ]
    mock_pipe_config_client.get_automation.return_value = {
        "id": "a1",
        "name": "Move to phase",
        "event_params": {"to_phase_id": "55"},
    }
    mock_pipe_config_client.get_phase_cards_count.return_value = 2
    mock_pipe_config_client.get_phase_fields.return_value = {
        "fields": [
            {"id": "f1", "label": "A"},
            {"id": "f2", "label": "B"},
        ],
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase",
            {"phase_id": 55, "pipe_id": 1, "confirm": False},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    deps = payload.get("dependents")
    assert deps is not None
    assert len(deps["field_conditions"]) == 1
    assert deps["field_conditions"][0]["id"] == "c1"
    assert len(deps["automations"]) == 1
    assert deps["automations"][0]["id"] == "a1"
    assert deps["cards_count"] == 2
    assert deps["phase_fields_count"] == 2
    assert "hint" in deps
    assert "2 card(s)" in deps["hint"]
    assert "irreversible" in deps["hint"]
    # Pin the cheap-count contract: native scalar, zero card enumeration.
    mock_pipe_config_client.get_phase_cards_count.assert_awaited_once_with("55")
    mock_pipe_config_client.get_cards.assert_not_called()


@pytest.mark.anyio
async def test_delete_phase_preview_partial_failure_automations_raises(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_field_conditions.return_value = {
        "phase": {
            "fieldConditions": [
                {"id": "c1", "name": "Cond A", "actions": []},
            ]
        }
    }
    mock_pipe_config_client.get_automations.side_effect = PipefyGraphQLError(
        [{"message": "Internal"}]
    )
    mock_pipe_config_client.get_phase_cards_count.return_value = 1
    mock_pipe_config_client.get_phase_fields.return_value = {
        "fields": [{"id": "f1"}],
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase",
            {"phase_id": 55, "pipe_id": 1, "confirm": False},
        )
    payload = extract_payload(result)
    deps = payload.get("dependents")
    assert deps is not None
    assert "automations" not in deps
    assert len(deps["field_conditions"]) == 1
    assert deps["cards_count"] == 1
    assert deps["phase_fields_count"] == 1
    hint = deps.get("hint", "")
    assert "1 card(s)" in hint
    assert "automation" not in hint


@pytest.mark.anyio
async def test_delete_phase_preview_all_sublookups_fail(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    err = PipefyGraphQLError([{"message": "x"}])
    mock_pipe_config_client.get_field_conditions.side_effect = err
    mock_pipe_config_client.get_automations.side_effect = err
    mock_pipe_config_client.get_phase_cards_count.side_effect = err
    mock_pipe_config_client.get_phase_fields.side_effect = err
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase",
            {"phase_id": 55, "pipe_id": 1, "confirm": False},
        )
    assert "dependents" not in extract_payload(result)


@pytest.mark.anyio
async def test_delete_phase_sublookups_run_in_parallel(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    """All four sub-lookups must be in flight at once, not awaited serially.

    Each mock blocks on a shared four-party barrier, so a parallel ``gather``
    releases it while a serial rewrite deadlocks at the first lookup; ``wait_for``
    turns that deadlock into a clean failure. It is four because ``get_automations``
    returns ``[]``, so the inner per-automation gather never adds a fifth party.
    """
    barrier = asyncio.Barrier(4)

    def _rendezvous(value):
        async def _side_effect(*_a, **_kw):
            await barrier.wait()
            return value

        return _side_effect

    mock_pipe_config_client.get_field_conditions.side_effect = _rendezvous(
        {"phase": {"fieldConditions": []}}
    )
    mock_pipe_config_client.get_automations.side_effect = _rendezvous([])
    mock_pipe_config_client.get_phase_cards_count.side_effect = _rendezvous(0)
    mock_pipe_config_client.get_phase_fields.side_effect = _rendezvous({"fields": []})

    async with pipe_config_session as session:
        result = await asyncio.wait_for(
            session.call_tool(
                "delete_phase",
                {"phase_id": 55, "pipe_id": 1, "confirm": False},
            ),
            timeout=5.0,
        )
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
async def test_delete_phase_cards_not_enumerated(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_field_conditions.return_value = {
        "phase": {"fieldConditions": []}
    }
    mock_pipe_config_client.get_automations.return_value = []
    mock_pipe_config_client.get_phase_cards_count.return_value = 3
    mock_pipe_config_client.get_phase_fields.return_value = {"fields": []}
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase",
            {"phase_id": 55, "pipe_id": 1, "confirm": False},
        )
    deps = extract_payload(result).get("dependents")
    assert deps is not None
    assert "cards" not in deps
    assert deps.get("cards_count") == 3
    assert isinstance(deps.get("cards_count"), int)
    # Cheap path: native scalar, no get_cards enumeration.
    mock_pipe_config_client.get_cards.assert_not_called()


@pytest.mark.anyio
async def test_create_phase_field_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_phase_field.return_value = {
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

    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_phase_field",
            {
                "phase_id": 1,
                "label": "Email",
                "field_type": "email",
                "description": "Contact",
            },
        )

    mock_pipe_config_client.create_phase_field.assert_awaited_once_with(
        "1",
        "Email",
        "email",
        description="Contact",
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
async def test_create_phase_field_with_options(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_phase_field.return_value = {
        "createPhaseField": {
            "phase_field": {
                "id": "prioridade",
                "internal_id": "427957330",
                "uuid": "c1d2e3f4-5678-9abc-def0-123456789abc",
                "label": "Prioridade",
                "type": "select",
            },
        },
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_phase_field",
            {
                "phase_id": 1,
                "label": "Prioridade",
                "field_type": "select",
                "options": ["Alta", "Média", "Baixa"],
            },
        )

    mock_pipe_config_client.create_phase_field.assert_awaited_once_with(
        "1",
        "Prioridade",
        "select",
        options=["Alta", "Média", "Baixa"],
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_update_phase_field_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_phase_field.return_value = {
        "updatePhaseField": {
            "phase_field": {"id": "9", "label": "Renamed", "type": "short_text"},
        },
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_phase_field",
            {"field_id": 9, "label": "Renamed"},
        )

    mock_pipe_config_client.update_phase_field.assert_awaited_once_with(
        "9",
        label="Renamed",
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_update_phase_field_success_with_string_slug(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_phase_field.return_value = {
        "updatePhaseField": {
            "phase_field": {
                "id": "detalhe_mcp",
                "label": "Renamed",
                "type": "short_text",
            },
        },
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_phase_field",
            {"field_id": "detalhe_mcp", "label": "Renamed"},
        )

    mock_pipe_config_client.update_phase_field.assert_awaited_once_with(
        "detalhe_mcp",
        label="Renamed",
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_update_phase_field_with_uuid_for_disambiguation(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_phase_field.return_value = {
        "updatePhaseField": {
            "phase_field": {
                "id": "prioridade",
                "label": "Nível de Urgência",
                "type": "select",
            },
        },
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_phase_field",
            {
                "field_id": "prioridade",
                "label": "Nível de Urgência",
                "uuid": "a796cc44-6568-4bfb-9c09-2b903eb7bff2",
            },
        )

    mock_pipe_config_client.update_phase_field.assert_awaited_once_with(
        "prioridade",
        label="Nível de Urgência",
        uuid="a796cc44-6568-4bfb-9c09-2b903eb7bff2",
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_update_phase_field_rejects_blank_label(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_phase_field",
            {"field_id": 9, "label": "   "},
        )
    mock_pipe_config_client.update_phase_field.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "label" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_delete_phase_field_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_phase_field.return_value = {
        "deletePhaseField": {"success": True},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase_field",
            {"field_id": 100, "confirm": True},
        )

    mock_pipe_config_client.delete_phase_field.assert_awaited_once_with(
        "100", pipe_uuid=None
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_delete_phase_field_preview_does_not_delete(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool("delete_phase_field", {"field_id": 100})

    assert result.is_error is False
    mock_pipe_config_client.delete_phase_field.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert payload["resource"] == "phase field (ID: 100)"
    assert "⚠️" in payload["message"]
    assert "confirm=True" in payload["message"]


@pytest.mark.anyio
async def test_delete_phase_field_preview_lists_dependent_conditions(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_phase_fields.return_value = {
        "fields": [
            {
                "id": "my_field",
                "internal_id": "308821043",
                "uuid": "aaa-bbb-ccc",
            }
        ]
    }
    mock_pipe_config_client.get_field_conditions.return_value = {
        "phase": {
            "fieldConditions": [
                {
                    "id": "cond-1",
                    "name": "Show when X",
                    "actions": [{"phaseFieldId": "308821043"}],
                }
            ]
        }
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase_field",
            {"field_id": "my_field", "phase_id": 50, "confirm": False},
        )

    mock_pipe_config_client.delete_phase_field.assert_not_called()
    mock_pipe_config_client.get_phase_fields.assert_awaited_once_with("50")
    mock_pipe_config_client.get_field_conditions.assert_awaited_once_with("50")
    payload = extract_payload(result)
    assert payload["success"] is False
    deps = payload.get("dependents")
    assert deps is not None
    assert len(deps["field_conditions"]) == 1
    assert deps["field_conditions"][0]["id"] == "cond-1"
    assert deps["field_conditions"][0]["name"] == "Show when X"
    assert deps["field_conditions"][0]["action_count"] == 1
    assert "delete_field_condition" in deps["hint"]


# delete_phase_field preview — expression-only field condition dependents
@pytest.mark.anyio
async def test_delete_phase_field_preview_includes_conditions_with_expression_only_refs(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    """Rule references ``priority`` in condition expressions.

    ``find_phase_field_dependents`` must treat expression ``field_address`` as a
    dependency, not only ``actions[].phaseFieldId``. Preview must list
    ``dependents.field_conditions`` when the field appears only in the rule
    ``when`` expression (actions may target a different field).
    """
    pipe_uuid = "bddc2aff-9c0b-4ef8-bb6d-6bb9bd380a11"
    phase_id = 343162749
    mock_pipe_config_client.get_phase_fields.return_value = {
        "fields": [
            {
                "id": "priority",
                "internal_id": "429358624",
                "uuid": pipe_uuid,
            },
            {
                "id": "detail",
                "internal_id": "429358625",
                "uuid": "c0ffee00-9c0b-4ef8-bb6d-6bb9bd380a11",
            },
        ]
    }
    mock_pipe_config_client.get_field_conditions.return_value = {
        "phase": {
            "fieldConditions": [
                {
                    "id": "306743895",
                    "name": "When priority is Alta hide detail",
                    "condition": {
                        "expressions": [
                            {
                                "field_address": "429358624",
                                "operation": "equals",
                                "value": "Alta",
                            }
                        ]
                    },
                    "actions": [{"phaseFieldId": "429358625"}],
                }
            ]
        }
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase_field",
            {
                "field_id": "priority",
                "phase_id": phase_id,
                "pipe_uuid": pipe_uuid,
                "confirm": False,
            },
        )

    mock_pipe_config_client.delete_phase_field.assert_not_called()
    mock_pipe_config_client.get_phase_fields.assert_awaited_once_with(str(phase_id))
    mock_pipe_config_client.get_field_conditions.assert_awaited_once_with(str(phase_id))
    payload = extract_payload(result)
    assert payload["success"] is False
    deps = payload.get("dependents")
    assert deps is not None
    fcs = deps.get("field_conditions") or []
    assert len(fcs) >= 1
    assert any(c.get("id") == "306743895" for c in fcs)


@pytest.mark.anyio
async def test_delete_phase_field_preview_no_deps_unchanged(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_phase_fields.return_value = {
        "fields": [
            {
                "id": "my_field",
                "internal_id": "308821043",
                "uuid": "aaa-bbb-ccc",
            }
        ]
    }
    mock_pipe_config_client.get_field_conditions.return_value = {
        "phase": {"fieldConditions": []}
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase_field",
            {"field_id": "my_field", "phase_id": 50, "confirm": False},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "dependents" not in payload


@pytest.mark.anyio
async def test_delete_phase_field_no_phase_id_skips_enrichment(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase_field",
            {"field_id": 100, "confirm": False},
        )

    mock_pipe_config_client.get_field_conditions.assert_not_called()
    mock_pipe_config_client.get_phase_fields.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "dependents" not in payload


@pytest.mark.anyio
async def test_delete_phase_field_identifier_match_by_uuid(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_phase_fields.return_value = {
        "fields": [
            {
                "id": "other_slug",
                "internal_id": "999999999",
                "uuid": "match-uuid-001",
            }
        ]
    }
    mock_pipe_config_client.get_field_conditions.return_value = {
        "phase": {
            "fieldConditions": [
                {
                    "id": "c-uuid",
                    "name": "By uuid",
                    "actions": [{"phaseFieldId": "match-uuid-001"}],
                }
            ]
        }
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase_field",
            {
                "field_id": "match-uuid-001",
                "phase_id": 50,
                "confirm": False,
            },
        )

    payload = extract_payload(result)
    deps = payload.get("dependents")
    assert deps is not None
    assert deps["field_conditions"][0]["id"] == "c-uuid"


@pytest.mark.anyio
async def test_delete_phase_field_enrichment_failure_degrades_gracefully(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_phase_fields.return_value = {
        "fields": [
            {"id": "f1", "internal_id": "1", "uuid": "u1"},
        ]
    }
    mock_pipe_config_client.get_field_conditions.side_effect = PipefyGraphQLError(
        [{"message": "Permission denied"}]
    )

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase_field",
            {"field_id": "f1", "phase_id": 50, "confirm": False},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "dependents" not in payload


@pytest.mark.anyio
async def test_delete_phase_field_confirm_true_skips_enrichment(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_phase_field.return_value = {
        "deletePhaseField": {"success": True},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase_field",
            {"field_id": 100, "phase_id": 50, "confirm": True},
        )

    mock_pipe_config_client.get_field_conditions.assert_not_called()
    mock_pipe_config_client.get_phase_fields.assert_not_called()
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_delete_phase_field_success_with_string_slug(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_phase_field.return_value = {
        "deletePhaseField": {"success": True},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase_field",
            {"field_id": "detalhe_mcp", "confirm": True},
        )

    mock_pipe_config_client.delete_phase_field.assert_awaited_once_with(
        "detalhe_mcp", pipe_uuid=None
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_create_label_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_label.return_value = {
        "createLabel": {"label": {"id": "1", "name": "Bug", "color": "#FF0000"}},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_label",
            {"pipe_id": 2, "name": "Bug", "color": "#FF0000"},
        )

    mock_pipe_config_client.create_label.assert_awaited_once_with("2", "Bug", "#FF0000")
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_update_label_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_label.return_value = {
        "updateLabel": {"label": {"id": "3", "name": "Story", "color": "#0000FF"}},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_label",
            {"label_id": 3, "name": "Story", "color": "#0000FF"},
        )

    mock_pipe_config_client.update_label.assert_awaited_once_with(
        "3", name="Story", color="#0000FF"
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_update_label_strips_id_from_extra_input__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_label.return_value = {
        "updateLabel": {"label": {"id": "3", "name": "X", "color": "#0000FF"}},
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_label",
            {
                "label_id": 3,
                "name": "X",
                "color": "#0000FF",
                "extra_input": {"id": 999},
            },
        )
    mock_pipe_config_client.update_label.assert_awaited_once_with(
        "3",
        name="X",
        color="#0000FF",
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_update_label_missing_color_rejected_at_tool_boundary(
    pipe_config_session, mock_pipe_config_client
):
    """Pipefy's ``UpdateLabelInput`` declares name and color NON_NULL;
    omitting either raises a protocol-level validation error before the
    tool body runs, so the mutation is never called."""
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_label",
            {"label_id": 3, "name": "Story"},
        )
    mock_pipe_config_client.update_label.assert_not_called()
    assert_invalid_arguments_envelope(result)


@pytest.mark.anyio
async def test_update_label_empty_color_returns_error(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_label",
            {"label_id": 3, "name": "Story", "color": "   "},
        )
    mock_pipe_config_client.update_label.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "color" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_delete_label_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_label.return_value = {
        "deleteLabel": {"success": True},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_label", {"label_id": 40, "confirm": True}
        )

    mock_pipe_config_client.delete_label.assert_awaited_once_with("40")
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_delete_label_preview_does_not_delete(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool("delete_label", {"label_id": 40})

    assert result.is_error is False
    mock_pipe_config_client.delete_label.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert payload["resource"] == "label (ID: 40)"
    assert "⚠️" in payload["message"]
    assert "confirm=True" in payload["message"]


@pytest.mark.anyio
async def test_delete_label_preview_with_cards_in_use(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_cards.return_value = {
        "cards": {
            "edges": [{"node": {"id": str(i)}} for i in range(1, 7)],
            "pageInfo": {"hasNextPage": True},
        }
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_label",
            {"label_id": 40, "pipe_id": 2, "confirm": False},
        )

    mock_pipe_config_client.delete_label.assert_not_called()
    mock_pipe_config_client.get_cards.assert_awaited_once()
    call = mock_pipe_config_client.get_cards.await_args
    assert call.args[0] == "2"
    assert call.kwargs["first"] == 6
    assert call.args[1]["label_ids"] == ["40"]

    payload = extract_payload(result)
    deps = payload.get("dependents")
    assert deps is not None
    cul = deps["cards_using_label"]
    assert cul["sample_size"] == 5
    assert cul["sample_cap"] == 5
    assert cul["has_more"] is True
    assert len(cul["sample_card_ids"]) == 5
    assert cul["sample_card_ids"][0] == "1"
    assert "More than 5 card(s)" in deps["hint"]
    assert "Proceed if that is intended" in deps["hint"]


@pytest.mark.anyio
async def test_delete_label_preview_partial_sample_reports_actual_count(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    """3 cards in use — hint must say `3 card(s)`, not the cap `5`."""
    mock_pipe_config_client.get_cards.return_value = {
        "cards": {
            "edges": [{"node": {"id": str(i)}} for i in range(1, 4)],
            "pageInfo": {"hasNextPage": False},
        }
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_label",
            {"label_id": 40, "pipe_id": 2, "confirm": False},
        )

    payload = extract_payload(result)
    deps = payload.get("dependents")
    assert deps is not None
    cul = deps["cards_using_label"]
    assert cul["sample_size"] == 3
    assert cul["sample_cap"] == 5
    assert cul["has_more"] is False
    assert cul["sample_card_ids"] == ["1", "2", "3"]
    assert "3 card(s)" in deps["hint"]
    assert "More than" not in deps["hint"]


@pytest.mark.anyio
async def test_delete_label_preview_unused_label_no_dependents(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_cards.return_value = {
        "cards": {"edges": [], "pageInfo": {"hasNextPage": False}}
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_label",
            {"label_id": 40, "pipe_id": 2, "confirm": False},
        )

    payload = extract_payload(result)
    assert "dependents" not in payload


@pytest.mark.anyio
async def test_delete_label_preview_get_cards_fails_degrades(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_cards.side_effect = PipefyGraphQLError(
        [{"message": "Forbidden"}]
    )

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_label",
            {"label_id": 40, "pipe_id": 2, "confirm": False},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "dependents" not in payload


@pytest.mark.anyio
async def test_delete_label_confirm_true_skips_resolver(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_label.return_value = {
        "deleteLabel": {"success": True},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_label",
            {"label_id": 40, "pipe_id": 2, "confirm": True},
        )

    mock_pipe_config_client.get_cards.assert_not_called()
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_delete_label_preview_without_pipe_id_skips_cards_lookup(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_label",
            {"label_id": 40, "confirm": False},
        )

    mock_pipe_config_client.get_cards.assert_not_called()
    assert "dependents" not in extract_payload(result)


@pytest.mark.anyio
async def test_create_pipe_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_pipe.side_effect = PipefyGraphQLError(
        [{"message": "Organization not found"}]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_pipe",
            {"name": "Test", "organization_id": 999},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Organization not found" in tool_error_message(payload)


@pytest.mark.anyio
async def test_update_pipe_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_pipe.side_effect = PipefyGraphQLError(
        [{"message": "Pipe locked"}]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_pipe",
            {"pipe_id": 1, "name": "X"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Pipe locked" in tool_error_message(payload)


@pytest.mark.anyio
async def test_clone_pipe_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.clone_pipe.side_effect = PipefyGraphQLError(
        [{"message": "Template missing"}]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "clone_pipe",
            {"pipe_template_id": 1},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Template missing" in tool_error_message(payload)


@pytest.mark.anyio
async def test_create_phase_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_phase.side_effect = PipefyGraphQLError(
        [{"message": "Pipe not found"}]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_phase",
            {"pipe_id": 1, "name": "A"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Pipe not found" in tool_error_message(payload)


@pytest.mark.anyio
async def test_update_phase_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_phase.side_effect = PipefyGraphQLError(
        [{"message": "Phase invalid"}]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_phase",
            {"phase_id": 10, "name": "N"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Phase invalid" in tool_error_message(payload)


@pytest.mark.anyio
async def test_update_phase_get_phase_fields_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_phase_fields.side_effect = PipefyGraphQLError(
        [{"message": "Forbidden"}]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_phase",
            {"phase_id": 10, "done": True},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Forbidden" in tool_error_message(payload)


@pytest.mark.anyio
async def test_delete_phase_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_phase.side_effect = PipefyGraphQLError(
        [{"message": "Cannot delete"}]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase", {"phase_id": 1, "confirm": True}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Cannot delete" in tool_error_message(payload)


@pytest.mark.anyio
async def test_create_phase_field_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_phase_field.side_effect = PipefyGraphQLError(
        [{"message": "Invalid type"}]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_phase_field",
            {"phase_id": 1, "label": "L", "field_type": "email"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Invalid type" in tool_error_message(payload)


@pytest.mark.anyio
async def test_update_phase_field_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_phase_field.side_effect = PipefyGraphQLError(
        [{"message": "Field gone"}]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_phase_field",
            {"field_id": 9, "label": "L"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Field gone" in tool_error_message(payload)


@pytest.mark.anyio
async def test_delete_phase_field_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_phase_field.side_effect = PipefyGraphQLError(
        [{"message": "Nope"}]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase_field",
            {"field_id": 100, "confirm": True},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Nope" in tool_error_message(payload)


@pytest.mark.anyio
async def test_delete_phase_field_cascade_diagnosis_with_pipe_id(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    """When the parent phase was deleted earlier in the session, Pipefy returns
    a generic ``INTERNAL_SERVER_ERROR``. With ``pipe_id`` supplied, the tool
    verifies the field is really gone and returns an actionable message
    instead of the opaque upstream error."""
    mock_pipe_config_client.delete_phase_field.side_effect = PipefyGraphQLError(
        [
            {
                "message": "Something went wrong",
                "extensions": {"code": "INTERNAL_SERVER_ERROR"},
            }
        ]
    )
    # After failure, verify path fetches pipe + phases and finds no matching field.
    mock_pipe_config_client.get_pipe.return_value = {
        "pipe": {"id": "77", "phases": [{"id": "700"}, {"id": "701"}]}
    }
    mock_pipe_config_client.get_phase_fields.return_value = {
        "phase_id": "700",
        "fields": [
            {"id": "unrelated_field", "uuid": "xyz"},
        ],
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase_field",
            {
                "field_id": "gone_field",
                "confirm": True,
                "pipe_id": "77",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    msg = tool_error_message(payload)
    assert "no longer exists" in msg
    assert "cascaded" in msg.lower()


@pytest.mark.anyio
async def test_delete_phase_field_cascade_diagnosis_field_still_exists(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    """If the field is still present somewhere, the error is NOT a cascade —
    fall back to the generic upstream error instead of misleading the caller."""
    mock_pipe_config_client.delete_phase_field.side_effect = PipefyGraphQLError(
        [
            {
                "message": "Something went wrong",
                "extensions": {"code": "INTERNAL_SERVER_ERROR"},
            }
        ]
    )
    mock_pipe_config_client.get_pipe.return_value = {
        "pipe": {"id": "77", "phases": [{"id": "700"}]}
    }
    mock_pipe_config_client.get_phase_fields.return_value = {
        "phase_id": "700",
        "fields": [{"id": "still_here", "uuid": "abc"}],
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase_field",
            {
                "field_id": "still_here",
                "confirm": True,
                "pipe_id": "77",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    msg = tool_error_message(payload)
    assert "no longer exists" not in msg


@pytest.mark.anyio
async def test_delete_phase_field_cascade_diagnosis_skipped_without_pipe_id(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    """Without ``pipe_id`` the tool cannot diagnose; it preserves the raw error
    and does NOT perform the extra read-backs."""
    mock_pipe_config_client.delete_phase_field.side_effect = PipefyGraphQLError(
        [
            {
                "message": "Something went wrong",
                "extensions": {"code": "INTERNAL_SERVER_ERROR"},
            }
        ]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase_field",
            {"field_id": "any_field", "confirm": True},
        )
    mock_pipe_config_client.get_pipe.assert_not_called()
    mock_pipe_config_client.get_phase_fields.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False


@pytest.mark.anyio
async def test_create_label_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_label.side_effect = PipefyGraphQLError(
        [{"message": "Bad color"}]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_label",
            {"pipe_id": 2, "name": "Bug", "color": "#FF0000"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Bad color" in tool_error_message(payload)


@pytest.mark.anyio
async def test_update_label_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_label.side_effect = PipefyGraphQLError(
        [{"message": "Label missing"}]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_label",
            {"label_id": 3, "name": "Story", "color": "#0000FF"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Label missing" in tool_error_message(payload)


@pytest.mark.anyio
async def test_delete_label_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_label.side_effect = PipefyGraphQLError(
        [{"message": "Still in use"}]
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_label", {"label_id": 40, "confirm": True}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Still in use" in tool_error_message(payload)


@pytest.mark.anyio
async def test_create_phase_field_strips_reserved_keys_from_extra_input__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_phase_field.return_value = {
        "createPhaseField": {"phase_field": {"id": "f1"}},
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_phase_field",
            {
                "phase_id": 1,
                "label": "Email",
                "field_type": "email",
                "extra_input": {
                    "phase_id": 99,
                    "label": "Shadow",
                    "type": "short_text",
                    "description": "Kept",
                },
            },
        )
    assert extract_payload(result)["success"] is True
    mock_pipe_config_client.create_phase_field.assert_awaited_once_with(
        "1",
        "Email",
        "email",
        description="Kept",
    )


@pytest.mark.anyio
async def test_create_phase_rejects_blank_name__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_phase",
            {"pipe_id": 1, "name": "  "},
        )
    mock_pipe_config_client.create_phase.assert_not_called()
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
async def test_create_label_rejects_blank_color__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_label",
            {"pipe_id": 2, "name": "Bug", "color": "  "},
        )
    mock_pipe_config_client.create_label.assert_not_called()
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (
            "create_label",
            {"pipe_id": 2, "name": "Bug", "color": "red"},
        ),
        (
            "update_label",
            {"label_id": 3, "name": "Story", "color": "blue"},
        ),
    ],
)
async def test_label_color_maps_sdk_value_error__no_integration(
    pipe_config_session,
    mock_pipe_config_client,
    extract_payload,
    tool_name: str,
    arguments: dict[str, object],
):
    rejection = ValueError(
        f"expected #RGB or #RRGGBB hex color, received {arguments['color']!r}"
    )
    mock_pipe_config_client.create_label.side_effect = rejection
    mock_pipe_config_client.update_label.side_effect = rejection
    async with pipe_config_session as session:
        result = await session.call_tool(tool_name, arguments)
    getattr(mock_pipe_config_client, tool_name).assert_awaited_once()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert "expected #RGB or #RRGGBB" in tool_error_message(payload)


@pytest.mark.anyio
async def test_clone_pipe_rejects_invalid_organization_id__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "clone_pipe",
            {"pipe_template_id": 100, "organization_id": 0},
        )
    mock_pipe_config_client.clone_pipe.assert_not_called()
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
async def test_delete_phase_rejects_invalid_id__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool("delete_phase", {"phase_id": 0})
    mock_pipe_config_client.delete_phase.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "requires_confirmation" not in payload


@pytest.mark.anyio
async def test_delete_label_rejects_invalid_id__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool("delete_label", {"label_id": -1})
    mock_pipe_config_client.delete_label.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "requires_confirmation" not in payload


@pytest.mark.anyio
async def test_create_field_condition_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    expr_input = {
        "expressions": [
            {
                "field_address": "a",
                "operation": "equals",
                "value": "1",
                "structure_id": "42",
            }
        ],
        "expressions_structure": [["42"]],
    }
    actions = [{"phaseFieldId": "308821043", "whenEvaluator": True, "actionId": "hide"}]
    mock_pipe_config_client.create_field_condition.return_value = {
        "createFieldCondition": {"fieldCondition": {"id": "cond-new"}},
    }
    mock_pipe_config_client.get_field_condition.return_value = {
        "fieldCondition": {"id": "cond-new", "phase": {"id": "pf-99"}},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {
                "phase_id": "pf-99",
                "condition": expr_input,
                "actions": actions,
                "extra_input": {"name": "R1"},
                "debug": False,
            },
        )

    assert result.is_error is False
    mock_pipe_config_client.create_field_condition.assert_awaited_once_with(
        "pf-99",
        expr_input,
        actions,
        name="R1",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["condition_id"] == "cond-new"
    assert payload["action"] == "created"
    assert payload["verified"] is True


@pytest.mark.anyio
async def test_create_field_condition_slug_like_phase_field_id_carries_invalid_arguments_code(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    """Pre-API arg validation must surface ``error.code = INVALID_ARGUMENTS``.

    A slug-looking ``phaseFieldId`` (e.g. ``"nome_do_campo"``) triggers
    ``field_condition_actions_error_message``
    before any Pipefy call. The envelope must match the shape of coercion
    errors so agents can branch on ``error.code`` consistently.
    """
    expr = {
        "expressions": [{"field_address": "a", "operation": "equals", "value": "1"}],
    }
    # Slug-like phaseFieldId (non-digit) triggers the looks_like_slug check.
    actions = [{"phaseFieldId": "nome_do_campo", "actionId": "hide"}]
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {
                "phase_id": "pf-99",
                "condition": expr,
                "actions": actions,
                "name": "probe-5",
            },
        )

    assert result.is_error is False
    mock_pipe_config_client.create_field_condition.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert "get_phase_fields" in payload["error"]["message"]


@pytest.mark.anyio
async def test_create_field_condition_top_level_name__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    expr = {
        "expressions": [{"field_address": "a", "operation": "equals", "value": "1"}],
    }
    actions = [{"phaseFieldId": "308821043", "actionId": "hide"}]
    mock_pipe_config_client.create_field_condition.return_value = {
        "createFieldCondition": {"fieldCondition": {"id": "cond-top"}},
    }
    mock_pipe_config_client.get_field_condition.return_value = {
        "fieldCondition": {"id": "cond-top", "phase": {"id": "pf-99"}},
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {
                "phase_id": "pf-99",
                "condition": expr,
                "actions": actions,
                "name": "Top-level name",
            },
        )
    assert result.is_error is False
    mock_pipe_config_client.create_field_condition.assert_awaited_once_with(
        "pf-99",
        expr,
        actions,
        name="Top-level name",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["verified"] is True


@pytest.mark.anyio
async def test_create_field_condition_top_level_name_wins_over_extra_input__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    expr = {
        "expressions": [{"field_address": "a", "operation": "equals", "value": "1"}],
    }
    actions = [{"phaseFieldId": "308821043", "actionId": "hide"}]
    mock_pipe_config_client.create_field_condition.return_value = {
        "createFieldCondition": {"fieldCondition": {"id": "cond-win"}},
    }
    mock_pipe_config_client.get_field_condition.return_value = {
        "fieldCondition": {"id": "cond-win", "phase": {"id": "pf-99"}},
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {
                "phase_id": "pf-99",
                "condition": expr,
                "actions": actions,
                "name": "Top wins",
                "extra_input": {"name": "Loser", "index": 3},
            },
        )
    assert result.is_error is False
    mock_pipe_config_client.create_field_condition.assert_awaited_once_with(
        "pf-99",
        expr,
        actions,
        index=3,
        name="Top wins",
    )
    assert extract_payload(result)["verified"] is True


@pytest.mark.anyio
async def test_create_field_condition_rejects_missing_name__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    expr = {
        "expressions": [{"field_address": "a", "operation": "equals", "value": "1"}],
    }
    actions = [{"phaseFieldId": "308821043", "actionId": "hide"}]
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {"phase_id": "pf-99", "condition": expr, "actions": actions},
        )
    mock_pipe_config_client.create_field_condition.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "name" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_create_field_condition_rejects_blank_name__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    expr = {
        "expressions": [{"field_address": "a", "operation": "equals", "value": "1"}],
    }
    actions = [{"phaseFieldId": "308821043", "actionId": "hide"}]
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {
                "phase_id": "pf-99",
                "condition": expr,
                "actions": actions,
                "name": "   ",
            },
        )
    mock_pipe_config_client.create_field_condition.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "name" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_create_field_condition_rejects_empty_condition__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {
                "phase_id": 1,
                "condition": {},
                "actions": [{"phaseFieldId": "123"}],
            },
        )
    mock_pipe_config_client.create_field_condition.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "non-empty" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_create_field_condition_rejects_empty_expressions__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {
                "phase_id": 1,
                "condition": {"expressions": []},
                "actions": [{"phaseFieldId": "123", "actionId": "hide"}],
            },
        )
    mock_pipe_config_client.create_field_condition.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "expressions" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_create_field_condition_rejects_slug_like_phase_field_id__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {
                "phase_id": 1,
                "condition": {
                    "expressions": [
                        {"field_address": "a", "operation": "equals", "value": "1"}
                    ],
                },
                "actions": [{"phaseFieldId": "my_custom_field_slug"}],
            },
        )
    mock_pipe_config_client.create_field_condition.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "internal_id" in tool_error_message(payload)
    assert "get_phase_fields" in tool_error_message(payload)


@pytest.mark.anyio
async def test_create_field_condition_accepts_uuid_phase_field_id__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    uid = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    expr = {
        "expressions": [{"field_address": "a", "operation": "equals", "value": "1"}],
    }
    actions = [{"phaseFieldId": uid}]
    mock_pipe_config_client.create_field_condition.return_value = {
        "createFieldCondition": {"fieldCondition": {"id": "cond-uuid"}},
    }
    mock_pipe_config_client.get_field_condition.return_value = {
        "fieldCondition": {"id": "cond-uuid", "phase": {"id": "1"}},
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {
                "phase_id": 1,
                "condition": expr,
                "actions": actions,
                "name": "R",
            },
        )
    assert result.is_error is False
    mock_pipe_config_client.create_field_condition.assert_awaited_once_with(
        "1",
        expr,
        actions,
        name="R",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["verified"] is True


@pytest.mark.anyio
async def test_create_field_condition_passes_raw_actions_to_sdk__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    """MCP forwards actions verbatim; SDK service normalizes ``hidden`` → ``hide``."""
    expr = {
        "expressions": [{"field_address": "a", "operation": "equals", "value": "1"}]
    }
    actions_in = [
        {"phaseFieldId": "308821043", "whenEvaluator": True, "actionId": "hidden"}
    ]
    mock_pipe_config_client.create_field_condition.return_value = {
        "createFieldCondition": {"fieldCondition": {"id": "cond-x"}},
    }
    mock_pipe_config_client.get_field_condition.return_value = {
        "fieldCondition": {"id": "cond-x", "phase": {"id": "1"}},
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {"phase_id": 1, "condition": expr, "actions": actions_in, "name": "R"},
        )
    assert result.is_error is False
    mock_pipe_config_client.create_field_condition.assert_awaited_once_with(
        "1",
        expr,
        actions_in,
        name="R",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["verified"] is True


@pytest.mark.anyio
async def test_create_field_condition_forwards_condition_to_sdk__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    """MCP forwards condition verbatim; SDK service strips persisted expression ids."""
    expr_with_id = {
        "expressions": [
            {
                "id": "e1",
                "field_address": "a",
                "operation": "equals",
                "value": "1",
                "structure_id": "99",
            }
        ],
        "expressions_structure": [["99"]],
    }
    actions = [{"phaseFieldId": "308821043", "whenEvaluator": True, "actionId": "hide"}]
    mock_pipe_config_client.create_field_condition.return_value = {
        "createFieldCondition": {"fieldCondition": {"id": "cond-stripped"}},
    }
    mock_pipe_config_client.get_field_condition.return_value = {
        "fieldCondition": {"id": "cond-stripped", "phase": {"id": "1"}},
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {
                "phase_id": 1,
                "condition": expr_with_id,
                "actions": actions,
                "name": "R",
            },
        )
    assert result.is_error is False
    mock_pipe_config_client.create_field_condition.assert_awaited_once_with(
        "1",
        expr_with_id,
        actions,
        name="R",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["condition_id"] == "cond-stripped"
    assert payload["verified"] is True


@pytest.mark.anyio
async def test_create_field_condition_error(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_field_condition.side_effect = PipefyGraphQLError(
        [{"message": "Invalid condition"}]
    )
    expr = {
        "expressions": [{"field_address": "a", "operation": "equals", "value": "1"}],
    }
    actions = [{"phaseFieldId": "308821043"}]

    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {
                "phase_id": "pf-1",
                "condition": expr,
                "actions": actions,
                "name": "R",
                "extra_input": None,
                "debug": False,
            },
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Invalid condition" in tool_error_message(payload)


@pytest.mark.anyio
async def test_update_field_condition_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_field_condition.return_value = {
        "updateFieldCondition": {"fieldCondition": {"id": "cond-2"}},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_field_condition",
            {
                "condition_id": "cond-2",
                "extra_input": {"name": "Patched"},
                "debug": False,
            },
        )

    assert result.is_error is False
    mock_pipe_config_client.update_field_condition.assert_awaited_once_with(
        "cond-2",
        name="Patched",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["condition_id"] == "cond-2"
    assert payload["action"] == "updated"


@pytest.mark.anyio
async def test_update_field_condition_success_with_explicit_condition_and_actions(
    pipe_config_session,
    mock_pipe_config_client,
    extract_payload,
):
    mock_pipe_config_client.update_field_condition.return_value = {
        "updateFieldCondition": {"fieldCondition": {"id": "cond-7"}},
    }
    condition_in = {
        "expressions": [{"field_address": "f1", "operation": "equals", "value": "x"}],
    }
    actions_in = [{"phaseFieldId": "308821043", "actionId": "hidden"}]

    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_field_condition",
            {
                "condition_id": "cond-7",
                "condition": condition_in,
                "actions": actions_in,
                "extra_input": {"name": "N7"},
                "debug": False,
            },
        )

    assert result.is_error is False
    mock_pipe_config_client.update_field_condition.assert_awaited_once_with(
        "cond-7",
        name="N7",
        condition=condition_in,
        actions=actions_in,
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_update_field_condition_top_level_name__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_field_condition.return_value = {
        "updateFieldCondition": {"fieldCondition": {"id": "cond-8"}},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_field_condition",
            {"condition_id": "cond-8", "name": "Top name"},
        )

    assert result.is_error is False
    mock_pipe_config_client.update_field_condition.assert_awaited_once_with(
        "cond-8",
        name="Top name",
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
async def test_update_field_condition_rejects_blank_name__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_field_condition",
            {"condition_id": "cond-8", "name": "   "},
        )
    mock_pipe_config_client.update_field_condition.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "name" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_update_field_condition_error(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_field_condition.side_effect = PipefyGraphQLError(
        [{"message": "Not found"}]
    )

    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_field_condition",
            {
                "condition_id": "missing",
                "extra_input": {"phase_id": "88"},
                "debug": False,
            },
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Field condition not found" in tool_error_message(payload)


@pytest.mark.anyio
async def test_delete_field_condition_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_field_condition.return_value = {"success": True}

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_field_condition",
            {"condition_id": "cond-9", "confirm": True},
        )

    assert result.is_error is False
    mock_pipe_config_client.delete_field_condition.assert_awaited_once_with("cond-9")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload.get("message")


@pytest.mark.anyio
async def test_delete_field_condition_error(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_field_condition.side_effect = PipefyGraphQLError(
        [{"message": "Forbidden"}]
    )

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_field_condition",
            {"condition_id": "cond-x", "confirm": True},
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Forbidden" in tool_error_message(payload)


@pytest.mark.unit
def test_normalize_phase_allowed_move_targets__no_integration():
    raw = {
        "phase": {
            "id": "100",
            "name": "Doing",
            "cards_can_be_moved_to_phases": [
                {"id": "200", "name": "Done"},
                {"id": "201", "name": "Blocked"},
            ],
        }
    }
    assert normalize_phase_allowed_move_targets(raw) == {
        "phase_id": "100",
        "phase_name": "Doing",
        "allowed_phases": [
            {"id": "200", "name": "Done"},
            {"id": "201", "name": "Blocked"},
        ],
    }


@pytest.mark.unit
def test_normalize_phase_allowed_move_targets_missing_phase__no_integration():
    assert normalize_phase_allowed_move_targets({}) is None
    assert normalize_phase_allowed_move_targets({"phase": None}) is None


@pytest.mark.anyio
async def test_get_phase_allowed_move_targets_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    phase_id = 342182335
    mock_pipe_config_client.get_phase_allowed_move_targets.return_value = {
        "phase": {
            "id": str(phase_id),
            "name": "Doing",
            "cards_can_be_moved_to_phases": [{"id": "200", "name": "Done"}],
        }
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "get_phase_allowed_move_targets",
            {"phase_id": phase_id},
        )

    assert result.is_error is False
    mock_pipe_config_client.get_phase_allowed_move_targets.assert_awaited_once_with(
        str(phase_id)
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"] == {
        "phase_id": str(phase_id),
        "phase_name": "Doing",
        "allowed_phases": [{"id": "200", "name": "Done"}],
    }


@pytest.mark.anyio
@pytest.mark.parametrize("invalid_phase_id", [0, -1])
async def test_get_phase_allowed_move_targets_rejects_invalid_phase_id(
    pipe_config_session,
    mock_pipe_config_client,
    extract_payload,
    invalid_phase_id,
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "get_phase_allowed_move_targets",
            {"phase_id": invalid_phase_id},
        )
    mock_pipe_config_client.get_phase_allowed_move_targets.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False


@pytest.mark.anyio
async def test_get_phase_allowed_move_targets_not_found(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_phase_allowed_move_targets.return_value = {
        "phase": None
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "get_phase_allowed_move_targets",
            {"phase_id": 999},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_get_phase_allowed_move_targets_graphql_error(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_phase_allowed_move_targets.side_effect = (
        PipefyGraphQLError([{"message": "Forbidden"}])
    )

    async with pipe_config_session as session:
        result = await session.call_tool(
            "get_phase_allowed_move_targets",
            {"phase_id": 55},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Forbidden" in tool_error_message(payload)


@pytest.mark.anyio
async def test_get_phase_allowed_move_targets_read_only_hint(pipe_config_session):
    async with pipe_config_session as session:
        listed = await session.list_tools()
    matching = [t for t in listed.tools if t.name == "get_phase_allowed_move_targets"]
    assert len(matching) == 1
    tool = matching[0]
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True


@pytest.mark.unit
def test_normalize_phase_cards_list__no_integration():
    raw = {
        "phase": {
            "id": "100",
            "cards": {"edges": [], "pageInfo": {"hasNextPage": False}},
        }
    }
    assert normalize_phase_cards_list(raw) == raw["phase"]


@pytest.mark.unit
def test_normalize_phase_cards_list_missing_phase__no_integration():
    assert normalize_phase_cards_list({}) is None
    assert normalize_phase_cards_list({"phase": None}) is None


@pytest.mark.anyio
async def test_get_phase_cards_count_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    phase_id = 342182335
    mock_pipe_config_client.get_phase.return_value = {
        "phase_id": str(phase_id),
        "phase_name": "Doing",
        "cards_count": 7,
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "get_phase_cards_count",
            {"phase_id": phase_id},
        )

    assert result.is_error is False
    mock_pipe_config_client.get_phase.assert_awaited_once_with(str(phase_id))
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"] == {
        "phase_id": str(phase_id),
        "phase_name": "Doing",
        "cards_count": 7,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("invalid_phase_id", [0, -1])
async def test_get_phase_cards_count_rejects_invalid_phase_id(
    pipe_config_session,
    mock_pipe_config_client,
    extract_payload,
    invalid_phase_id,
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "get_phase_cards_count",
            {"phase_id": invalid_phase_id},
        )
    mock_pipe_config_client.get_phase.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False


@pytest.mark.anyio
async def test_get_phase_cards_count_not_found(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_phase.side_effect = ValueError(
        "phase.cards_count missing from response"
    )

    async with pipe_config_session as session:
        result = await session.call_tool(
            "get_phase_cards_count",
            {"phase_id": 999},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_get_phase_cards_count_graphql_error(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_phase.side_effect = PipefyGraphQLError(
        [{"message": "Forbidden"}]
    )

    async with pipe_config_session as session:
        result = await session.call_tool(
            "get_phase_cards_count",
            {"phase_id": 55},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Forbidden" in tool_error_message(payload)


@pytest.mark.anyio
async def test_get_phase_cards_success(
    pipe_config_session,
    mock_pipe_config_client,
    extract_payload,
    legacy_envelope,
):
    phase_id = 342182335
    raw = {
        "phase": {
            "id": str(phase_id),
            "cards": {
                "edges": [{"node": {"id": "1", "title": "A"}}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "totalCount": 1,
            },
        }
    }
    mock_pipe_config_client.get_phase_cards.return_value = raw

    async with pipe_config_session as session:
        result = await session.call_tool(
            "get_phase_cards",
            {"phase_id": phase_id, "first": 50, "after": "cursor-1"},
        )

    assert result.is_error is False
    mock_pipe_config_client.get_phase_cards.assert_awaited_once_with(
        str(phase_id),
        first=50,
        after="cursor-1",
        include_fields=False,
    )
    payload = extract_payload(result)
    assert payload == raw


@pytest.mark.anyio
async def test_get_phase_cards_not_found(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_phase_cards.return_value = {"phase": None}

    async with pipe_config_session as session:
        result = await session.call_tool(
            "get_phase_cards",
            {"phase_id": 999},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("invalid_phase_id", [0, -1])
async def test_get_phase_cards_rejects_invalid_phase_id(
    pipe_config_session,
    mock_pipe_config_client,
    extract_payload,
    invalid_phase_id,
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "get_phase_cards",
            {"phase_id": invalid_phase_id},
        )
    mock_pipe_config_client.get_phase_cards.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False


@pytest.mark.anyio
async def test_get_phase_cards_read_only_hint(pipe_config_session):
    async with pipe_config_session as session:
        listed = await session.list_tools()
    for name in ("get_phase_cards_count", "get_phase_cards"):
        matching = [t for t in listed.tools if t.name == name]
        assert len(matching) == 1
        tool = matching[0]
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True


@pytest.mark.anyio
async def test_delete_field_condition_has_destructive_hint(pipe_config_session):
    async with pipe_config_session as session:
        listed = await session.list_tools()
    matching = [t for t in listed.tools if t.name == "delete_field_condition"]
    assert len(matching) == 1
    delete_tool = matching[0]
    assert delete_tool.annotations is not None
    assert delete_tool.annotations.destructive_hint is True
    assert delete_tool.annotations.read_only_hint is False
