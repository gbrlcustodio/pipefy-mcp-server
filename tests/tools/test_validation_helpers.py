"""Unit tests for shared MCP tool validation helpers."""

import pytest

from pipefy_mcp.tools.tool_error_envelope import tool_error_message
from pipefy_mcp.tools.validation_helpers import (
    format_json_preview,
    mutation_error_if_not_optional_dict,
    valid_repo_id,
    validate_optional_tool_id,
    validate_tool_id,
)


@pytest.mark.unit
def test_format_json_preview_pretty_and_utf8():
    s = format_json_preview({"a": 1, "ç": "β"})
    assert '"a": 1' in s
    assert "ç" in s
    assert "β" in s
    assert "\n" in s


@pytest.mark.unit
def test_valid_repo_id_positive_int_and_non_empty_str():
    assert valid_repo_id(1) is True
    assert valid_repo_id("abc") is True
    assert valid_repo_id("  x  ") is True


@pytest.mark.unit
def test_valid_repo_id_rejects_zero_negative_empty_and_other_types():
    assert valid_repo_id(0) is False
    assert valid_repo_id(-1) is False
    assert valid_repo_id("") is False
    assert valid_repo_id("   ") is False
    assert valid_repo_id(None) is False
    assert valid_repo_id([1]) is False


@pytest.mark.unit
def test_mutation_error_if_not_optional_dict_none_and_dict_ok():
    assert mutation_error_if_not_optional_dict(None, arg_name="extra_input") is None
    assert mutation_error_if_not_optional_dict({}, arg_name="extra_input") is None
    assert mutation_error_if_not_optional_dict({"a": 1}, arg_name="x") is None


@pytest.mark.unit
def test_mutation_error_if_not_optional_dict_rejects_non_mapping():
    err = mutation_error_if_not_optional_dict("x", arg_name="extra_input")
    assert err is not None
    assert err["success"] is False
    assert "extra_input" in tool_error_message(err)
    err_list = mutation_error_if_not_optional_dict([], arg_name="extra_input")
    assert err_list is not None
    assert err_list["success"] is False


@pytest.mark.unit
class TestValidateToolId:
    def test_positive_int_coerced_to_str(self):
        val, err = validate_tool_id(42, "card_id")
        assert val == "42"
        assert err is None

    def test_non_empty_str_passes(self):
        val, err = validate_tool_id("abc-123", "pipe_id")
        assert val == "abc-123"
        assert err is None

    def test_str_is_stripped(self):
        val, err = validate_tool_id("  99  ", "id")
        assert val == "99"
        assert err is None

    def test_rejects_empty_str(self):
        val, err = validate_tool_id("", "card_id")
        assert val is None
        assert err["success"] is False
        assert "card_id" in tool_error_message(err)

    def test_rejects_whitespace_only(self):
        val, err = validate_tool_id("   ", "card_id")
        assert val is None
        assert err["success"] is False

    def test_rejects_zero(self):
        val, err = validate_tool_id(0, "card_id")
        assert val is None
        assert err["success"] is False

    def test_rejects_negative_int(self):
        val, err = validate_tool_id(-1, "card_id")
        assert val is None
        assert err["success"] is False

    def test_rejects_negative_str(self):
        val, err = validate_tool_id("-5", "card_id")
        assert val is None
        assert err["success"] is False

    def test_rejects_bool(self):
        val, err = validate_tool_id(True, "card_id")
        assert val is None
        assert err["success"] is False


@pytest.mark.unit
class TestValidateOptionalToolId:
    def test_none_passes_through(self):
        ok, val, err = validate_optional_tool_id(None, "org_id")
        assert ok is True
        assert val is None
        assert err is None

    def test_valid_value_cleaned(self):
        ok, val, err = validate_optional_tool_id("  42  ", "org_id")
        assert ok is True
        assert val == "42"
        assert err is None

    def test_invalid_returns_error(self):
        ok, val, err = validate_optional_tool_id("", "org_id")
        assert ok is False
        assert val is None
        assert err["success"] is False
        assert "org_id" in tool_error_message(err)
