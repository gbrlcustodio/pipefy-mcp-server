"""Unit tests for the canonical tool_success helper (REQ-1)."""

from pipefy_mcp.tools.tool_error_envelope import tool_success


def test_minimal_call_returns_only_success_true() -> None:
    assert tool_success() == {"success": True}


def test_data_only() -> None:
    assert tool_success({"id": "42"}) == {"success": True, "data": {"id": "42"}}


def test_all_keys_present() -> None:
    out = tool_success({"items": []}, message="ok", pagination={"has_more": False})
    assert set(out.keys()) == {"success", "data", "message", "pagination"}
    assert out["success"] is True
    assert out["data"] == {"items": []}
    assert out["message"] == "ok"
    assert out["pagination"] == {"has_more": False}


def test_optional_keys_omitted_when_none() -> None:
    out = tool_success({"x": 1}, message=None, pagination=None)
    assert set(out.keys()) == {"success", "data"}
    assert "message" not in out
    assert "pagination" not in out


def test_data_none_is_omitted() -> None:
    out = tool_success(data=None, message="hello")
    assert set(out.keys()) == {"success", "message"}
    assert out == {"success": True, "message": "hello"}
