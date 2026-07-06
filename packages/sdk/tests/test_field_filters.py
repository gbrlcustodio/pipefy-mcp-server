"""Tests for ``pipefy_sdk.field_filters``."""

from __future__ import annotations

from pipefy_sdk.field_filters import (
    filter_editable_field_definitions,
    filter_fields_by_definitions,
    skipped_field_ids,
)


def test_filter_editable_field_definitions_empty_list() -> None:
    assert filter_editable_field_definitions([]) == []


def test_filter_editable_field_definitions_editable_true_included() -> None:
    fields = [{"id": "f1", "label": "A", "editable": True}]
    assert filter_editable_field_definitions(fields) == fields


def test_filter_editable_field_definitions_editable_false_excluded() -> None:
    fields = [
        {"id": "f1", "editable": True},
        {"id": "f2", "editable": False},
    ]
    assert filter_editable_field_definitions(fields) == [{"id": "f1", "editable": True}]


def test_filter_editable_field_definitions_default_editable() -> None:
    fields = [{"id": "f1", "label": "X"}]
    assert filter_editable_field_definitions(fields) == fields


def test_filter_editable_field_definitions_skips_non_dict() -> None:
    fields = [{"id": "f1"}, "not a dict", None, {"id": "f2"}]
    assert filter_editable_field_definitions(fields) == [{"id": "f1"}, {"id": "f2"}]


def test_filter_fields_by_definitions_none_returns_empty() -> None:
    defs = [{"id": "a", "type": "short_text"}]
    assert filter_fields_by_definitions(None, defs) == {}


def test_filter_fields_by_definitions_empty_returns_empty() -> None:
    defs = [{"id": "a", "type": "short_text"}]
    assert filter_fields_by_definitions({}, defs) == {}


def test_filter_fields_by_definitions_keeps_only_editable_ids() -> None:
    fields = {"a": 1, "b": 2, "c": 3}
    defs = [{"id": "a", "type": "short_text"}, {"id": "c", "type": "short_text"}]
    assert filter_fields_by_definitions(fields, defs) == {"a": 1, "c": 3}


def test_filter_fields_by_definitions_skips_definitions_without_id() -> None:
    fields = {"a": 1}
    defs = [{"type": "short_text"}, {"id": "a", "type": "short_text"}]
    assert filter_fields_by_definitions(fields, defs) == {"a": 1}


def test_skipped_field_ids_lists_dropped_keys() -> None:
    assert skipped_field_ids({"a": 1, "b": 2}, {"a": 1}) == ["b"]
