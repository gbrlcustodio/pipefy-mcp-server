"""Unit tests for pipe_tool_helpers.

Tests validate payload builders, error message mappers, and field filters
without invoking the MCP server or Pipefy client.
"""

import pytest

from pipefy_mcp.tools.pipe_tool_helpers import (
    FIND_CARDS_EMPTY_MESSAGE,
    UserCancelledError,
    _extract_error_strings,
    _extract_graphql_correlation_id,
    _extract_graphql_error_codes,
    _filter_editable_field_definitions,
    _filter_fields_by_definitions,
    _with_debug_suffix,
    build_add_card_comment_error_payload,
    build_add_card_comment_success_payload,
    build_delete_card_error_payload,
    build_delete_card_preview_payload,
    build_delete_card_success_payload,
    map_add_card_comment_error_to_message,
    map_delete_card_error_to_message,
)

# =============================================================================
# UserCancelledError
# =============================================================================


@pytest.mark.unit
def test_user_cancelled_error_is_exception():
    """UserCancelledError is a subclass of Exception."""
    assert issubclass(UserCancelledError, Exception)


@pytest.mark.unit
def test_user_cancelled_error_can_be_raised_and_caught():
    """UserCancelledError can be raised and caught by type."""
    with pytest.raises(UserCancelledError):
        raise UserCancelledError("cancelled")


# =============================================================================
# build_add_card_comment_success_payload
# =============================================================================


@pytest.mark.unit
def test_build_add_card_comment_success_payload_converts_comment_id_to_str():
    """Success payload uses string comment_id."""
    out = build_add_card_comment_success_payload(comment_id=12345)
    assert out == {"success": True, "comment_id": "12345"}


@pytest.mark.unit
def test_build_add_card_comment_success_payload_accepts_str_comment_id():
    """Success payload accepts string comment_id as-is."""
    out = build_add_card_comment_success_payload(comment_id="c_abc")
    assert out == {"success": True, "comment_id": "c_abc"}


# =============================================================================
# _extract_error_strings
# =============================================================================


@pytest.mark.unit
def test_extract_error_strings_empty_exception():
    """Empty exception string yields no messages."""
    exc = Exception("")
    assert _extract_error_strings(exc) == []


@pytest.mark.unit
def test_extract_error_strings_uses_str_exc():
    """Raw str(exc) is included when non-empty."""
    exc = Exception("something went wrong")
    assert _extract_error_strings(exc) == ["something went wrong"]


@pytest.mark.unit
def test_extract_error_strings_from_errors_list_dict_message():
    """Errors list with dict items extracts 'message'."""
    exc = Exception("outer")
    exc.errors = [{"message": "GraphQL error"}]
    result = _extract_error_strings(exc)
    assert "outer" in result
    assert "GraphQL error" in result


@pytest.mark.unit
def test_extract_error_strings_from_errors_list_string_items():
    """Errors list with string items includes them."""
    exc = Exception("outer")
    exc.errors = ["first", "second"]
    result = _extract_error_strings(exc)
    assert "outer" in result
    assert "first" in result
    assert "second" in result


@pytest.mark.unit
def test_extract_error_strings_skips_empty_message_and_blank_strings():
    """Dict with empty message or blank string items are skipped."""
    exc = Exception("")
    exc.errors = [{"message": ""}, {"message": "ok"}, ""]
    result = _extract_error_strings(exc)
    assert result == ["ok"]


# =============================================================================
# map_add_card_comment_error_to_message
# =============================================================================


@pytest.mark.unit
def test_map_add_card_comment_error_not_found():
    """Not-found markers map to card not found message."""
    exc = Exception("record not found")
    assert "Card not found" in map_add_card_comment_error_to_message(exc)
    assert "card_id" in map_add_card_comment_error_to_message(exc)


@pytest.mark.unit
def test_map_add_card_comment_error_permission():
    """Permission markers map to permission message."""
    exc = Exception("permission denied")
    assert "permission" in map_add_card_comment_error_to_message(exc).lower()


@pytest.mark.unit
def test_map_add_card_comment_error_invalid_input():
    """Invalid/validation markers map to invalid input message."""
    exc = Exception("validation failed")
    assert "Invalid input" in map_add_card_comment_error_to_message(exc)
    exc2 = Exception("field must be non-empty")
    assert "Invalid input" in map_add_card_comment_error_to_message(exc2)


@pytest.mark.unit
def test_map_add_card_comment_error_fallback():
    """Unknown errors map to generic retry message."""
    exc = Exception("network timeout")
    assert "Unexpected error" in map_add_card_comment_error_to_message(exc)
    assert "try again" in map_add_card_comment_error_to_message(exc)


@pytest.mark.unit
def test_map_add_card_comment_error_uses_errors_attribute():
    """Message mapping uses exc.errors when present."""
    exc = Exception("")
    exc.errors = [{"message": "Not authorized"}]
    assert "permission" in map_add_card_comment_error_to_message(exc).lower()


# =============================================================================
# build_add_card_comment_error_payload
# =============================================================================


@pytest.mark.unit
def test_build_add_card_comment_error_payload():
    """Error payload has success False and given message."""
    out = build_add_card_comment_error_payload(message="Something failed")
    assert out == {"success": False, "error": "Something failed"}


# =============================================================================
# build_delete_card_preview_payload
# =============================================================================


@pytest.mark.unit
def test_build_delete_card_preview_payload():
    """Preview payload includes requires_confirmation and card/pipe info."""
    out = build_delete_card_preview_payload(
        card_id=99, card_title="My Card", pipe_name="My Pipe"
    )
    assert out["success"] is False
    assert out["requires_confirmation"] is True
    assert out["card_id"] == 99
    assert out["card_title"] == "My Card"
    assert out["pipe_name"] == "My Pipe"
    assert "permanently delete" in out["message"]
    assert "confirm=True" in out["message"]


# =============================================================================
# build_delete_card_success_payload
# =============================================================================


@pytest.mark.unit
def test_build_delete_card_success_payload():
    """Success payload includes card and pipe info and confirmation message."""
    out = build_delete_card_success_payload(
        card_id=99, card_title="My Card", pipe_name="My Pipe"
    )
    assert out["success"] is True
    assert out["card_id"] == 99
    assert out["card_title"] == "My Card"
    assert out["pipe_name"] == "My Pipe"
    assert "permanently deleted" in out["message"]


# =============================================================================
# build_delete_card_error_payload
# =============================================================================


@pytest.mark.unit
def test_build_delete_card_error_payload():
    """Error payload has success False and given message."""
    out = build_delete_card_error_payload(message="Delete failed")
    assert out == {"success": False, "error": "Delete failed"}


# =============================================================================
# _filter_editable_field_definitions
# =============================================================================


@pytest.mark.unit
def test_filter_editable_field_definitions_empty_list():
    """Empty list returns empty list."""
    assert _filter_editable_field_definitions([]) == []


@pytest.mark.unit
def test_filter_editable_field_definitions_editable_true_included():
    """Field with editable=True is included."""
    fields = [{"id": "f1", "label": "A", "editable": True}]
    assert _filter_editable_field_definitions(fields) == fields


@pytest.mark.unit
def test_filter_editable_field_definitions_editable_false_excluded():
    """Field with editable=False is excluded."""
    fields = [
        {"id": "f1", "editable": True},
        {"id": "f2", "editable": False},
    ]
    result = _filter_editable_field_definitions(fields)
    assert result == [{"id": "f1", "editable": True}]


@pytest.mark.unit
def test_filter_editable_field_definitions_default_editable():
    """Field without 'editable' key is included (default True)."""
    fields = [{"id": "f1", "label": "X"}]
    assert _filter_editable_field_definitions(fields) == fields


@pytest.mark.unit
def test_filter_editable_field_definitions_skips_non_dict():
    """Non-dict items in list are skipped."""
    fields = [{"id": "f1"}, "not a dict", None, {"id": "f2"}]
    result = _filter_editable_field_definitions(fields)
    assert result == [{"id": "f1"}, {"id": "f2"}]


# =============================================================================
# _filter_fields_by_definitions
# =============================================================================


@pytest.mark.unit
def test_filter_fields_by_definitions_none_returns_empty():
    """None fields returns empty dict."""
    defs = [{"id": "a"}]
    assert _filter_fields_by_definitions(None, defs) == {}


@pytest.mark.unit
def test_filter_fields_by_definitions_empty_returns_empty():
    """Empty fields returns empty dict."""
    defs = [{"id": "a"}]
    assert _filter_fields_by_definitions({}, defs) == {}


@pytest.mark.unit
def test_filter_fields_by_definitions_keeps_only_editable_ids():
    """Only field IDs present in definitions are kept."""
    fields = {"a": 1, "b": 2, "c": 3}
    defs = [{"id": "a"}, {"id": "c"}]
    result = _filter_fields_by_definitions(fields, defs)
    assert result == {"a": 1, "c": 3}


# =============================================================================
# _extract_graphql_error_codes
# =============================================================================


@pytest.mark.unit
def test_extract_graphql_error_codes_no_errors():
    """Exception without errors attribute returns empty list."""
    exc = Exception("foo")
    assert _extract_graphql_error_codes(exc) == []


@pytest.mark.unit
def test_extract_graphql_error_codes_from_extensions():
    """Codes are extracted from errors[].extensions.code."""
    exc = Exception("")
    exc.errors = [
        {"extensions": {"code": "RESOURCE_NOT_FOUND"}},
        {"extensions": {"code": "PERMISSION_DENIED"}},
    ]
    assert _extract_graphql_error_codes(exc) == [
        "RESOURCE_NOT_FOUND",
        "PERMISSION_DENIED",
    ]


@pytest.mark.unit
def test_extract_graphql_error_codes_skips_invalid_items():
    """Non-dict items and missing extensions/code are skipped."""
    exc = Exception("")
    exc.errors = [
        {"extensions": {"code": "OK"}},
        "string",
        {"extensions": None},
        {"extensions": {"code": ""}},
    ]
    assert _extract_graphql_error_codes(exc) == ["OK"]


@pytest.mark.unit
def test_extract_graphql_error_codes_from_string_regex():
    """Codes are parsed from exception string when extensions missing."""
    exc = Exception('{"code": "CUSTOM_CODE"}')
    result = _extract_graphql_error_codes(exc)
    assert "CUSTOM_CODE" in result


@pytest.mark.unit
def test_extract_graphql_error_codes_dedup_preserves_order():
    """Duplicate codes are removed, order preserved."""
    exc = Exception("")
    exc.errors = [
        {"extensions": {"code": "A"}},
        {"extensions": {"code": "B"}},
        {"extensions": {"code": "A"}},
    ]
    assert _extract_graphql_error_codes(exc) == ["A", "B"]


# =============================================================================
# _extract_graphql_correlation_id
# =============================================================================


@pytest.mark.unit
def test_extract_graphql_correlation_id_empty_string_returns_none():
    """Empty exception string returns None."""
    exc = Exception("")
    assert _extract_graphql_correlation_id(exc) is None


@pytest.mark.unit
def test_extract_graphql_correlation_id_no_match_returns_none():
    """String without correlation_id pattern returns None."""
    exc = Exception("some error")
    assert _extract_graphql_correlation_id(exc) is None


@pytest.mark.unit
def test_extract_graphql_correlation_id_extracts_value():
    """Correlation ID is extracted from string."""
    exc = Exception('{"correlation_id": "abc-123"}')
    assert _extract_graphql_correlation_id(exc) == "abc-123"


# =============================================================================
# _with_debug_suffix
# =============================================================================


@pytest.mark.unit
def test_with_debug_suffix_debug_false_returns_message_unchanged():
    """When debug=False, message is returned unchanged."""
    msg = "Something failed"
    assert _with_debug_suffix(msg, debug=False, codes=[], correlation_id=None) == msg


@pytest.mark.unit
def test_with_debug_suffix_debug_true_with_codes_and_correlation_id():
    """When debug=True, codes and correlation_id are appended."""
    msg = "Error"
    result = _with_debug_suffix(
        msg,
        debug=True,
        codes=["A", "B"],
        correlation_id="corr-1",
    )
    assert result.startswith("Error")
    assert "codes=A,B" in result
    assert "correlation_id=corr-1" in result


@pytest.mark.unit
def test_with_debug_suffix_debug_true_empty_parts_returns_message():
    """When debug=True but no codes or correlation_id, message unchanged."""
    msg = "Error"
    result = _with_debug_suffix(msg, debug=True, codes=[], correlation_id=None)
    assert result == msg


# =============================================================================
# map_delete_card_error_to_message
# =============================================================================


@pytest.mark.unit
def test_map_delete_card_error_resource_not_found():
    """RESOURCE_NOT_FOUND maps to card not found message."""
    msg = map_delete_card_error_to_message(
        card_id=42, card_title="X", codes=["RESOURCE_NOT_FOUND"]
    )
    assert "not found" in msg
    assert "42" in msg


@pytest.mark.unit
def test_map_delete_card_error_permission_denied():
    """PERMISSION_DENIED maps to permission message."""
    msg = map_delete_card_error_to_message(
        card_id=42, card_title="X", codes=["PERMISSION_DENIED"]
    )
    assert "permission" in msg.lower()
    assert "42" in msg


@pytest.mark.unit
def test_map_delete_card_error_record_not_destroyed():
    """RECORD_NOT_DESTROYED maps to try again message."""
    msg = map_delete_card_error_to_message(
        card_id=42, card_title="My Card", codes=["RECORD_NOT_DESTROYED"]
    )
    assert "Failed to delete" in msg
    assert "My Card" in msg
    assert "try again" in msg or "support" in msg


@pytest.mark.unit
def test_map_delete_card_error_unknown_codes_returns_codes_in_message():
    """Unknown codes are listed in the message."""
    msg = map_delete_card_error_to_message(
        card_id=1, card_title="T", codes=["UNKNOWN_CODE", "OTHER"]
    )
    assert "UNKNOWN_CODE" in msg
    assert "OTHER" in msg
    assert "T" in msg


@pytest.mark.unit
def test_map_delete_card_error_empty_codes_fallback():
    """Empty codes list returns generic try again message."""
    msg = map_delete_card_error_to_message(card_id=99, card_title="Card", codes=[])
    assert "Failed to delete" in msg
    assert "Card" in msg
    assert "try again" in msg or "support" in msg


# =============================================================================
# FIND_CARDS_EMPTY_MESSAGE
# =============================================================================


@pytest.mark.unit
def test_find_cards_empty_message_constant():
    """FIND_CARDS_EMPTY_MESSAGE is the expected string."""
    assert FIND_CARDS_EMPTY_MESSAGE == "No cards found for this field/value."
