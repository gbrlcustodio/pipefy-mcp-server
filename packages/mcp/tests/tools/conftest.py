"""Shared fixtures for tool tests."""

import json
from contextlib import asynccontextmanager

import pytest
from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.runtime import McpRuntime, RequestScopedIdentity
from pipefy_mcp.settings import settings


def build_tool_test_server(name, register, client):
    """Build a FastMCP server whose lifespan yields a runtime serving ``client``.

    Tools resolve their client per request from the ``lifespan_context`` by calling
    :meth:`McpRuntime.session_for_request` (see
    :func:`pipefy_mcp.tools.tool_context.get_pipefy_client`), so a test injects its
    mock by overriding that method to return ``client``. The request-scoped source
    resolves no credential at construction (no keychain or network I/O), so the
    runtime builds cleanly before the override lands. ``register`` is a tool
    group's ``register`` staticmethod, called with the app alone.
    """

    @asynccontextmanager
    async def _lifespan(_app):
        runtime = McpRuntime(settings, RequestScopedIdentity())
        runtime.session_for_request = lambda *_: client
        yield runtime

    mcp = FastMCP(name, lifespan=_lifespan)
    register(mcp)
    return mcp


@pytest.fixture
def legacy_envelope(monkeypatch):
    """Disable unified envelope (``PIPEFY_MCP_UNIFIED_ENVELOPE`` off)."""
    monkeypatch.setattr(settings.mcp, "unified_envelope", False)
    return False


@pytest.fixture
def unified_envelope(monkeypatch):
    """Enable unified envelope (explicit)."""
    monkeypatch.setattr(settings.mcp, "unified_envelope", True)
    return True


@pytest.fixture(params=[True, False], ids=["flag-on", "flag-off"])
def envelope_flag(request, monkeypatch):
    """Runs the test twice: unified envelope on, then off."""
    monkeypatch.setattr(settings.mcp, "unified_envelope", request.param)
    return request.param


def _extract_payload_impl(result):
    """Extract tool payload from CallToolResult across MCP SDK versions."""
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        if isinstance(structured, dict) and "result" in structured:
            payload = structured.get("result")
            if isinstance(payload, dict):
                if "success" in payload or "error" in payload:
                    return payload
                if "success" in structured or "error" in structured:
                    return structured
                return payload
        if isinstance(structured, dict):
            return structured
    content = getattr(result, "content", None) or []
    for item in content:
        if getattr(item, "type", None) == "text":
            text = getattr(item, "text", "")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    raise AssertionError("Could not extract tool payload from CallToolResult")


@pytest.fixture
def extract_payload():
    """Return the shared extractor as a callable fixture (back-compat)."""
    return _extract_payload_impl


def assert_invalid_arguments_envelope(result):
    """Assert a ``CallToolResult`` carries a Pipefy ``INVALID_ARGUMENTS`` envelope.

    Use this for cases where FastMCP's argument coercion rejects the input
    (missing required arg, wrong type, ``@field_validator`` rejecting blank /
    empty strings). The envelope is produced by
    :class:`pipefy_mcp.tools.validation_envelope.PipefyValidationTool` and is
    delivered as a structured success payload (``isError == False``), not as a
    transport-level error.
    """
    assert result.isError is False, (
        "Expected a tool-error envelope (isError=False), got a transport error: "
        f"{result}"
    )
    payload = _extract_payload_impl(result)
    assert payload.get("success") is False, (
        f"Expected envelope success=False, got payload: {payload!r}"
    )
    error = payload.get("error") or {}
    assert error.get("code") == "INVALID_ARGUMENTS", (
        f"Expected error.code=INVALID_ARGUMENTS, got payload: {payload!r}"
    )
    return payload
