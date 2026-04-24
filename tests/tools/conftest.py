"""Shared fixtures for tool tests."""

import json

import pytest

from pipefy_mcp.settings import settings


@pytest.fixture
def legacy_envelope(monkeypatch):
    """Force the legacy (pre-unified) success shape by disabling the flag.

    Use this in tests that assert byte-identical pre-PR output from a migrated
    helper or tool. Without it, the default-TRUE ``PIPEFY_MCP_UNIFIED_ENVELOPE``
    causes migrated helpers to emit the unified ``{success, data, message?}`` shape.
    """
    monkeypatch.setattr(settings.pipefy, "mcp_unified_envelope", False)
    return False


@pytest.fixture
def unified_envelope(monkeypatch):
    """Force the unified envelope shape (explicit, not relying on default)."""
    monkeypatch.setattr(settings.pipefy, "mcp_unified_envelope", True)
    return True


@pytest.fixture(params=[True, False], ids=["flag-on", "flag-off"])
def envelope_flag(request, monkeypatch):
    """Parametrize a test across both flag states via monkeypatch.

    Tests that use this fixture receive the current flag value as ``envelope_flag``
    and run twice — once with ``True`` (unified) and once with ``False`` (legacy).
    """
    monkeypatch.setattr(settings.pipefy, "mcp_unified_envelope", request.param)
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
