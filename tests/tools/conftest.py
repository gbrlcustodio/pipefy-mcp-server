"""Shared fixtures for tool tests."""

import json

import pytest


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
