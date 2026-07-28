"""Tests for AI-automation summary-row filtering (canonical response key style)."""

import pytest

from pipefy_sdk.ai_preflight import filter_ai_automation_summaries


@pytest.mark.unit
def test_filter_keeps_only_generate_with_ai_by_snake_action_id():
    rows = [
        {"id": "1", "name": "AI", "active": True, "action_id": "generate_with_ai"},
        {"id": "2", "name": "HTTP", "active": True, "action_id": "send_http_request"},
        {"id": "3", "name": "AI 2", "active": True, "action_id": "generate_with_ai"},
    ]
    kept = filter_ai_automation_summaries(rows)
    assert [r["id"] for r in kept] == ["1", "3"]


@pytest.mark.unit
def test_filter_ignores_non_declared_spellings():
    """The list query emits snake ``action_id`` only; camel/action_params never occur."""
    rows = [
        {"id": "9", "name": "AI", "active": True, "actionId": "generate_with_ai"},
        {"id": "10", "name": "Legacy", "actionParams": {"aiParams": {"value": "x"}}},
    ]
    assert filter_ai_automation_summaries(rows) == []


@pytest.mark.unit
def test_filter_skips_non_dict_rows():
    assert filter_ai_automation_summaries([None, "x", 3]) == []
