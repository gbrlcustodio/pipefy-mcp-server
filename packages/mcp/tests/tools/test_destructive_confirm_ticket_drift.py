"""Live-registry drift guard for destructive confirmation (REQ-7).

Schema coverage is keyed to registered tools, not a hardcoded count. Identity
coverage captures ``resource_identity`` at the bound call site rather than
declaring an expected mapping.
"""

import ast
import sys
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
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
from pipefy_mcp.tools.ipaas_tools import IPAAS_DESTRUCTIVE_NEEDLES
from pipefy_mcp.tools.registry import ToolRegistry
from tools.conftest import extract_tool_payload

PROTOCOL_KEYS = frozenset({"confirm", "confirmation_token", "debug"})
# Optional selectors that reach a mutation are not in this set; bind them in
# resource_identity (today: delete_phase_field.pipe_uuid). "Required" here is
# the schema required list, so an optional selector is invisible to the walk.

# A destructive needle in the name that the tool does not act on. Keep empty
# unless a tool genuinely reads as destructive while doing something else.
DESTRUCTIVELY_NAMED_BUT_NOT_DESTRUCTIVE = frozenset()
# The reads every destructive tool is allowed to run before consulting the
# guard, so a preview can describe what would be destroyed.
PRE_GUARD_CLIENT_READS = frozenset(
    {
        "get_pipe",
        "get_card",
        "get_table",
        "get_advanced_automations_token",
    }
)
FAKE_IPAAS_TOOL_NAME = "demo_delete_flow"
SENTINEL_UUID = "00000000-0000-4000-8000-000000000001"
DRIFT_PREVIEW = {
    "success": False,
    "requires_confirmation": True,
    "confirmation_token": "drift",
}
_TOOLS_DIR = Path(__file__).resolve().parents[2] / "src" / "pipefy_mcp" / "tools"
_GUARD_CALL = "check_destructive_confirmation"
_CLIENT_CALL = "get_pipefy_client"
_IPAAS_PREAMBLE = "_run_ipaas_tool"


def _call_name(node):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _iter_direct_calls(func_node):
    def walk(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return
        if isinstance(node, ast.Call):
            yield node
        for child in ast.iter_child_nodes(node):
            yield from walk(child)

    for stmt in func_node.body:
        yield from walk(stmt)


def _first_direct_call_lineno(func_node, name):
    for call in _iter_direct_calls(func_node):
        if _call_name(call) == name:
            return call.lineno
    return None


def _parents(tree):
    mapping = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            mapping[child] = node
    return mapping


def _enclosing_functions(node, parents):
    funcs = []
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(current)
        current = parents.get(current)
    return funcs


def _tool_modules():
    return sorted(
        path for path in _TOOLS_DIR.glob("*.py") if path.name != "__init__.py"
    )


def _run_ipaas_tool_function():
    path = _TOOLS_DIR / "ipaas_tools.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == _IPAAS_PREAMBLE
        ):
            return node
    raise AssertionError(f"{_IPAAS_PREAMBLE} not found in {path}")


def _guard_sites_without_prior_client():
    offenders = []
    for path in _tool_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = _parents(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) != _GUARD_CALL:
                continue
            enclosing = _enclosing_functions(node, parents)
            if not enclosing:
                offenders.append(f"{path.name}:{node.lineno} (no enclosing function)")
                continue
            innermost = enclosing[0]
            client_line = _first_direct_call_lineno(innermost, _CLIENT_CALL)
            if client_line is not None and client_line < node.lineno:
                continue
            if any(
                _first_direct_call_lineno(func, _IPAAS_PREAMBLE) is not None
                for func in enclosing
            ):
                continue
            offenders.append(f"{path.name}:{innermost.name}:{node.lineno}")
    return offenders


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


def _identity_value_matches_sentinel(got, sent):
    if got == sent:
        return True
    if isinstance(sent, bool) or isinstance(got, bool):
        return False
    if isinstance(sent, (int, float)) and got == str(sent):
        return True
    if isinstance(got, (int, float)) and sent == str(got):
        return True
    if isinstance(sent, list) and isinstance(got, list):
        return len(sent) == len(got) and all(
            _identity_value_matches_sentinel(item_got, item_sent)
            for item_got, item_sent in zip(got, sent, strict=True)
        )
    return False


def assert_identity_values_match_sentinels(
    tool_name, identity, arguments, required_keys
):
    mismatches = []
    for key in sorted(required_keys):
        sent = arguments[key]
        got = identity[key]
        if not _identity_value_matches_sentinel(got, sent):
            mismatches.append(f"{key}: sent {sent!r} got {got!r}")
    assert not mismatches, (
        f"{tool_name} resource_identity values do not match sentinels: {mismatches}"
    )


def assert_preview_honors_guard(tool_name, result):
    payload = _payload_or_result(result)
    token = payload.get("confirmation_token") if isinstance(payload, dict) else None
    requires = (
        payload.get("requires_confirmation") if isinstance(payload, dict) else None
    )
    assert token == DRIFT_PREVIEW["confirmation_token"], (
        f"{tool_name} discarded the guard preview; confirmation_token={token!r}, "
        f"expected {DRIFT_PREVIEW['confirmation_token']!r}"
    )
    assert requires is True, (
        f"{tool_name} discarded the guard preview; requires_confirmation={requires!r}"
    )


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
        return extract_tool_payload(result)
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

    def test_destructively_named_tools_carry_destructive_hint(self):
        """Every frozen needle, in any position, not only the two prefixes.

        A tool named for destruction but registered without the hint is
        invisible to every other check here, since they all walk the hinted set.
        """
        unhinted = [
            tool.name
            for tool in _listed_tools(_schema_server())
            if any(needle in tool.name.lower() for needle in IPAAS_DESTRUCTIVE_NEEDLES)
            and tool.name not in DESTRUCTIVELY_NAMED_BUT_NOT_DESTRUCTIVE
            and not _is_destructive(tool)
        ]
        assert not unhinted, (
            f"tools named for destruction must set destructiveHint=True: {unhinted}"
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
                required_keys = _required_identity_keys(_input_schema(tool))
                assert_identity_covers_required(
                    tool.name,
                    captured[tool.name],
                    required_keys,
                )
                assert_identity_values_match_sentinels(
                    tool.name,
                    captured[tool.name],
                    arguments,
                    required_keys,
                )
                assert_preview_honors_guard(tool.name, result)

    @pytest.mark.anyio
    async def test_no_destructive_tool_writes_before_consulting_the_guard(self):
        """A preview must describe the deletion, never perform part of it.

        The identity walk proves the guard was consulted and its verdict
        returned. It cannot see a tool that deletes first and previews after,
        which would pass every other check here.
        """
        client = _fake_client()
        mcp = _identity_server(client, _fake_ipaas_gateway())
        destructive = [tool for tool in _listed_tools(mcp) if _is_destructive(tool)]
        assert destructive, "no destructiveHint=True tools registered"
        async with create_client_session(
            mcp,
            read_timeout_seconds=timedelta(seconds=10),
            raise_exceptions=True,
        ) as session:
            for tool in destructive:
                client.reset_mock()
                arguments = sentinel_arguments(tool.name, _input_schema(tool))
                await session.call_tool(tool.name, arguments)
                called = {
                    name.split(".")[0] for name, _args, _kwargs in client.mock_calls
                }
                unexpected = {name for name in called if name} - PRE_GUARD_CLIENT_READS
                assert not unexpected, (
                    f"{tool.name} called {sorted(unexpected)} on the default "
                    "confirm=False preview; a preview must not reach the API "
                    "beyond the reads that describe the resource"
                )

    def test_gated_call_sites_resolve_the_client_before_the_guard(self):
        """Hosted signing is sha256(bearer); the process-key fallback is dead
        only because every gated tool calls get_pipefy_client first.

        Move a guard call above that resolve and a preview minted on one
        replica fails to verify on another, reported as invalid_or_expired.
        """
        offenders = _guard_sites_without_prior_client()
        assert not offenders, (
            "check_destructive_confirmation must follow get_pipefy_client "
            f"in the same function, or sit behind _run_ipaas_tool: {offenders}"
        )

    def test_ipaas_preamble_resolves_the_client_before_work(self):
        """call_ipaas_tool's nested work() has no get_pipefy_client of its own.

        That is only safe while _run_ipaas_tool still resolves the client
        before invoking work.
        """
        preamble = _run_ipaas_tool_function()
        client_line = _first_direct_call_lineno(preamble, "get_pipefy_client")
        work_line = _first_direct_call_lineno(preamble, "work")
        assert client_line is not None, "_run_ipaas_tool never calls get_pipefy_client"
        assert work_line is not None, "_run_ipaas_tool never calls work"
        assert client_line < work_line, (
            f"_run_ipaas_tool calls work at line {work_line} before "
            f"get_pipefy_client at line {client_line}"
        )
