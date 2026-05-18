import pytest

from pipefy_sdk.utils.formatters import (
    convert_fields_to_array,
    convert_values_to_camel_case,
    normalize_field_condition_actions,
    normalize_field_condition_payload,
)


@pytest.mark.unit
def test_convert_fields_to_array_from_dict_defaults_generated_by_ai():
    fields = {"title": "Teste-MCP", "description": "Test description"}

    result = convert_fields_to_array(fields)

    assert result == [
        {"field_id": "title", "field_value": "Teste-MCP", "generated_by_ai": True},
        {
            "field_id": "description",
            "field_value": "Test description",
            "generated_by_ai": True,
        },
    ]


@pytest.mark.unit
def test_convert_fields_to_array_from_list_adds_generated_by_ai_when_missing():
    fields = [{"field_id": "title", "field_value": "Teste-MCP"}]

    result = convert_fields_to_array(fields)

    assert result == [
        {"field_id": "title", "field_value": "Teste-MCP", "generated_by_ai": True}
    ]


@pytest.mark.unit
def test_convert_fields_to_array_from_list_keeps_existing_generated_by_ai():
    fields = [
        {"field_id": "title", "field_value": "Teste-MCP", "generated_by_ai": False}
    ]

    result = convert_fields_to_array(fields)

    assert result == [
        {"field_id": "title", "field_value": "Teste-MCP", "generated_by_ai": False}
    ]


@pytest.mark.unit
def test_convert_fields_to_array_from_list_preserves_non_dict_items():
    fields = [{"field_id": "title", "field_value": "Teste-MCP"}, "raw-item"]

    result = convert_fields_to_array(fields)

    assert result[0] == {
        "field_id": "title",
        "field_value": "Teste-MCP",
        "generated_by_ai": True,
    }
    assert result[1] == "raw-item"


@pytest.mark.unit
def test_convert_fields_to_array_wraps_non_list_non_dict_truthy():
    result = convert_fields_to_array("x")
    assert result == ["x"]


@pytest.mark.unit
def test_convert_fields_to_array_returns_empty_list_for_falsy_value():
    result = convert_fields_to_array(None)
    assert result == []


@pytest.mark.unit
def test_convert_values_to_camel_case_defaults_operation_and_sets_generated_by_ai():
    values = [{"field_id": "field_1", "value": "New Value"}]

    result = convert_values_to_camel_case(values)

    assert result == [
        {
            "fieldId": "field_1",
            "value": "New Value",
            "operation": "REPLACE",
            "generatedByAi": True,
        }
    ]


@pytest.mark.unit
def test_convert_values_to_camel_case_uppercases_operation():
    values = [{"field_id": "field_1", "value": "New Value", "operation": "add"}]

    result = convert_values_to_camel_case(values)

    assert result[0]["operation"] == "ADD"
    assert result[0]["generatedByAi"] is True


@pytest.mark.unit
def test_convert_values_to_camel_case_missing_field_id_raises_value_error():
    values = [{"value": "test"}]

    with pytest.raises(
        ValueError, match="Value at index 0 is missing required 'field_id' key"
    ):
        convert_values_to_camel_case(values)


@pytest.mark.unit
def test_convert_values_to_camel_case_missing_value_raises_value_error():
    values = [{"field_id": "test"}]

    with pytest.raises(
        ValueError, match="Value at index 0 is missing required 'value' key"
    ):
        convert_values_to_camel_case(values)


@pytest.mark.unit
def test_convert_values_to_camel_case_accepts_camelcase_field_id():
    """Pipefy API responses use ``fieldId`` (camelCase); accept it as a synonym."""
    values = [{"fieldId": "field_1", "value": "New Value"}]

    result = convert_values_to_camel_case(values)

    assert result == [
        {
            "fieldId": "field_1",
            "value": "New Value",
            "operation": "REPLACE",
            "generatedByAi": True,
        }
    ]


@pytest.mark.unit
def test_convert_values_to_camel_case_snake_case_wins_over_camel_case():
    """If both ``field_id`` and ``fieldId`` are present, snake_case takes precedence."""
    values = [{"field_id": "snake_id", "fieldId": "camel_id", "value": "v"}]

    result = convert_values_to_camel_case(values)

    assert result[0]["fieldId"] == "snake_id"


@pytest.mark.unit
def test_normalize_field_condition_drops_expression_id_on_create():
    """``ConditionExpressionInput.id`` is a persisted PK; sending tokens errors RECORD_NOT_FOUND."""
    condition = {
        "expressions": [
            {
                "id": "client-token-xyz",
                "field_address": "f",
                "operation": "equals",
                "value": "v",
                "structure_id": "1",
            }
        ],
        "expressions_structure": [["1"]],
    }

    result = normalize_field_condition_payload(condition)

    assert "id" not in result["expressions"][0]
    assert result["expressions"][0]["field_address"] == "f"


@pytest.mark.unit
def test_normalize_field_condition_coerces_string_indices_to_int():
    """String indices come from the MCP docstring; Pipefy's API rejects them in 5xx form."""
    condition = {
        "expressions": [{"structure_id": "42", "field_address": "f", "value": "v"}],
        "expressions_structure": [["42"]],
    }

    result = normalize_field_condition_payload(condition)

    assert result["expressions"][0]["structure_id"] == 42
    assert result["expressions_structure"] == [[42]]


@pytest.mark.unit
def test_normalize_field_condition_passes_through_non_coercible_values():
    """Non-numeric strings are preserved (e.g. legacy UUID-style structure ids)."""
    condition = {
        "expressions": [{"structure_id": "not-a-number"}],
        "expressions_structure": [["not-a-number"]],
    }

    result = normalize_field_condition_payload(condition)

    assert result["expressions"][0]["structure_id"] == "not-a-number"
    assert result["expressions_structure"] == [["not-a-number"]]


@pytest.mark.unit
def test_normalize_field_condition_handles_flat_structure_group():
    """Bare scalars in ``expressions_structure`` are wrapped in a list (legacy callers)."""
    condition = {
        "expressions": [{"structure_id": "0"}],
        "expressions_structure": ["0"],
    }

    result = normalize_field_condition_payload(condition)

    assert result["expressions_structure"] == [[0]]


@pytest.mark.unit
def test_normalize_field_condition_preserves_top_level_extras():
    """Unknown top-level keys (e.g. ``index``) are forwarded — schema may evolve."""
    condition = {
        "expressions": [{"structure_id": 1}],
        "expressions_structure": [[1]],
        "index": 5,
    }

    result = normalize_field_condition_payload(condition)

    assert result["index"] == 5


@pytest.mark.unit
def test_normalize_field_condition_idempotent_on_already_int_values():
    """Re-applying the helper (e.g. MCP layer + SDK layer) must be a no-op."""
    condition = {
        "expressions": [{"structure_id": 7, "value": "v"}],
        "expressions_structure": [[7]],
    }

    once = normalize_field_condition_payload(condition)
    twice = normalize_field_condition_payload(once)

    assert once == twice


@pytest.mark.unit
def test_normalize_field_condition_returns_copy_without_expressions():
    """Conditions missing ``expressions`` round-trip as a shallow copy (no crash)."""
    condition = {"only_index": 1}

    result = normalize_field_condition_payload(condition)

    assert result == {"only_index": 1}
    assert result is not condition


@pytest.mark.unit
def test_normalize_field_condition_actions_maps_hidden_to_hide():
    """Legacy ``actionId: "hidden"`` is canonicalized to ``"hide"`` (case/whitespace insensitive)."""
    actions = [
        {"phaseFieldId": "1", "actionId": "hidden"},
        {"phaseFieldId": "2", "actionId": "  HIDDEN "},
        {"phaseFieldId": "3", "actionId": "show"},
    ]

    result = normalize_field_condition_actions(actions)

    assert [a["actionId"] for a in result] == ["hide", "hide", "show"]


@pytest.mark.unit
def test_normalize_field_condition_actions_does_not_mutate_input():
    """Caller-supplied dicts must remain untouched."""
    actions = [{"phaseFieldId": "1", "actionId": "hidden"}]

    result = normalize_field_condition_actions(actions)

    assert actions[0]["actionId"] == "hidden"
    assert result[0] is not actions[0]


@pytest.mark.unit
def test_normalize_field_condition_actions_passes_through_non_dict():
    """Non-dict items survive (forward-compatible with hypothetical scalar tokens)."""
    actions = ["raw-token", {"phaseFieldId": "1", "actionId": "hide"}]

    result = normalize_field_condition_actions(actions)

    assert result[0] == "raw-token"
    assert result[1]["actionId"] == "hide"
