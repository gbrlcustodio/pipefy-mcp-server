"""Tests for iPaaS MCP tools (mocked PipefyClient and gateway)."""

from contextlib import asynccontextmanager
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from _mcp_compat import (
    create_connected_server_and_client_session as create_client_session,
)
from mcp.server.mcpserver import MCPServer
from pipefy_sdk import PipefyClient

from pipefy_mcp.auth import RequestScopedIdentity
from pipefy_mcp.core.ipaas_gateway import IpaasGateway, IpaasGatewayError
from pipefy_mcp.core.runtime import McpRuntime
from pipefy_mcp.core.tool_error_envelope import tool_error_message
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.ipaas_tools import (
    IPAAS_DESTRUCTIVE_NEEDLES,
    IpaasTools,
    ipaas_call_is_destructive,
)
from tools.destructive_confirm_test_support import confirm_after_preview

TOOLS = [
    {
        "name": "demo_create_flow",
        "description": "Create a new flow\n\nLonger guidance the compact list drops.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}},
    },
    {
        "name": "demo_list_flows",
        "description": "List flows in the current project",
        "inputSchema": {"type": "object"},
    },
]


def build_ipaas_test_server(client, gateway, *, remote=False):
    """An MCPServer whose runtime serves ``client`` and ``gateway``.

    Mirrors ``build_tool_test_server`` (tools/conftest.py) and additionally
    plants the iPaaS gateway on the runtime (the property reads the instance
    attribute the composition normally sets from settings). ``remote=True``
    builds the runtime from settings resolved to the hosted profile, which is
    what the tools' call-time input restrictions read.
    """
    runtime_settings = settings
    if remote:
        runtime_settings = settings.model_copy(
            update={"mcp": settings.mcp.model_copy(update={"profile": "remote"})}
        )

    @asynccontextmanager
    async def _lifespan(_app):
        runtime = McpRuntime(runtime_settings, RequestScopedIdentity())
        runtime.session_for_request = lambda _req: client
        runtime._ipaas_gateway = gateway
        yield runtime

    mcp = MCPServer("Pipefy iPaaS Tools Test", lifespan=_lifespan)
    IpaasTools.register(mcp)
    return mcp


@pytest.fixture
def mock_client():
    client = MagicMock(PipefyClient)
    client.get_advanced_automations_token = AsyncMock(return_value="embed-jwt")
    return client


_CALL_OK = {
    "content": [{"type": "text", "text": "ok"}],
    "isError": False,
}

PIPE_ID = "303088927"


def _wire_entry(name, *, destructive_hint=None, extra_annotations=None):
    """Live-shaped list_tools wire object. Omit destructive_hint for no boolean."""
    entry = {
        "name": name,
        "description": f"{name} catalog entry",
        "inputSchema": {"type": "object"},
    }
    annotations = dict(extra_annotations or {})
    if destructive_hint is not None:
        annotations["destructiveHint"] = destructive_hint
    if annotations:
        entry["annotations"] = annotations
    return entry


_MIXED_WIDGETS = _wire_entry("manage_widgets", destructive_hint=False)


@pytest.fixture
def mock_gateway():
    gateway = MagicMock(IpaasGateway)
    gateway.list_tools = AsyncMock(return_value=TOOLS)
    gateway.call_tool = AsyncMock(return_value=_CALL_OK)

    @asynccontextmanager
    async def mcp_session(token):
        session = MagicMock()

        async def list_tools():
            return await gateway.list_tools(token)

        async def call_tool(name, arguments=None):
            return await gateway.call_tool(token, name, arguments)

        session.list_tools = list_tools
        session.call_tool = call_tool
        yield session

    gateway.mcp_session = mcp_session
    return gateway


def _session(server):
    return create_client_session(
        server, read_timeout_seconds=timedelta(seconds=10), raise_exceptions=True
    )


def test_ipaas_destructive_needles_are_the_frozen_six():
    assert IPAAS_DESTRUCTIVE_NEEDLES == (
        "delete",
        "remove",
        "destroy",
        "drop",
        "uninstall",
        "revoke",
    )


def test_ipaas_call_is_destructive_annotation_true_wins_over_benign_name():
    entry = _wire_entry("archive_everything", destructive_hint=True)
    assert ipaas_call_is_destructive(entry, None) is True
    assert ipaas_call_is_destructive(entry, {"operation": "ADD"}) is True


def test_ipaas_call_is_destructive_operation_equality_gates_even_when_annotated_false():
    entry = _MIXED_WIDGETS
    assert ipaas_call_is_destructive(entry, {"operation": "DELETE"}) is True
    assert ipaas_call_is_destructive(entry, {"operation": "delete"}) is True
    assert ipaas_call_is_destructive(entry, {"operation": "ADD"}) is False
    assert ipaas_call_is_destructive(entry, {"operation": "UNDELETE"}) is False
    assert ipaas_call_is_destructive(entry, {"operation": 1}) is False
    assert ipaas_call_is_destructive(entry, {}) is False
    assert ipaas_call_is_destructive(entry, None) is False


def test_ipaas_call_is_destructive_annotation_false_does_not_fall_through_to_name():
    entry = _wire_entry("delete_flow", destructive_hint=False)
    assert ipaas_call_is_destructive(entry, None) is False


def test_ipaas_call_is_destructive_no_boolean_uses_name_substring():
    named = {"name": "delete_flow"}
    assert ipaas_call_is_destructive(named, None) is True
    assert (
        ipaas_call_is_destructive(
            _wire_entry("list_flows", extra_annotations={"readOnlyHint": True}),
            None,
        )
        is False
    )
    assert ipaas_call_is_destructive({"name": "list_flows"}, None) is False


def test_ipaas_call_is_destructive_missing_entry_is_no_boolean():
    assert ipaas_call_is_destructive(None, None) is False
    assert ipaas_call_is_destructive(None, {"operation": "DELETE"}) is True
    assert ipaas_call_is_destructive(None, {"operation": "UNDELETE"}) is False
    assert ipaas_call_is_destructive({"name": "delete_flow"}, None) is True
    assert ipaas_call_is_destructive({"name": "list_widgets"}, None) is False


@pytest.mark.anyio
async def test_compact_catalog_lists_names_and_first_lines(
    mock_client, mock_gateway, extract_payload
):
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool("get_ipaas_tools", {"pipe_id": "303088927"})

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is True
    mock_client.get_advanced_automations_token.assert_awaited_once_with("303088927")
    mock_gateway.list_tools.assert_awaited_once_with("embed-jwt")
    assert '"count": 2' in payload["result"]
    assert '"demo_create_flow"' in payload["result"]
    # Compact mode keeps the first description line and drops the schema.
    assert "Create a new flow" in payload["result"]
    assert "Longer guidance" not in payload["result"]
    assert "inputSchema" not in payload["result"]
    # The hint names the full discover -> expand -> call loop.
    assert "call_ipaas_tool" in payload["result"]


@pytest.mark.anyio
async def test_tool_name_returns_full_schema(
    mock_client, mock_gateway, extract_payload
):
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "get_ipaas_tools", {"pipe_id": "303088927", "tool_name": "demo_create_flow"}
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    assert "inputSchema" in payload["result"]
    assert "Longer guidance" in payload["result"]
    assert "demo_list_flows" not in payload["result"]


@pytest.mark.anyio
async def test_unknown_tool_name_lists_available(
    mock_client, mock_gateway, extract_payload
):
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "get_ipaas_tools", {"pipe_id": "303088927", "tool_name": "demo_nope"}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload)
    assert "demo_nope" in message
    assert "demo_create_flow" in message


@pytest.mark.anyio
async def test_unconfigured_gateway_reports_clearly(mock_client, extract_payload):
    server = build_ipaas_test_server(mock_client, gateway=None)
    async with _session(server) as session:
        result = await session.call_tool("get_ipaas_tools", {"pipe_id": "303088927"})

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "disabled" in tool_error_message(payload)
    mock_client.get_advanced_automations_token.assert_not_awaited()


@pytest.mark.anyio
async def test_token_permission_error_becomes_error_payload(
    mock_client, mock_gateway, extract_payload
):
    mock_client.get_advanced_automations_token = AsyncMock(
        side_effect=ValueError("PermissionDeniedError: not allowed")
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool("get_ipaas_tools", {"pipe_id": "303088927"})

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "PermissionDenied" in tool_error_message(payload)
    mock_gateway.list_tools.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("exc_message", ["", "   "])
async def test_empty_exception_message_uses_fallback(
    mock_client, mock_gateway, extract_payload, exc_message
):
    mock_client.get_advanced_automations_token = AsyncMock(
        side_effect=RuntimeError(exc_message)
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool("get_ipaas_tools", {"pipe_id": "303088927"})

    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload)
    assert message.strip()
    assert "iPaaS request failed." in message
    assert "do not blind-retry" in message
    mock_gateway.list_tools.assert_not_awaited()


@pytest.mark.anyio
async def test_non_empty_exception_message_preserved(
    mock_client, mock_gateway, extract_payload
):
    mock_client.get_advanced_automations_token = AsyncMock(
        side_effect=RuntimeError("token mint failed")
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool("get_ipaas_tools", {"pipe_id": "303088927"})

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "token mint failed" in tool_error_message(payload)


@pytest.mark.anyio
async def test_gateway_error_becomes_error_payload(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.list_tools = AsyncMock(
        side_effect=IpaasGatewayError("iPaaS session exchange failed (HTTP 401): nope")
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool("get_ipaas_tools", {"pipe_id": "303088927"})

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "session exchange" in tool_error_message(payload)


@pytest.mark.anyio
async def test_int_pipe_id_is_coerced_to_string(
    mock_client, mock_gateway, extract_payload
):
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool("get_ipaas_tools", {"pipe_id": 303088927})

    payload = extract_payload(result)
    assert payload["success"] is True
    mock_client.get_advanced_automations_token.assert_awaited_once_with("303088927")


@pytest.mark.anyio
async def test_call_tool_forwards_arguments_and_relays_output(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.call_tool = AsyncMock(
        return_value={
            "content": [
                {"type": "text", "text": "flow created"},
                {"type": "text", "text": "id: flow-1"},
            ],
            "isError": False,
        }
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "call_ipaas_tool",
            {
                "pipe_id": "303088927",
                "tool_name": "demo_create_flow",
                "arguments": {"name": "My flow"},
            },
        )

    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is True
    mock_client.get_advanced_automations_token.assert_awaited_once_with("303088927")
    mock_gateway.list_tools.assert_awaited_once_with("embed-jwt")
    mock_gateway.call_tool.assert_awaited_once_with(
        "embed-jwt", "demo_create_flow", {"name": "My flow"}
    )
    # Text segments are joined and relayed in full.
    assert "flow created" in payload["result"]
    assert "id: flow-1" in payload["result"]
    assert '"demo_create_flow"' in payload["result"]


@pytest.mark.anyio
async def test_call_tool_arguments_default_to_none(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.call_tool = AsyncMock(
        return_value={"content": [{"type": "text", "text": "[]"}], "isError": False}
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "call_ipaas_tool",
            {"pipe_id": "303088927", "tool_name": "demo_list_flows"},
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    mock_gateway.call_tool.assert_awaited_once_with(
        "embed-jwt", "demo_list_flows", None
    )


@pytest.mark.anyio
async def test_call_tool_maps_host_iserror_to_error_payload(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.call_tool = AsyncMock(
        return_value={
            "content": [{"type": "text", "text": "flow not found"}],
            "isError": True,
        }
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "call_ipaas_tool",
            {"pipe_id": "303088927", "tool_name": "demo_create_flow"},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "flow not found" in tool_error_message(payload)


@pytest.mark.anyio
async def test_call_tool_null_result_becomes_error_payload_not_attribute_error(
    mock_client, mock_gateway, extract_payload
):
    """A host `result: null` surfaces (via the gateway guard) as the standard
    envelope, never a bare `AttributeError` on a None result."""
    mock_gateway.call_tool = AsyncMock(
        side_effect=IpaasGatewayError("iPaaS tools/call returned a non-object result.")
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "call_ipaas_tool",
            {"pipe_id": "303088927", "tool_name": "demo_list_flows"},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "non-object result" in tool_error_message(payload)


@pytest.mark.anyio
async def test_call_tool_passes_non_text_content_through(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.call_tool = AsyncMock(
        return_value={
            "content": [
                {"type": "text", "text": "done"},
                {"type": "image", "data": "aGk=", "mimeType": "image/png"},
            ],
            "isError": False,
        }
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "call_ipaas_tool",
            {"pipe_id": "303088927", "tool_name": "demo_get_run"},
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    assert '"image"' in payload["result"]
    assert "aGk=" in payload["result"]


@pytest.mark.anyio
async def test_call_tool_gateway_error_becomes_error_payload(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.call_tool = AsyncMock(
        side_effect=IpaasGatewayError("iPaaS tools/call failed (HTTP 500): boom")
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "call_ipaas_tool",
            {"pipe_id": "303088927", "tool_name": "demo_create_flow"},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "tools/call" in tool_error_message(payload)


@pytest.mark.anyio
async def test_call_tool_unconfigured_gateway_reports_clearly(
    mock_client, extract_payload
):
    server = build_ipaas_test_server(mock_client, gateway=None)
    async with _session(server) as session:
        result = await session.call_tool(
            "call_ipaas_tool",
            {"pipe_id": "303088927", "tool_name": "demo_create_flow"},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "disabled" in tool_error_message(payload)
    mock_client.get_advanced_automations_token.assert_not_awaited()


async def _call_ipaas(session, tool_name, arguments=None, **extra):
    payload = {
        "pipe_id": PIPE_ID,
        "tool_name": tool_name,
        **extra,
    }
    if arguments is not None:
        payload["arguments"] = arguments
    return await session.call_tool("call_ipaas_tool", payload)


@pytest.mark.anyio
async def test_read_like_annotated_false_calls_tool_without_preview(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.list_tools = AsyncMock(
        return_value=[_wire_entry("list_flows", destructive_hint=False)]
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await _call_ipaas(session, "list_flows")

    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload.get("requires_confirmation") is not True
    mock_gateway.list_tools.assert_awaited_once_with("embed-jwt")
    mock_gateway.call_tool.assert_awaited_once_with("embed-jwt", "list_flows", None)


@pytest.mark.anyio
async def test_annotated_true_benign_name_previews_without_calling(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.list_tools = AsyncMock(
        return_value=[_wire_entry("archive_everything", destructive_hint=True)]
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await _call_ipaas(session, "archive_everything")

    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert payload["confirmation_token"]
    assert "archive_everything" in payload["resource"]
    assert PIPE_ID in payload["resource"]
    mock_gateway.call_tool.assert_not_awaited()


@pytest.mark.anyio
async def test_no_boolean_delete_flow_name_previews(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.list_tools = AsyncMock(
        return_value=[
            _wire_entry("delete_flow", extra_annotations={"readOnlyHint": False})
        ]
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await _call_ipaas(session, "delete_flow")

    payload = extract_payload(result)
    assert payload["requires_confirmation"] is True
    mock_gateway.call_tool.assert_not_awaited()


@pytest.mark.anyio
async def test_mixed_operation_add_calls_tool(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.list_tools = AsyncMock(return_value=[_MIXED_WIDGETS])
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await _call_ipaas(session, "manage_widgets", {"operation": "ADD"})

    payload = extract_payload(result)
    assert payload["success"] is True
    mock_gateway.call_tool.assert_awaited_once_with(
        "embed-jwt", "manage_widgets", {"operation": "ADD"}
    )


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["DELETE", "delete"])
async def test_mixed_operation_delete_previews_with_operation_identity(
    mock_client, mock_gateway, extract_payload, monkeypatch, operation
):
    mock_gateway.list_tools = AsyncMock(return_value=[_MIXED_WIDGETS])
    captured = {}

    async def capture_guard(_ctx, **kwargs):
        captured["resource_identity"] = kwargs["resource_identity"]
        captured["resource_descriptor"] = kwargs["resource_descriptor"]
        captured["tool_name"] = kwargs["tool_name"]
        return {
            "success": False,
            "requires_confirmation": True,
            "confirmation_token": "v1.preview",
            "resource": kwargs["resource_descriptor"],
            "message": "preview",
        }

    monkeypatch.setattr(
        "pipefy_mcp.tools.ipaas_tools.check_destructive_confirmation",
        capture_guard,
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await _call_ipaas(session, "manage_widgets", {"operation": operation})

    payload = extract_payload(result)
    assert payload["requires_confirmation"] is True
    mock_gateway.call_tool.assert_not_awaited()
    assert captured["tool_name"] == "call_ipaas_tool"
    assert captured["resource_identity"] == {
        "pipe_id": PIPE_ID,
        "tool_name": "manage_widgets",
        "operation": "delete",
    }
    descriptor = captured["resource_descriptor"]
    assert PIPE_ID in descriptor
    assert "manage_widgets" in descriptor
    assert operation in descriptor


@pytest.mark.anyio
async def test_delete_token_does_not_confirm_add_arguments(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.list_tools = AsyncMock(
        return_value=[_wire_entry("archive_everything", destructive_hint=True)]
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        preview = await _call_ipaas(
            session, "archive_everything", {"operation": "DELETE"}
        )
        token = extract_payload(preview)["confirmation_token"]
        mismatch = await _call_ipaas(
            session,
            "archive_everything",
            {"operation": "ADD"},
            confirm=True,
            confirmation_token=token,
        )

    payload = extract_payload(mismatch)
    assert payload["requires_confirmation"] is True
    assert payload["confirmation_token"] != token
    assert payload["message"].startswith("⚠️ Running ")
    mock_gateway.call_tool.assert_not_awaited()


@pytest.mark.anyio
async def test_mixed_delete_token_does_not_confirm_add_arguments(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.list_tools = AsyncMock(return_value=[_MIXED_WIDGETS])
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        preview = await _call_ipaas(session, "manage_widgets", {"operation": "DELETE"})
        token = extract_payload(preview)["confirmation_token"]
        mismatch = await _call_ipaas(
            session,
            "manage_widgets",
            {"operation": "ADD"},
            confirm=True,
            confirmation_token=token,
        )

    payload = extract_payload(mismatch)
    assert payload["requires_confirmation"] is True
    assert payload["confirmation_token"] != token
    assert payload["message"].startswith("⚠️ Running ")
    mock_gateway.call_tool.assert_not_awaited()


@pytest.mark.anyio
async def test_delete_token_confirms_matching_delete_arguments(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.list_tools = AsyncMock(return_value=[_MIXED_WIDGETS])
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        payload = await confirm_after_preview(
            session,
            "call_ipaas_tool",
            {
                "pipe_id": PIPE_ID,
                "tool_name": "manage_widgets",
                "arguments": {"operation": "DELETE"},
                "confirm": True,
            },
        )

    assert payload["success"] is True
    mock_gateway.call_tool.assert_awaited_once_with(
        "embed-jwt", "manage_widgets", {"operation": "DELETE"}
    )


@pytest.mark.anyio
async def test_mixed_undelete_operation_is_ungated(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.list_tools = AsyncMock(return_value=[_MIXED_WIDGETS])
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await _call_ipaas(session, "manage_widgets", {"operation": "UNDELETE"})

    payload = extract_payload(result)
    assert payload["success"] is True
    mock_gateway.call_tool.assert_awaited_once()


@pytest.mark.anyio
async def test_list_tools_failure_is_error_envelope_and_does_not_call(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.list_tools = AsyncMock(
        side_effect=IpaasGatewayError("iPaaS tools/list failed (HTTP 500): boom")
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await _call_ipaas(session, "delete_flow")

    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload.get("requires_confirmation") is not True
    assert "tools/list" in tool_error_message(payload)
    mock_gateway.call_tool.assert_not_awaited()


@pytest.mark.anyio
async def test_missing_catalog_benign_name_still_calls(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.list_tools = AsyncMock(return_value=[_MIXED_WIDGETS])
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await _call_ipaas(session, "list_widgets")

    payload = extract_payload(result)
    assert payload["success"] is True
    mock_gateway.call_tool.assert_awaited_once_with("embed-jwt", "list_widgets", None)


@pytest.mark.anyio
async def test_missing_catalog_delete_flow_is_gated(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.list_tools = AsyncMock(return_value=[_MIXED_WIDGETS])
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await _call_ipaas(session, "delete_flow")

    payload = extract_payload(result)
    assert payload["requires_confirmation"] is True
    mock_gateway.call_tool.assert_not_awaited()


@pytest.mark.anyio
async def test_call_ipaas_tool_keeps_destructive_hint(mock_client, mock_gateway):
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        listed = await session.list_tools()

    tool = next(t for t in listed.tools if t.name == "call_ipaas_tool")
    assert tool.annotations is not None
    assert tool.annotations.destructive_hint is True


PIECE_NAME = "@example/piece-demo"

CREATED_CONNECTION = {
    "id": "conn-1",
    "externalId": "mcp-abc",
    "displayName": "Demo",
    "pieceName": PIECE_NAME,
    "status": "ACTIVE",
    "type": "SECRET_TEXT",
    "value": {"secret_text": "must-never-leak"},
}


@pytest.mark.anyio
async def test_create_connection_with_literal_secret(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.upsert_connection = AsyncMock(return_value=CREATED_CONNECTION)
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "create_ipaas_connection",
            {
                "pipe_id": "303088927",
                "piece_name": PIECE_NAME,
                "connection_type": "SECRET_TEXT",
                "value": {"secret_text": "shh"},
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    kwargs = mock_gateway.upsert_connection.await_args.kwargs
    assert kwargs["connection_type"] == "SECRET_TEXT"
    assert kwargs["value"] == {"secret_text": "shh"}
    # A fresh external id is generated; display name falls back to it.
    assert kwargs["external_id"].startswith("mcp-")
    assert kwargs["display_name"] == kwargs["external_id"]
    # Only non-sensitive fields are relayed.
    assert "must-never-leak" not in payload["result"]
    assert '"externalId": "mcp-abc"' in payload["result"]


@pytest.mark.anyio
async def test_create_connection_resolves_prefixed_env_refs(
    mock_client, mock_gateway, extract_payload, monkeypatch
):
    monkeypatch.setenv("PIPEFY_IPAAS_CONNECTION_DEMO_TOKEN", "resolved-secret")
    mock_gateway.upsert_connection = AsyncMock(return_value=CREATED_CONNECTION)
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "create_ipaas_connection",
            {
                "pipe_id": "303088927",
                "piece_name": PIECE_NAME,
                "connection_type": "CUSTOM_AUTH",
                "value": {
                    "props": {
                        "token": {"$env": "PIPEFY_IPAAS_CONNECTION_DEMO_TOKEN"},
                        "plain": "literal",
                    }
                },
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    kwargs = mock_gateway.upsert_connection.await_args.kwargs
    assert kwargs["value"] == {
        "props": {"token": "resolved-secret", "plain": "literal"}
    }
    assert "resolved-secret" not in payload["result"]


@pytest.mark.anyio
async def test_create_connection_rejects_unprefixed_env_refs(
    mock_client, mock_gateway, extract_payload, monkeypatch
):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "should-not-resolve")
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "create_ipaas_connection",
            {
                "pipe_id": "303088927",
                "piece_name": PIECE_NAME,
                "connection_type": "SECRET_TEXT",
                "value": {"secret_text": {"$env": "AWS_SECRET_ACCESS_KEY"}},
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "PIPEFY_IPAAS_CONNECTION_" in tool_error_message(payload)
    mock_gateway.upsert_connection.assert_not_awaited()


@pytest.mark.anyio
async def test_create_connection_reports_missing_env_var(
    mock_client, mock_gateway, extract_payload
):
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "create_ipaas_connection",
            {
                "pipe_id": "303088927",
                "piece_name": PIECE_NAME,
                "connection_type": "SECRET_TEXT",
                "value": {"secret_text": {"$env": "PIPEFY_IPAAS_CONNECTION_NOPE"}},
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not set" in tool_error_message(payload)


@pytest.mark.anyio
async def test_create_connection_rejects_env_refs_on_remote_profile(
    mock_client, mock_gateway, extract_payload, monkeypatch
):
    """A prefixed, set variable still does not resolve on the hosted profile.

    The hosted server's environment belongs to the deployment and is shared
    by every caller, so references are rejected before any lookup.
    """
    monkeypatch.setenv("PIPEFY_IPAAS_CONNECTION_DEMO_TOKEN", "resolved-secret")
    server = build_ipaas_test_server(mock_client, mock_gateway, remote=True)
    async with _session(server) as session:
        result = await session.call_tool(
            "create_ipaas_connection",
            {
                "pipe_id": "303088927",
                "piece_name": PIECE_NAME,
                "connection_type": "SECRET_TEXT",
                "value": {
                    "secret_text": {"$env": "PIPEFY_IPAAS_CONNECTION_DEMO_TOKEN"}
                },
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload)
    assert "hosted" in message
    assert "resolved-secret" not in str(payload)
    mock_gateway.upsert_connection.assert_not_awaited()


@pytest.mark.anyio
async def test_create_connection_literal_secret_works_on_remote_profile(
    mock_client, mock_gateway, extract_payload
):
    """Literal mode stays allowed on hosted; only $env references are gated."""
    mock_gateway.upsert_connection = AsyncMock(return_value=CREATED_CONNECTION)
    server = build_ipaas_test_server(mock_client, mock_gateway, remote=True)
    async with _session(server) as session:
        result = await session.call_tool(
            "create_ipaas_connection",
            {
                "pipe_id": "303088927",
                "piece_name": PIECE_NAME,
                "connection_type": "SECRET_TEXT",
                "value": {"secret_text": "shh"},
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    assert mock_gateway.upsert_connection.await_args.kwargs["value"] == {
        "secret_text": "shh"
    }


@pytest.mark.anyio
async def test_create_connection_oauth_mode_builds_value_from_bundle(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.upsert_connection = AsyncMock(return_value=CREATED_CONNECTION)
    server = build_ipaas_test_server(mock_client, mock_gateway)
    completion = {
        "type": "PLATFORM_OAUTH2",
        "client_id": "deployment-client",
        "redirect_url": "https://ipaas.test/redirect",
        "scope": "chat:write read",
        "code_verifier": "the-verifier",
    }
    async with _session(server) as session:
        result = await session.call_tool(
            "create_ipaas_connection",
            {
                "pipe_id": "303088927",
                "piece_name": PIECE_NAME,
                "oauth": {
                    "completion": completion,
                    "authorization_response": (
                        "https://ipaas.test/redirect?code=auth-code-1&state=xyz"
                    ),
                },
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    kwargs = mock_gateway.upsert_connection.await_args.kwargs
    assert kwargs["connection_type"] == "PLATFORM_OAUTH2"
    assert kwargs["value"] == {
        "client_id": "deployment-client",
        "code": "auth-code-1",
        "scope": "chat:write read",
        "redirect_url": "https://ipaas.test/redirect",
        "code_challenge": "the-verifier",
    }


@pytest.mark.anyio
async def test_create_connection_oauth_mode_accepts_bare_code(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.upsert_connection = AsyncMock(return_value=CREATED_CONNECTION)
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "create_ipaas_connection",
            {
                "pipe_id": "303088927",
                "piece_name": PIECE_NAME,
                "oauth": {
                    "completion": {
                        "type": "PLATFORM_OAUTH2",
                        "client_id": "c",
                        "redirect_url": "https://ipaas.test/redirect",
                        "scope": "",
                    },
                    "authorization_response": "bare-code-42",
                },
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    kwargs = mock_gateway.upsert_connection.await_args.kwargs
    assert kwargs["value"]["code"] == "bare-code-42"
    assert "code_challenge" not in kwargs["value"]


@pytest.mark.anyio
async def test_create_connection_env_ref_with_sibling_keys_is_rejected(
    mock_client, mock_gateway, extract_payload, monkeypatch
):
    """A $env object carrying extra keys must fail loudly, not ship literally."""
    monkeypatch.setenv("PIPEFY_IPAAS_CONNECTION_DEMO_TOKEN", "resolved-secret")
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "create_ipaas_connection",
            {
                "pipe_id": "303088927",
                "piece_name": PIECE_NAME,
                "connection_type": "SECRET_TEXT",
                "value": {
                    "secret_text": {
                        "$env": "PIPEFY_IPAAS_CONNECTION_DEMO_TOKEN",
                        "note": "typo",
                    }
                },
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "only" in tool_error_message(payload)
    mock_gateway.upsert_connection.assert_not_awaited()


@pytest.mark.anyio
async def test_create_connection_null_authorization_response_reports_empty(
    mock_client, mock_gateway, extract_payload
):
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "create_ipaas_connection",
            {
                "pipe_id": "303088927",
                "piece_name": PIECE_NAME,
                "oauth": {
                    "completion": {
                        "type": "PLATFORM_OAUTH2",
                        "client_id": "c",
                        "redirect_url": "https://ipaas.test/redirect",
                    },
                    "authorization_response": None,
                },
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "is empty" in tool_error_message(payload)


@pytest.mark.anyio
async def test_create_connection_incomplete_bundle_names_missing_fields(
    mock_client, mock_gateway, extract_payload
):
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "create_ipaas_connection",
            {
                "pipe_id": "303088927",
                "piece_name": PIECE_NAME,
                "oauth": {
                    "completion": {"type": "PLATFORM_OAUTH2"},
                    "authorization_response": "bare-code",
                },
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload)
    assert "client_id" in message
    assert "redirect_url" in message
    assert "verbatim" in message


@pytest.mark.anyio
async def test_create_connection_preserves_plus_in_pasted_code(
    mock_client, mock_gateway, extract_payload
):
    """Form-decoding the query would corrupt '+' inside the code to a space."""
    mock_gateway.upsert_connection = AsyncMock(return_value=CREATED_CONNECTION)
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "create_ipaas_connection",
            {
                "pipe_id": "303088927",
                "piece_name": PIECE_NAME,
                "oauth": {
                    "completion": {
                        "type": "PLATFORM_OAUTH2",
                        "client_id": "c",
                        "redirect_url": "https://ipaas.test/redirect",
                    },
                    "authorization_response": (
                        "https://ipaas.test/redirect?code=ab+cd%2Fef=&state=x"
                    ),
                },
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    kwargs = mock_gateway.upsert_connection.await_args.kwargs
    assert kwargs["value"]["code"] == "ab+cd/ef="


@pytest.mark.anyio
async def test_create_connection_requires_one_mode(
    mock_client, mock_gateway, extract_payload
):
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "create_ipaas_connection",
            {"pipe_id": "303088927", "piece_name": PIECE_NAME},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "connection_type must be one of" in tool_error_message(payload)


@pytest.mark.anyio
async def test_create_connection_explicit_external_id_rotates(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.upsert_connection = AsyncMock(return_value=CREATED_CONNECTION)
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        await session.call_tool(
            "create_ipaas_connection",
            {
                "pipe_id": "303088927",
                "piece_name": PIECE_NAME,
                "connection_type": "SECRET_TEXT",
                "value": {"secret_text": "rotated"},
                "external_id": "existing-conn",
                "display_name": "Kept Name",
            },
        )

    kwargs = mock_gateway.upsert_connection.await_args.kwargs
    assert kwargs["external_id"] == "existing-conn"
    assert kwargs["display_name"] == "Kept Name"


@pytest.mark.anyio
async def test_connection_auth_url_relays_bundle_and_instructions(
    mock_client, mock_gateway, extract_payload
):
    mock_gateway.connection_auth_url = AsyncMock(
        return_value={
            "authorization_url": "https://third-party.test/consent?x=1",
            "completion": {"type": "PLATFORM_OAUTH2", "client_id": "c"},
        }
    )
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "get_ipaas_connection_auth_url",
            {"pipe_id": "303088927", "piece_name": PIECE_NAME},
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    mock_gateway.connection_auth_url.assert_awaited_once_with("embed-jwt", PIECE_NAME)
    assert "https://third-party.test/consent?x=1" in payload["result"]
    assert '"completion"' in payload["result"]
    assert "create_ipaas_connection" in payload["result"]


@pytest.mark.anyio
async def test_connection_auth_url_is_not_read_only(mock_client, mock_gateway):
    """Step 1 POSTs for a fresh single-use PKCE bundle, so it is not a pure read;
    hosted clients must not treat it as a cacheable read-only call."""
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        listed = await session.list_tools()

    by_name = {t.name: t for t in listed.tools}
    auth_url = by_name["get_ipaas_connection_auth_url"]
    assert auth_url.annotations is not None
    assert auth_url.annotations.read_only_hint is False
    # The discovery meta-tool stays a genuine read.
    assert by_name["get_ipaas_tools"].annotations.read_only_hint is True


@pytest.mark.anyio
async def test_connection_tools_report_unconfigured_gateway(
    mock_client, extract_payload
):
    server = build_ipaas_test_server(mock_client, gateway=None)
    async with _session(server) as session:
        result = await session.call_tool(
            "get_ipaas_connection_auth_url",
            {"pipe_id": "303088927", "piece_name": PIECE_NAME},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "disabled" in tool_error_message(payload)
