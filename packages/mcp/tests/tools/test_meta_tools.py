"""Behavior of the ``power``-profile catalog meta-tools.

The meta-tools close over a catalog snapshot; here we build a real catalog from a
registered ``ToolRegistry`` and invoke each meta-tool's underlying function. The
validation-error and not-found paths never reach a Pipefy client, so no runtime is
needed.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from _mcp_compat import (
    create_connected_server_and_client_session as create_client_session,
)
from mcp.server.mcpserver import MCPServer
from pipefy_sdk import PipefyClient

from pipefy_mcp.tools.meta_tools import register_meta_tools
from pipefy_mcp.tools.registry import ToolRegistry
from pipefy_mcp.tools.toolsets import DOMAINS, POWER_GRAPHQL_TOOLS
from pipefy_mcp.tools.validation_envelope import install_pipefy_validation_envelope
from pipefy_mcp.tools.webhook_tools import WebhookTools
from tools.conftest import build_tool_test_server

_META_TOOLS = ("get_tool_categories", "search_tools", "describe_tool", "execute_tool")


def _catalog(*, remote: bool = False) -> dict:
    """A catalog snapshot of the registered Pipefy tools (optionally post-floor)."""
    install_pipefy_validation_envelope()
    mcp = MCPServer("catalog-source")
    registry = ToolRegistry(mcp=mcp)
    registry.register_tools()
    if remote:
        registry.apply_remote_profile(remote_mode=True)
    return {
        tool.name: tool
        for tool in mcp._tool_manager.list_tools()
        if tool.name in registry.pipefy_tool_names
        and tool.name not in POWER_GRAPHQL_TOOLS
    }


def _meta_fns(catalog: dict) -> dict:
    """Register the meta-tools over ``catalog`` and return their callables by name."""
    host = MCPServer("meta-host")
    register_meta_tools(host, catalog)
    return {name: host._tool_manager._tools[name].fn for name in _META_TOOLS}


class TestGetToolCategories:
    async def test_lists_every_populated_domain_with_a_description(self):
        fns = _meta_fns(_catalog())
        result = await fns["get_tool_categories"]()
        assert result["success"] is True
        categories = {c["category"]: c for c in result["data"]["categories"]}
        # A full catalog populates every domain.
        assert set(categories) == set(DOMAINS)
        assert all(c["description"] for c in categories.values())
        assert "get_pipe" in categories["workflow"]["tools"]


class TestSearchTools:
    async def test_finds_matches_and_ranks_name_hits(self):
        fns = _meta_fns(_catalog())
        result = await fns["search_tools"]("pipe")
        assert result["success"] is True
        names = [t["name"] for t in result["data"]["tools"]]
        assert "get_pipe" in names  # a name match surfaces
        assert result["data"]["count"] == len(names)
        assert len(names) <= 25  # capped

    async def test_no_match_returns_empty(self):
        fns = _meta_fns(_catalog())
        result = await fns["search_tools"]("zzz_no_such_tool")
        assert result["success"] is True
        assert result["data"]["count"] == 0


class TestDescribeTool:
    async def test_returns_schema_and_category(self):
        fns = _meta_fns(_catalog())
        result = await fns["describe_tool"]("get_pipe")
        assert result["success"] is True
        assert result["data"]["category"] == "workflow"
        assert "pipe_id" in result["data"]["input_schema"]["properties"]

    async def test_unknown_name_is_an_error(self):
        fns = _meta_fns(_catalog())
        result = await fns["describe_tool"]("not_a_tool")
        assert result["success"] is False
        assert result["error"]["code"] == "TOOL_NOT_FOUND"


class TestExecuteTool:
    async def test_unknown_name_is_an_error(self):
        fns = _meta_fns(_catalog())
        result = await fns["execute_tool"]("not_a_tool", None, {})
        assert result["success"] is False
        assert result["error"]["code"] == "TOOL_NOT_FOUND"

    async def test_dispatches_through_argument_validation(self):
        """Missing required args come back as the standard invalid-arguments envelope."""
        fns = _meta_fns(_catalog())
        result = await fns["execute_tool"]("get_pipe", None, {})  # missing pipe_id
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ARGUMENTS"

    async def test_cannot_reach_a_floor_withheld_tool(self):
        """A tool the remote floor withheld is absent from the catalog, so unreachable."""
        fns = _meta_fns(_catalog(remote=True))
        result = await fns["execute_tool"]("create_llm_provider", None, {})
        assert result["success"] is False
        assert result["error"]["code"] == "TOOL_NOT_FOUND"


@pytest.mark.anyio
async def test_execute_tool_passes_destructive_two_step_through(extract_payload):
    """Power-profile deletes are reachable only via execute_tool; arguments pass through."""
    client = MagicMock(PipefyClient)
    client.delete_webhook = AsyncMock(return_value={"deleteWebhook": {"success": True}})
    server = build_tool_test_server("power-passthrough", WebhookTools.register, client)
    catalog = {
        tool.name: tool
        for tool in server._tool_manager.list_tools()
        if tool.name == "delete_webhook"
    }
    assert catalog, "delete_webhook not registered"
    register_meta_tools(server, catalog)

    async with create_client_session(
        server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    ) as session:
        preview_result = await session.call_tool(
            "execute_tool",
            {"name": "delete_webhook", "arguments": {"webhook_id": "wh-1"}},
        )
        preview = extract_payload(preview_result)
        assert preview["success"] is False
        assert preview["requires_confirmation"] is True
        token = preview["confirmation_token"]
        assert isinstance(token, str) and token.startswith("v1.")
        assert token in preview["message"]
        client.delete_webhook.assert_not_called()

        confirm_result = await session.call_tool(
            "execute_tool",
            {
                "name": "delete_webhook",
                "arguments": {
                    "webhook_id": "wh-1",
                    "confirm": True,
                    "confirmation_token": token,
                },
            },
        )
        confirmed = extract_payload(confirm_result)
        assert confirmed.get("success") is True, confirmed
        client.delete_webhook.assert_awaited_once_with("wh-1")
