"""Tests for iPaaS MCP tools (mocked PipefyClient and gateway)."""

from contextlib import asynccontextmanager
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import PipefyClient

from pipefy_mcp.auth import RequestScopedIdentity
from pipefy_mcp.core.ipaas_gateway import IpaasGateway, IpaasGatewayError
from pipefy_mcp.core.runtime import McpRuntime
from pipefy_mcp.core.tool_error_envelope import tool_error_message
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.ipaas_tools import IpaasTools

TOOLS = [
    {
        "name": "ap_create_flow",
        "description": "Create a new flow\n\nLonger guidance the compact list drops.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}},
    },
    {
        "name": "ap_list_flows",
        "description": "List flows in the current project",
        "inputSchema": {"type": "object"},
    },
]


def build_ipaas_test_server(client, gateway):
    """A FastMCP server whose runtime serves ``client`` and ``gateway``.

    Mirrors ``build_tool_test_server`` (tools/conftest.py) and additionally
    plants the iPaaS gateway on the runtime (the property reads the instance
    attribute the composition normally sets from settings).
    """

    @asynccontextmanager
    async def _lifespan(_app):
        runtime = McpRuntime(settings, RequestScopedIdentity())
        runtime.session_for_request = lambda _req: client
        runtime._ipaas_gateway = gateway
        yield runtime

    mcp = FastMCP("Pipefy iPaaS Tools Test", lifespan=_lifespan)
    IpaasTools.register(mcp)
    return mcp


@pytest.fixture
def mock_client():
    client = MagicMock(PipefyClient)
    client.get_advanced_automations_token = AsyncMock(return_value="embed-jwt")
    return client


@pytest.fixture
def mock_gateway():
    gateway = MagicMock(IpaasGateway)
    gateway.list_tools = AsyncMock(return_value=TOOLS)
    return gateway


def _session(server):
    return create_client_session(
        server, read_timeout_seconds=timedelta(seconds=10), raise_exceptions=True
    )


@pytest.mark.anyio
async def test_compact_catalog_lists_names_and_first_lines(
    mock_client, mock_gateway, extract_payload
):
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool("get_ipaas_tools", {"pipe_id": "303088927"})

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    mock_client.get_advanced_automations_token.assert_awaited_once_with("303088927")
    mock_gateway.list_tools.assert_awaited_once_with("embed-jwt")
    assert '"count": 2' in payload["result"]
    assert '"ap_create_flow"' in payload["result"]
    # Compact mode keeps the first description line and drops the schema.
    assert "Create a new flow" in payload["result"]
    assert "Longer guidance" not in payload["result"]
    assert "inputSchema" not in payload["result"]


@pytest.mark.anyio
async def test_tool_name_returns_full_schema(
    mock_client, mock_gateway, extract_payload
):
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "get_ipaas_tools", {"pipe_id": "303088927", "tool_name": "ap_create_flow"}
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    assert "inputSchema" in payload["result"]
    assert "Longer guidance" in payload["result"]
    assert "ap_list_flows" not in payload["result"]


@pytest.mark.anyio
async def test_unknown_tool_name_lists_available(
    mock_client, mock_gateway, extract_payload
):
    server = build_ipaas_test_server(mock_client, mock_gateway)
    async with _session(server) as session:
        result = await session.call_tool(
            "get_ipaas_tools", {"pipe_id": "303088927", "tool_name": "ap_nope"}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload)
    assert "ap_nope" in message
    assert "ap_create_flow" in message


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
                "tool_name": "ap_create_flow",
                "arguments": {"name": "My flow"},
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    mock_client.get_advanced_automations_token.assert_awaited_once_with("303088927")
    mock_gateway.call_tool.assert_awaited_once_with(
        "embed-jwt", "ap_create_flow", {"name": "My flow"}
    )
    # Text segments are joined and relayed in full.
    assert "flow created" in payload["result"]
    assert "id: flow-1" in payload["result"]
    assert '"ap_create_flow"' in payload["result"]


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
            {"pipe_id": "303088927", "tool_name": "ap_list_flows"},
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    mock_gateway.call_tool.assert_awaited_once_with("embed-jwt", "ap_list_flows", None)


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
            {"pipe_id": "303088927", "tool_name": "ap_delete_flow"},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "flow not found" in tool_error_message(payload)


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
            {"pipe_id": "303088927", "tool_name": "ap_get_run"},
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
            {"pipe_id": "303088927", "tool_name": "ap_create_flow"},
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
            {"pipe_id": "303088927", "tool_name": "ap_create_flow"},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "disabled" in tool_error_message(payload)
    mock_client.get_advanced_automations_token.assert_not_awaited()
