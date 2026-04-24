"""Unit tests for pagination_helpers (REQ-4)."""

from pipefy_mcp.tools.pagination_helpers import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    build_pagination_info,
    validate_page_size,
)


def test_validate_page_size_none_returns_default():
    value, err = validate_page_size(None)
    assert value == DEFAULT_PAGE_SIZE == 50
    assert err is None


def test_validate_page_size_valid_int_passes_through():
    value, err = validate_page_size(100)
    assert value == 100
    assert err is None


def test_validate_page_size_above_max_returns_structured_error():
    value, err = validate_page_size(1000)
    assert value == 0
    assert err is not None
    assert err["success"] is False
    assert err["error"]["code"] == "INVALID_ARGUMENTS"
    assert err["error"]["details"] == {"min": 1, "max": 500, "provided": 1000}


def test_validate_page_size_below_1_returns_structured_error():
    value, err = validate_page_size(0)
    assert value == 0
    assert err is not None
    assert err["error"]["code"] == "INVALID_ARGUMENTS"
    assert err["error"]["details"] == {"min": 1, "max": 500, "provided": 0}


def test_validate_page_size_negative_returns_structured_error():
    value, err = validate_page_size(-5)
    assert value == 0
    assert err is not None
    assert err["error"]["code"] == "INVALID_ARGUMENTS"
    assert err["error"]["details"]["provided"] == -5


def test_validate_page_size_non_integer_returns_structured_error():
    value, err = validate_page_size("abc")  # type: ignore[arg-type]
    assert value == 0
    assert err is not None
    assert err["error"]["code"] == "INVALID_ARGUMENTS"
    # Non-int does not populate provided (no int to report).
    assert "message" in err["error"]


def test_validate_page_size_accepts_integer_string():
    # int("100") coerces successfully, so "100" is treated as 100.
    value, err = validate_page_size("100")  # type: ignore[arg-type]
    assert value == 100
    assert err is None


def test_validate_page_size_custom_max():
    value, err = validate_page_size(750, max_size=1000)
    assert value == 750
    assert err is None


def test_validate_page_size_custom_max_still_enforces_lower_bound():
    value, err = validate_page_size(0, max_size=1000)
    assert value == 0
    assert err is not None
    assert err["error"]["details"]["max"] == 1000


def test_validate_page_size_uses_arg_name_in_error():
    _, err = validate_page_size(9999, arg_name="first")
    assert err is not None
    assert "'first'" in err["error"]["message"]


def test_max_page_size_is_500():
    assert MAX_PAGE_SIZE == 500


def test_build_pagination_info_with_page_info():
    info = build_pagination_info(
        page_info={"hasNextPage": True, "endCursor": "xyz"},
        page_size=50,
    )
    assert info == {"has_more": True, "end_cursor": "xyz", "page_size": 50}


def test_build_pagination_info_without_page_info():
    info = build_pagination_info(page_info=None, page_size=50)
    assert info == {"has_more": False, "end_cursor": None, "page_size": 50}


def test_build_pagination_info_empty_page_info():
    info = build_pagination_info(page_info={}, page_size=25)
    # Empty dict is falsy — treated like absent pageInfo.
    assert info == {"has_more": False, "end_cursor": None, "page_size": 25}


def test_build_pagination_info_missing_next_page_key():
    info = build_pagination_info(
        page_info={"endCursor": "abc"},
        page_size=10,
    )
    assert info == {"has_more": False, "end_cursor": "abc", "page_size": 10}
