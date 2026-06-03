"""Unit tests for ReportCardsFilter preflight validation."""

from __future__ import annotations

from pipefy_sdk.report_filter_preflight import (
    EXAMPLE_PHASE_FILTER,
    validate_report_cards_filter,
)


def test_validate_report_cards_filter_none_passes():
    assert validate_report_cards_filter(None) is None


def test_validate_report_cards_filter_valid_phase_skeleton_passes():
    assert validate_report_cards_filter(EXAMPLE_PHASE_FILTER) is None


def test_validate_report_cards_filter_nested_group_passes():
    filt = {
        "operator": "or",
        "groups": [
            {
                "operator": "and",
                "queries": [
                    {"field": "current_phase", "operator": "eq", "value": "1"},
                ],
            }
        ],
    }
    assert validate_report_cards_filter(filt) is None


def test_validate_report_cards_filter_rejects_top_level_current_phase():
    err = validate_report_cards_filter({"current_phase": ["123"]})
    assert err is not None
    assert "top-level" in err
    assert "current_phase" in err
    assert "get_pipe_report_filterable_fields" in err


def test_validate_report_cards_filter_rejects_unknown_root_key():
    err = validate_report_cards_filter({"operator": "and", "bogus": True})
    assert err is not None
    assert "unknown key" in err
    assert "bogus" in err


def test_validate_report_cards_filter_requires_operator():
    err = validate_report_cards_filter({"queries": []})
    assert err is not None
    assert "operator is required" in err


def test_validate_report_cards_filter_rejects_invalid_group_operator():
    err = validate_report_cards_filter({"operator": "xor", "queries": []})
    assert err is not None
    assert "operator must be one of" in err


def test_validate_report_cards_filter_query_requires_field_and_operator():
    err = validate_report_cards_filter(
        {"operator": "and", "queries": [{"operator": "eq", "value": "x"}]}
    )
    assert err is not None
    assert ".field is required" in err


def test_validate_report_cards_filter_query_rejects_unknown_keys():
    err = validate_report_cards_filter(
        {
            "operator": "and",
            "queries": [{"field": "current_phase", "operator": "eq", "phase_id": "1"}],
        }
    )
    assert err is not None
    assert "unknown key" in err
    assert "phase_id" in err


def test_validate_report_cards_filter_rejects_non_object_filter():
    err = validate_report_cards_filter([])  # type: ignore[arg-type]
    assert err is not None
    assert "JSON object" in err
