"""Tests for pipe configuration MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.field_condition_tools import FieldConditionTools
from pipefy_mcp.tools.pipe_config_tool_helpers import (
    DeletePipeErrorPayload,
    build_field_condition_delete_payload,
    build_field_condition_success_payload,
    field_condition_phase_field_id_looks_like_slug,
)
from pipefy_mcp.tools.pipe_config_tools import PipeConfigTools
from pipefy_mcp.tools.tool_error_envelope import tool_error, tool_error_message
from tests.tools.conftest import assert_invalid_arguments_envelope


@pytest.mark.unit
def test_build_field_condition_payload_helpers__no_integration():
    created = build_field_condition_success_payload("c1", "created")
    assert created["success"] is True
    assert created["condition_id"] == "c1"
    assert created["action"] == "created"
    assert "c1" in created["message"]

    updated = build_field_condition_success_payload("c2", "updated")
    assert updated["action"] == "updated"

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
    client.get_phase_fields = AsyncMock()
    client.create_phase_field = AsyncMock()
    client.update_phase_field = AsyncMock()
    client.delete_phase_field = AsyncMock()
    client.create_label = AsyncMock()
    client.update_label = AsyncMock()
    client.delete_label = AsyncMock()
    client.create_field_condition = AsyncMock()
    client.update_field_condition = AsyncMock()
    client.delete_field_condition = AsyncMock()
    client.get_field_conditions = AsyncMock()
    client.get_field_condition = AsyncMock()
    return client


@pytest.fixture
def pipe_config_mcp_server(mock_pipe_config_client):
    mcp = FastMCP("Pipe Config Tools Test")
    PipeConfigTools.register(mcp, mock_pipe_config_client)
    FieldConditionTools.register(mcp, mock_pipe_config_client)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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

    assert result.isError is False
    mock_pipe_config_client.create_pipe.assert_awaited_once_with("N", "10")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "createPipe" in payload["result"]


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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

    assert result.isError is False
    mock_pipe_config_client.update_pipe.assert_awaited_once_with(
        "2", name="X", icon=None, color=None, preferences=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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

    assert result.isError is False
    mock_pipe_config_client.get_pipe.assert_awaited_once_with("9")
    mock_pipe_config_client.delete_pipe.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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

    assert result.isError is False
    mock_pipe_config_client.delete_pipe.assert_awaited_once_with("9")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["pipe_id"] == "9"


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_pipe_maps_not_found_on_get_pipe(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    error = TransportQueryError(
        "GraphQL Error",
        errors=[
            {
                "message": "Pipe not found",
                "extensions": {"code": "RESOURCE_NOT_FOUND"},
            }
        ],
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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

    assert result.isError is False
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_phase_preview_does_not_delete(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool("delete_phase", {"phase_id": 55})

    assert result.isError is False
    mock_pipe_config_client.delete_phase.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert payload["resource"] == "phase (ID: 55)"
    assert "⚠️" in payload["message"]
    assert "confirm=True" in payload["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_phase_field_preview_does_not_delete(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool("delete_phase_field", {"field_id": 100})

    assert result.isError is False
    mock_pipe_config_client.delete_phase_field.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert payload["resource"] == "phase field (ID: 100)"
    assert "⚠️" in payload["message"]
    assert "confirm=True" in payload["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_create_label_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_label.return_value = {
        "createLabel": {"label": {"id": "1", "name": "Bug", "color": "red"}},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_label",
            {"pipe_id": 2, "name": "Bug", "color": "red"},
        )

    mock_pipe_config_client.create_label.assert_awaited_once_with("2", "Bug", "red")
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_update_label_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_label.return_value = {
        "updateLabel": {"label": {"id": "3", "name": "Story", "color": "blue"}},
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_label",
            {"label_id": 3, "name": "Story", "color": "blue"},
        )

    mock_pipe_config_client.update_label.assert_awaited_once_with(
        "3", name="Story", color="blue"
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_update_label_strips_id_from_extra_input__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_label.return_value = {
        "updateLabel": {"label": {"id": "3", "name": "X", "color": "blue"}},
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_label",
            {
                "label_id": 3,
                "name": "X",
                "color": "blue",
                "extra_input": {"id": 999},
            },
        )
    mock_pipe_config_client.update_label.assert_awaited_once_with(
        "3",
        name="X",
        color="blue",
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_label_preview_does_not_delete(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool("delete_label", {"label_id": 40})

    assert result.isError is False
    mock_pipe_config_client.delete_label.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert payload["resource"] == "label (ID: 40)"
    assert "⚠️" in payload["message"]
    assert "confirm=True" in payload["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_create_pipe_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_pipe.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Organization not found"}],
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_update_pipe_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_pipe.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Pipe locked"}],
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_clone_pipe_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.clone_pipe.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Template missing"}],
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_create_phase_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_phase.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Pipe not found"}],
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_update_phase_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_phase.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Phase invalid"}],
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_update_phase_get_phase_fields_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.get_phase_fields.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Forbidden"}],
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_phase_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_phase.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Cannot delete"}],
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_phase", {"phase_id": 1, "confirm": True}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Cannot delete" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_create_phase_field_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_phase_field.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Invalid type"}],
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_update_phase_field_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_phase_field.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Field gone"}],
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_phase_field_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_phase_field.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Nope"}],
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_phase_field_cascade_diagnosis_with_pipe_id(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    """When the parent phase was deleted earlier in the session, Pipefy returns
    a generic ``INTERNAL_SERVER_ERROR``. With ``pipe_id`` supplied, the tool
    verifies the field is really gone and returns an actionable message
    instead of the opaque upstream error."""
    mock_pipe_config_client.delete_phase_field.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[
            {
                "message": "Something went wrong",
                "extensions": {"code": "INTERNAL_SERVER_ERROR"},
            }
        ],
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_phase_field_cascade_diagnosis_field_still_exists(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    """If the field is still present somewhere, the error is NOT a cascade —
    fall back to the generic upstream error instead of misleading the caller."""
    mock_pipe_config_client.delete_phase_field.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[
            {
                "message": "Something went wrong",
                "extensions": {"code": "INTERNAL_SERVER_ERROR"},
            }
        ],
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_phase_field_cascade_diagnosis_skipped_without_pipe_id(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    """Without ``pipe_id`` the tool cannot diagnose; it preserves the raw error
    and does NOT perform the extra read-backs."""
    mock_pipe_config_client.delete_phase_field.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[
            {
                "message": "Something went wrong",
                "extensions": {"code": "INTERNAL_SERVER_ERROR"},
            }
        ],
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_create_label_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_label.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Bad color"}],
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_label",
            {"pipe_id": 2, "name": "Bug", "color": "red"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Bad color" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_update_label_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_label.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Label missing"}],
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_label",
            {"label_id": 3, "name": "Story", "color": "blue"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Label missing" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_label_graphql_error_returns_failure__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_label.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Still in use"}],
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_label", {"label_id": 40, "confirm": True}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Still in use" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
    expected_condition = {
        "expressions": [
            {
                "field_address": "a",
                "operation": "equals",
                "value": "1",
                "structure_id": 42,
            }
        ],
        "expressions_structure": [[42]],
    }
    actions = [{"phaseFieldId": "308821043", "whenEvaluator": True, "actionId": "hide"}]
    mock_pipe_config_client.create_field_condition.return_value = {
        "createFieldCondition": {"fieldCondition": {"id": "cond-new"}},
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

    assert result.isError is False
    mock_pipe_config_client.create_field_condition.assert_awaited_once_with(
        "pf-99",
        expected_condition,
        actions,
        name="R1",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["condition_id"] == "cond-new"
    assert payload["action"] == "created"


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_create_field_condition_slug_like_phase_field_id_carries_invalid_arguments_code(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    """Pre-API arg validation must surface ``error.code = INVALID_ARGUMENTS``.

    Hit by smoke Phase 6 Probe 5: a slug-looking ``phaseFieldId`` (e.g.
    ``"nome_do_campo"``) triggers ``field_condition_actions_error_message``
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

    assert result.isError is False
    mock_pipe_config_client.create_field_condition.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert "get_phase_fields" in payload["error"]["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
    assert result.isError is False
    mock_pipe_config_client.create_field_condition.assert_awaited_once_with(
        "pf-99",
        expr,
        actions,
        name="Top-level name",
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
    assert result.isError is False
    mock_pipe_config_client.create_field_condition.assert_awaited_once_with(
        "pf-99",
        expr,
        actions,
        index=3,
        name="Top wins",
    )


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
    assert result.isError is False
    mock_pipe_config_client.create_field_condition.assert_awaited_once_with(
        "1",
        expr,
        actions,
        name="R",
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_create_field_condition_maps_hidden_action_id_to_hide__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    expr = {
        "expressions": [{"field_address": "a", "operation": "equals", "value": "1"}]
    }
    actions_in = [
        {"phaseFieldId": "308821043", "whenEvaluator": True, "actionId": "hidden"}
    ]
    mock_pipe_config_client.create_field_condition.return_value = {
        "createFieldCondition": {"fieldCondition": {"id": "cond-x"}},
    }
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_field_condition",
            {"phase_id": 1, "condition": expr, "actions": actions_in, "name": "R"},
        )
    assert result.isError is False
    mock_pipe_config_client.create_field_condition.assert_awaited_once_with(
        "1",
        expr,
        [{"phaseFieldId": "308821043", "whenEvaluator": True, "actionId": "hide"}],
        name="R",
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_create_field_condition_strips_expression_ids__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
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
    expected_condition = {
        "expressions": [
            {
                "field_address": "a",
                "operation": "equals",
                "value": "1",
                "structure_id": 99,
            }
        ],
        "expressions_structure": [[99]],
    }
    actions = [{"phaseFieldId": "308821043", "whenEvaluator": True, "actionId": "hide"}]
    mock_pipe_config_client.create_field_condition.return_value = {
        "createFieldCondition": {"fieldCondition": {"id": "cond-stripped"}},
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
    assert result.isError is False
    mock_pipe_config_client.create_field_condition.assert_awaited_once_with(
        "1",
        expected_condition,
        actions,
        name="R",
    )
    assert extract_payload(result)["success"] is True
    assert extract_payload(result)["condition_id"] == "cond-stripped"


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_create_field_condition_error(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_field_condition.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Invalid condition"}],
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

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Invalid condition" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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

    assert result.isError is False
    mock_pipe_config_client.update_field_condition.assert_awaited_once_with(
        "cond-2",
        name="Patched",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["condition_id"] == "cond-2"
    assert payload["action"] == "updated"


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
    condition_for_api = {
        "expressions": [{"field_address": "f1", "operation": "equals", "value": "x"}],
    }
    actions_in = [{"phaseFieldId": "308821043", "actionId": "hidden"}]
    actions_for_api = [{"phaseFieldId": "308821043", "actionId": "hide"}]

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

    assert result.isError is False
    mock_pipe_config_client.update_field_condition.assert_awaited_once_with(
        "cond-7",
        name="N7",
        condition=condition_for_api,
        actions=actions_for_api,
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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

    assert result.isError is False
    mock_pipe_config_client.update_field_condition.assert_awaited_once_with(
        "cond-8",
        name="Top name",
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
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
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_update_field_condition_error(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.update_field_condition.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Not found"}],
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

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Field condition not found" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_field_condition_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_field_condition.return_value = {"success": True}

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_field_condition",
            {"condition_id": "cond-9", "confirm": True},
        )

    assert result.isError is False
    mock_pipe_config_client.delete_field_condition.assert_awaited_once_with("cond-9")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload.get("message")


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_field_condition_error(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_field_condition.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Forbidden"}],
    )

    async with pipe_config_session as session:
        result = await session.call_tool(
            "delete_field_condition",
            {"condition_id": "cond-x", "confirm": True},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Forbidden" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_field_condition_has_destructive_hint(pipe_config_session):
    async with pipe_config_session as session:
        listed = await session.list_tools()
    matching = [t for t in listed.tools if t.name == "delete_field_condition"]
    assert len(matching) == 1
    delete_tool = matching[0]
    assert delete_tool.annotations is not None
    assert delete_tool.annotations.destructiveHint is True
    assert delete_tool.annotations.readOnlyHint is False
