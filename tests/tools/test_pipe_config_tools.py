"""Tests for pipe configuration MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.pipe_config_tool_helpers import DeletePipeErrorPayload
from pipefy_mcp.tools.pipe_config_tools import PipeConfigTools


@pytest.fixture
def anyio_backend():
    return "asyncio"


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
    return client


@pytest.fixture
def pipe_config_mcp_server(mock_pipe_config_client):
    mcp = FastMCP("Pipe Config Tools Test")
    PipeConfigTools.register(mcp, mock_pipe_config_client)
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
    mock_pipe_config_client.create_pipe.assert_awaited_once_with("N", 10)
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
        2, name="X", icon=None, color=None, preferences=None
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
    mock_pipe_config_client.get_pipe.assert_awaited_once_with(9)
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
    mock_pipe_config_client.delete_pipe.assert_awaited_once_with(9)
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["pipe_id"] == 9


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
    expected: DeletePipeErrorPayload = {
        "success": False,
        "error": "Invalid 'pipe_id'. Use a positive integer.",
    }
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
    assert "not found" in payload["error"].lower()


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
        100, organization_id=None
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
        1,
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
        10,
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

    mock_pipe_config_client.get_phase_fields.assert_awaited_once_with(10)
    mock_pipe_config_client.update_phase.assert_awaited_once_with(
        10,
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
        result = await session.call_tool("delete_phase", {"phase_id": 55})

    mock_pipe_config_client.delete_phase.assert_awaited_once_with(55)
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_create_phase_field_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_phase_field.return_value = {
        "createPhaseField": {
            "phase_field": {"id": "f1", "label": "Email", "type": "email"},
        },
    }

    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_phase_field",
            {
                "phase_id": 1,
                "label": "Email",
                "field_type": "email",
                "extra_input": {"description": "Contact"},
            },
        )

    mock_pipe_config_client.create_phase_field.assert_awaited_once_with(
        1,
        "Email",
        "email",
        description="Contact",
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
        9,
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
async def test_update_phase_field_requires_at_least_one_attr(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool(
            "update_phase_field",
            {"field_id": 9},
        )
    mock_pipe_config_client.update_phase_field.assert_not_called()
    assert extract_payload(result)["success"] is False


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
            {"field_id": 100},
        )

    mock_pipe_config_client.delete_phase_field.assert_awaited_once_with(100)
    assert extract_payload(result)["success"] is True


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
            {"field_id": "detalhe_mcp"},
        )

    mock_pipe_config_client.delete_phase_field.assert_awaited_once_with(
        "detalhe_mcp",
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

    mock_pipe_config_client.create_label.assert_awaited_once_with(2, "Bug", "red")
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
            {"label_id": 3, "name": "Story"},
        )

    mock_pipe_config_client.update_label.assert_awaited_once_with(3, name="Story")
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
                "extra_input": {"id": 999, "color": "blue"},
            },
        )
    mock_pipe_config_client.update_label.assert_awaited_once_with(
        3,
        name="X",
        color="blue",
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_label_success(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.delete_label.return_value = {
        "deleteLabel": {"success": True},
    }

    async with pipe_config_session as session:
        result = await session.call_tool("delete_label", {"label_id": 40})

    mock_pipe_config_client.delete_label.assert_awaited_once_with(40)
    assert extract_payload(result)["success"] is True


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
    assert "Organization not found" in payload["error"]


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
    assert "Pipe locked" in payload["error"]


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
    assert "Template missing" in payload["error"]


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
    assert "Pipe not found" in payload["error"]


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
    assert "Phase invalid" in payload["error"]


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
    assert "Forbidden" in payload["error"]


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
        result = await session.call_tool("delete_phase", {"phase_id": 1})
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Cannot delete" in payload["error"]


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
    assert "Invalid type" in payload["error"]


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
    assert "Field gone" in payload["error"]


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
            {"field_id": 100},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Nope" in payload["error"]


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
    assert "Bad color" in payload["error"]


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
            {"label_id": 3, "name": "Story"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Label missing" in payload["error"]


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
        result = await session.call_tool("delete_label", {"label_id": 40})
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Still in use" in payload["error"]


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
        1,
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
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_delete_label_rejects_invalid_id__no_integration(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    async with pipe_config_session as session:
        result = await session.call_tool("delete_label", {"label_id": -1})
    mock_pipe_config_client.delete_label.assert_not_called()
    assert extract_payload(result)["success"] is False
