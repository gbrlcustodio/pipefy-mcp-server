"""Unit tests for automation mutation input key normalization."""

from __future__ import annotations

import pytest

from pipefy_sdk.automation_input import normalize_automation_input_keys


@pytest.mark.unit
def test_none_returns_none():
    assert normalize_automation_input_keys(None) is None


@pytest.mark.unit
def test_empty_dict_returns_empty_dict():
    assert normalize_automation_input_keys({}) == {}


@pytest.mark.unit
def test_camel_aliases_map_to_snake_api_names():
    extra = {
        "actionParams": {"to_phase_id": "42"},
        "eventParams": {"to_phase_id": "7"},
        "actionId": "move_single_card",
        "eventId": "card_moved",
        "actionRepoId": "301",
        "eventRepoId": "300",
        "schedulerFrequency": "daily",
    }
    assert normalize_automation_input_keys(extra) == {
        "action_params": {"to_phase_id": "42"},
        "event_params": {"to_phase_id": "7"},
        "action_id": "move_single_card",
        "event_id": "card_moved",
        "action_repo_id": "301",
        "event_repo_id": "300",
        "scheduler_frequency": "daily",
    }


@pytest.mark.unit
def test_snake_aliases_map_to_camel_api_names():
    extra = {
        "scheduler_cron": {"expression": "0 0 * * *"},
        "response_schema": {"type": "object"},
        "search_for": [{"field": "x"}],
        "client_mutation_id": "cli-1",
    }
    assert normalize_automation_input_keys(extra) == {
        "schedulerCron": {"expression": "0 0 * * *"},
        "responseSchema": {"type": "object"},
        "searchFor": [{"field": "x"}],
        "clientMutationId": "cli-1",
    }


@pytest.mark.unit
def test_api_names_pass_through_unchanged():
    extra = {
        "action_params": {"card_id": "%{id}"},
        "event_params": {"to_phase_id": "7"},
        "schedulerCron": {"expression": "0 0 * * *"},
        "searchFor": [{"field": "x"}],
        "active": False,
        "name": "Rule",
        "condition": {"expressions": []},
    }
    assert normalize_automation_input_keys(extra) == extra


@pytest.mark.unit
def test_api_name_wins_when_both_spellings_present():
    extra = {
        "action_params": {"to_phase_id": "keep"},
        "actionParams": {"to_phase_id": "drop"},
    }
    assert normalize_automation_input_keys(extra) == {
        "action_params": {"to_phase_id": "keep"},
    }


@pytest.mark.unit
def test_unknown_keys_pass_through_verbatim():
    extra = {"somethingElse": 1, "another_key": 2}
    assert normalize_automation_input_keys(extra) == extra


@pytest.mark.unit
def test_nested_dicts_are_not_rewritten():
    extra = {
        "actionParams": {
            "taskParams": {"title": "T"},
            "fieldsAttributes": [{"fieldId": "1"}],
        },
    }
    assert normalize_automation_input_keys(extra) == {
        "action_params": {
            "taskParams": {"title": "T"},
            "fieldsAttributes": [{"fieldId": "1"}],
        },
    }


@pytest.mark.unit
def test_input_dict_is_not_mutated():
    extra = {"actionParams": {"a": 1}}
    normalize_automation_input_keys(extra)
    assert extra == {"actionParams": {"a": 1}}
