"""Unit tests for shared MCP tool validation helpers."""

import pytest

from pipefy_mcp.tools.validation_helpers import (
    format_json_preview,
    mutation_error_if_not_optional_dict,
    valid_repo_id,
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
    assert "extra_input" in err["error"]
    err_list = mutation_error_if_not_optional_dict([], arg_name="extra_input")
    assert err_list is not None
    assert err_list["success"] is False
