import pytest

from pipefy_mcp.services.pipefy.utils.formatters import (
    convert_fields_to_array,
    convert_values_to_camel_case,
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
    fields = [{"field_id": "title", "field_value": "Teste-MCP", "generated_by_ai": False}]

    result = convert_fields_to_array(fields)

    assert result == [
        {"field_id": "title", "field_value": "Teste-MCP", "generated_by_ai": False}
    ]


@pytest.mark.unit
def test_convert_fields_to_array_from_list_preserves_non_dict_items():
    fields = [{"field_id": "title", "field_value": "Teste-MCP"}, "raw-item"]

    result = convert_fields_to_array(fields)

    assert result[0] == {"field_id": "title", "field_value": "Teste-MCP", "generated_by_ai": True}
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
        {"fieldId": "field_1", "value": "New Value", "operation": "REPLACE", "generatedByAi": True}
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

    with pytest.raises(ValueError, match="Value at index 0 is missing required 'field_id' key"):
        convert_values_to_camel_case(values)


@pytest.mark.unit
def test_convert_values_to_camel_case_missing_value_raises_value_error():
    values = [{"field_id": "test"}]

    with pytest.raises(ValueError, match="Value at index 0 is missing required 'value' key"):
        convert_values_to_camel_case(values)


