"""Unit tests for canonical tool error helpers."""

from pipefy_mcp.tools.tool_error_envelope import (
    tool_error,
    tool_error_message,
)


def test_tool_error_includes_message_and_optional_code() -> None:
    out = tool_error("nope", code="E_BAD")
    assert out == {
        "success": False,
        "error": {"message": "nope", "code": "E_BAD"},
    }


def test_tool_error_message_from_structured() -> None:
    assert tool_error_message({"success": False, "error": {"message": "x"}}) == "x"


def test_tool_error_message_legacy_string() -> None:
    assert tool_error_message({"success": False, "error": "plain"}) == "plain"
