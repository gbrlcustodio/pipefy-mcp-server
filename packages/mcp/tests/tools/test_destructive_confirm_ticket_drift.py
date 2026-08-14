"""Live-registry drift guard for destructive confirmation (REQ-7).

Schema coverage is keyed to registered tools, not a hardcoded count. Identity
coverage captures ``resource_identity`` at the bound call site rather than
declaring an expected mapping.
"""

import sys
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
from pipefy_mcp.core.ipaas_gateway import IpaasGateway
from pipefy_mcp.core.runtime import McpRuntime
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.registry import ToolRegistry
from tools.conftest import _extract_payload_impl

PROTOCOL_KEYS = frozenset({"confirm", "confirmation_token", "debug"})
FAKE_IPAAS_TOOL_NAME = "demo_delete_flow"
SENTINEL_UUID = "00000000-0000-4000-8000-000000000001"
DRIFT_PREVIEW = {
    "success": False,
    "requires_confirmation": True,
    "confirmation_token": "drift",
}


def _schema_server():
    mcp = MCPServer("destructive-confirm-drift")
    registry = ToolRegistry(mcp=mcp)
    registry.register_tools()
    return mcp


def _listed_tools(mcp):
    return list(mcp._tool_manager.list_tools())


def _input_schema(tool):
    schema = getattr(tool, "parameters", None)
    if schema is None:
        schema = getattr(tool, "input_schema", None)
    assert schema is not None, f"{tool.name} has no input schema"
    return schema


def _schema_properties(schema):
    return schema.get("properties") or {}


def _is_destructive(tool):
    annotations = tool.annotations
    return annotations is not None and annotations.destructive_hint is True


def _required_identity_keys(schema):
    return set(schema.get("required") or []) - PROTOCOL_KEYS


def assert_identity_covers_required(tool_name, identity, required_keys):
    missing = sorted(set(required_keys) - set(identity))
    assert not missing, f"{tool_name} resource_identity missing required keys {missing}"


def _schema_type(spec):
    if not spec:
        return "string"
    declared = spec.get("type")
    if isinstance(declared, list):
        for item in declared:
            if item != "null":
                return item
        return "string"
    if declared:
        return declared
    for option in spec.get("anyOf") or spec.get("oneOf") or ():
        option_type = _schema_type(option)
        if option_type != "null":
            return option_type
    return "string"


def sentinel_for_property(name, spec):
    kind = _schema_type(spec)
    if kind in {"integer", "number"}:
        return 1
    if kind == "boolean":
        return False
    if kind == "array":
        return [sentinel_for_property(name, spec.get("items") or {})]
    if kind == "object":
        return {}
    if "uuid" in name.lower() or spec.get("format") == "uuid":
        return SENTINEL_UUID
    return "1"


def sentinel_arguments(tool_name, schema):
    properties = _schema_properties(schema)
    arguments = {
        key: sentinel_for_property(key, properties.get(key) or {})
        for key in _required_identity_keys(schema)
    }
    if tool_name == "call_ipaas_tool":
        arguments["tool_name"] = FAKE_IPAAS_TOOL_NAME
    return arguments


def _fake_client():
    client = MagicMock(PipefyClient)
    client.get_pipe = AsyncMock(
        return_value={"pipe": {"id": "1", "name": "Drift", "phases": []}}
    )
    client.get_card = AsyncMock(
        return_value={"card": {"title": "Drift", "pipe": {"name": "Drift"}}}
    )
    client.get_table = AsyncMock(return_value={"table": {"name": "Drift"}})
    client.get_advanced_automations_token = AsyncMock(return_value="embed-jwt")
    return client


def _fake_ipaas_gateway():
    gateway = MagicMock(IpaasGateway)

    @asynccontextmanager
    async def mcp_session(token):
        session = MagicMock()

        async def list_tools():
            return [
                {
                    "name": FAKE_IPAAS_TOOL_NAME,
                    "description": "Demo catalog entry",
                    "inputSchema": {"type": "object"},
                    "annotations": {"destructiveHint": True},
                }
            ]

        async def call_tool(name, arguments=None):
            return {"content": [{"type": "text", "text": "ok"}], "isError": False}

        session.list_tools = list_tools
        session.call_tool = call_tool
        yield session

    gateway.mcp_session = mcp_session
    return gateway


def _identity_server(client, gateway):
    @asynccontextmanager
    async def _lifespan(_app):
        runtime = McpRuntime(settings, RequestScopedIdentity())
        runtime.session_for_request = lambda _req: client
        runtime._ipaas_gateway = gateway
        yield runtime

    mcp = MCPServer("destructive-confirm-identity", lifespan=_lifespan)
    registry = ToolRegistry(mcp=mcp)
    registry.register_tools()
    return mcp


def _install_identity_capture(monkeypatch):
    captured = {}

    async def wrapper(*args, **kwargs):
        captured[kwargs["tool_name"]] = dict(kwargs["resource_identity"])
        return dict(DRIFT_PREVIEW)

    for name, module in list(sys.modules.items()):
        if not name.startswith("pipefy_mcp.tools."):
            continue
        if hasattr(module, "check_destructive_confirmation"):
            monkeypatch.setattr(module, "check_destructive_confirmation", wrapper)
    return captured


def _payload_or_result(result):
    try:
        return _extract_payload_impl(result)
    except AssertionError:
        return result


class TestDestructiveConfirmSchema:
    def test_destructive_hint_tools_declare_confirm_and_token(self):
        tools = _listed_tools(_schema_server())
        destructive = [tool for tool in tools if _is_destructive(tool)]
        assert destructive, "no destructiveHint=True tools registered"
        for tool in destructive:
            properties = _schema_properties(_input_schema(tool))
            assert "confirm" in properties, (
                f"{tool.name} missing confirm in input schema"
            )
            assert "confirmation_token" in properties, (
                f"{tool.name} missing confirmation_token in input schema"
            )

    def test_execute_graphql_declares_confirm_fields_without_hint(self):
        tools = {tool.name: tool for tool in _listed_tools(_schema_server())}
        tool = tools["execute_graphql"]
        hint = tool.annotations.destructive_hint if tool.annotations else None
        assert hint is not True
        properties = _schema_properties(_input_schema(tool))
        assert "confirm" in properties, (
            "execute_graphql missing confirm in input schema"
        )
        assert "confirmation_token" in properties, (
            "execute_graphql missing confirmation_token in input schema"
        )

    def test_non_destructive_tools_omit_confirmation_token(self):
        tools = _listed_tools(_schema_server())
        names = {tool.name for tool in tools}
        assert "unpublish_sub_portal" in names
        skip = {tool.name for tool in tools if _is_destructive(tool)}
        skip.add("execute_graphql")
        for tool in tools:
            if tool.name in skip:
                continue
            properties = _schema_properties(_input_schema(tool))
            assert "confirmation_token" not in properties, (
                f"{tool.name} must not list confirmation_token in input schema"
            )


class TestDestructiveConfirmIdentity:
    def test_incomplete_identity_fails_naming_the_missing_key(self):
        with pytest.raises(AssertionError, match="table_id") as caught:
            assert_identity_covers_required(
                "delete_table_field",
                {"field_id": "1"},
                {"field_id", "table_id"},
            )
        assert "delete_table_field" in str(caught.value)

    @pytest.mark.anyio
    async def test_captured_identity_covers_required_schema_keys(self, monkeypatch):
        mcp = _identity_server(_fake_client(), _fake_ipaas_gateway())
        captured = _install_identity_capture(monkeypatch)
        destructive = [tool for tool in _listed_tools(mcp) if _is_destructive(tool)]
        assert destructive, "no destructiveHint=True tools registered"
        async with create_client_session(
            mcp,
            read_timeout_seconds=timedelta(seconds=10),
            raise_exceptions=True,
        ) as session:
            for tool in destructive:
                arguments = sentinel_arguments(tool.name, _input_schema(tool))
                try:
                    result = await session.call_tool(tool.name, arguments)
                except Exception as exc:
                    raise AssertionError(
                        f"{tool.name} raised before the guard; arguments={arguments!r}"
                    ) from exc
                if tool.name not in captured:
                    raise AssertionError(
                        f"{tool.name} never called check_destructive_confirmation; "
                        f"arguments={arguments!r} payload={_payload_or_result(result)!r}"
                    )
                assert_identity_covers_required(
                    tool.name,
                    captured[tool.name],
                    _required_identity_keys(_input_schema(tool)),
                )
