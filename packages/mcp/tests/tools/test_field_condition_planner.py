"""Unit tests for field_condition_planner (pure persistence + required/hide lint)."""

import pytest

from pipefy_mcp.tools.field_condition_planner import (
    enrich_required_field_move_message,
    evaluate_condition_persistence,
    extract_required_field_label_from_error,
    find_required_hidden_fields,
    is_required_hidden_by_label,
    phase_fields_from_payload,
)


@pytest.mark.unit
def test_evaluate_condition_persistence_verified_when_fetched_phase_matches():
    result = evaluate_condition_persistence(
        requested_phase_id="10",
        condition_id="fc-1",
        fetched={"id": "fc-1", "phase": {"id": "10", "name": "Inbox"}},
        listed_ids=None,
    )
    assert result.status == "verified"
    assert result.actual_phase_id is None


@pytest.mark.unit
def test_evaluate_condition_persistence_wrong_phase_when_fetched_phase_differs():
    result = evaluate_condition_persistence(
        requested_phase_id="10",
        condition_id="fc-1",
        fetched={"id": "fc-1", "phase": {"id": "99", "name": "Start form"}},
        listed_ids=None,
    )
    assert result.status == "wrong_phase"
    assert result.actual_phase_id == "99"


@pytest.mark.unit
def test_evaluate_condition_persistence_incomplete_phase_uses_list_fallback():
    result = evaluate_condition_persistence(
        requested_phase_id="10",
        condition_id="fc-1",
        fetched={"id": "fc-1", "phase": None},
        listed_ids=["fc-other", "fc-1"],
    )
    assert result.status == "verified"
    assert result.actual_phase_id is None


@pytest.mark.unit
def test_evaluate_condition_persistence_incomplete_phase_missing_when_list_lacks_id():
    result = evaluate_condition_persistence(
        requested_phase_id="10",
        condition_id="fc-1",
        fetched={"id": "fc-1", "phase": {}},
        listed_ids=["fc-other"],
    )
    assert result.status == "missing"


@pytest.mark.unit
def test_evaluate_condition_persistence_missing_when_not_in_list():
    result = evaluate_condition_persistence(
        requested_phase_id="10",
        condition_id="fc-1",
        fetched=None,
        listed_ids=["fc-other", "fc-2"],
    )
    assert result.status == "missing"
    assert result.actual_phase_id is None


@pytest.mark.unit
def test_evaluate_condition_persistence_verified_via_list_fallback():
    result = evaluate_condition_persistence(
        requested_phase_id="10",
        condition_id="fc-1",
        fetched=None,
        listed_ids=["fc-other", "fc-1"],
    )
    assert result.status == "verified"
    assert result.actual_phase_id is None


@pytest.mark.unit
def test_evaluate_condition_persistence_compares_phase_ids_as_strings():
    result = evaluate_condition_persistence(
        requested_phase_id=10,
        condition_id="fc-1",
        fetched={"id": "fc-1", "phase": {"id": 10}},
        listed_ids=None,
    )
    assert result.status == "verified"


@pytest.mark.unit
def test_find_required_hidden_fields_lists_required_hide_target():
    fields = [
        {"id": "slug-a", "internal_id": "123", "required": True},
        {"id": "slug-b", "internal_id": "456", "required": False},
    ]
    actions = [{"phaseFieldId": "123", "actionId": "hide"}]
    assert find_required_hidden_fields(fields, actions) == ["123"]


@pytest.mark.unit
def test_find_required_hidden_fields_treats_legacy_hidden_as_hide():
    fields = [
        {"id": "slug-a", "internal_id": "123", "required": True},
    ]
    actions = [{"phaseFieldId": "123", "actionId": "hidden"}]
    assert find_required_hidden_fields(fields, actions) == ["123"]


@pytest.mark.unit
def test_find_required_hidden_fields_treats_whitespace_case_hidden_alias():
    fields = [
        {"id": "slug-a", "internal_id": "123", "required": True},
    ]
    actions = [{"phaseFieldId": "123", "actionId": "  HIDDEN "}]
    assert find_required_hidden_fields(fields, actions) == ["123"]


@pytest.mark.unit
def test_find_required_hidden_fields_skips_show_and_optional():
    fields = [
        {"id": "slug-a", "internal_id": "123", "required": True},
        {"id": "slug-b", "internal_id": "456", "required": False},
    ]
    actions = [
        {"phaseFieldId": "123", "actionId": "show"},
        {"phaseFieldId": "456", "actionId": "hide"},
    ]
    assert find_required_hidden_fields(fields, actions) == []


@pytest.mark.unit
def test_find_required_hidden_fields_ignores_non_dict_defs():
    fields = [
        "skip-me",
        None,
        {"id": "slug-a", "internal_id": "123", "required": True},
    ]
    actions = [{"phaseFieldId": "123", "actionId": "hide"}]
    assert find_required_hidden_fields(fields, actions) == ["123"]


@pytest.mark.unit
def test_find_required_hidden_fields_matches_phase_field_id_against_id():
    fields = [
        {"id": "789", "internal_id": "111", "required": True},
    ]
    actions = [{"phaseFieldId": "789", "actionId": "hide"}]
    assert find_required_hidden_fields(fields, actions) == ["789"]


@pytest.mark.unit
def test_find_required_hidden_fields_matches_phase_field_id_against_uuid():
    field_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    fields = [
        {
            "id": "slug-a",
            "internal_id": "123",
            "uuid": field_uuid,
            "required": True,
        },
    ]
    actions = [{"phaseFieldId": field_uuid, "actionId": "hide"}]
    assert find_required_hidden_fields(fields, actions) == [field_uuid]


@pytest.mark.unit
def test_find_required_hidden_fields_dedupes_stable_action_order():
    fields = [
        {"internal_id": "123", "required": True},
        {"internal_id": "456", "required": True},
    ]
    actions = [
        {"phaseFieldId": "456", "actionId": "hide"},
        {"phaseFieldId": "123", "actionId": "hide"},
        {"phaseFieldId": "456", "actionId": "hide"},
    ]
    assert find_required_hidden_fields(fields, actions) == ["456", "123"]


@pytest.mark.unit
def test_phase_fields_from_payload_unwraps_fields_list():
    assert phase_fields_from_payload({"fields": [{"id": "a"}]}) == [{"id": "a"}]
    assert phase_fields_from_payload({"fields": "bad"}) == []
    assert phase_fields_from_payload(None) == []
    assert phase_fields_from_payload([]) == []


@pytest.mark.unit
def test_extract_required_field_label_from_error_returns_label():
    message = (
        'Field "Hidden required note" is required! '
        "Please fill it and you'll be ready to go!"
    )
    assert extract_required_field_label_from_error(message) == "Hidden required note"


@pytest.mark.unit
def test_extract_required_field_label_from_error_handles_invalid_inputs_prefix():
    message = (
        'Invalid inputs: Field "SF Hidden required" is required! '
        "Please fill it and you'll be ready to go!"
    )
    assert extract_required_field_label_from_error(message) == "SF Hidden required"


@pytest.mark.unit
def test_extract_required_field_label_from_error_returns_none_when_unrelated():
    assert extract_required_field_label_from_error("permission denied") is None
    assert extract_required_field_label_from_error("Field is required") is None


@pytest.mark.unit
def test_is_required_hidden_by_label_true_when_label_matches_hide_target():
    fields = [
        {"id": "slug", "internal_id": "123", "label": "Foo", "required": True},
    ]
    actions = [{"phaseFieldId": "123", "actionId": "hide"}]
    assert is_required_hidden_by_label(fields, actions, "Foo") is True


@pytest.mark.unit
def test_is_required_hidden_by_label_false_when_not_hidden_or_label_mismatch():
    fields = [
        {"id": "slug", "internal_id": "123", "label": "Foo", "required": True},
        {"id": "other", "internal_id": "456", "label": "Bar", "required": True},
    ]
    actions = [{"phaseFieldId": "456", "actionId": "hide"}]
    assert is_required_hidden_by_label(fields, actions, "Foo") is False
    assert is_required_hidden_by_label(fields, actions, "Missing") is False


@pytest.mark.unit
def test_enrich_required_field_move_message_appends_hint_when_hidden():
    api = 'Field "Foo" is required! Please fill it and you\'ll be ready to go!'
    enriched = enrich_required_field_move_message(api, hidden_by_condition=True)
    assert enriched.startswith(api)
    assert "may be hidden by a field condition while still required" in enriched
    assert enrich_required_field_move_message(api, hidden_by_condition=False) == api
