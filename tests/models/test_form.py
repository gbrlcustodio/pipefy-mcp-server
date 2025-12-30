import pytest

from pipefy_mcp.models.form import create_form_model


@pytest.mark.unit
def test_form_model_creation():
    """Test dynamic Pydantic model creation for form validation."""
    field_definitions = [
        {"id": "name", "type": "short_text", "label": "Name", "required": True},
        {
            "id": "description",
            "type": "long_text",
            "label": "Description",
            "required": False,
        },
        {"id": "priority", "type": "select", "label": "Priority", "required": True},
        {"id": "due_date", "type": "date", "label": "Due Date", "required": False},
        {"id": "amount", "type": "number", "label": "Amount", "required": True},
        {
            "id": "is_active",
            "type": "checkbox",
            "label": "Is Active",
            "required": False,
        },
    ]

    expected_fields = {
        "name": (str, ...),
        "description": (str, None),
        "priority": (str, ...),
        "due_date": (str, None),
        "amount": (float, ...),
        "is_active": (bool, None),
    }

    FormModel = create_form_model(field_definitions)

    for field_name, (expected_type, expected_default) in expected_fields.items():
        assert field_name in FormModel.model_fields
        field_info = FormModel.model_fields[field_name]
        assert field_info.annotation == expected_type
        if expected_default is ...:
            assert field_info.is_required() is True
        else:
            assert field_info.is_required() is False
            assert field_info.get_default() is expected_default


@pytest.mark.unit
def test_json_schema_with_choices():
    """Test json schema generation with select field choices."""
    field_definitions = [
        {
            "id": "status",
            "type": "select",
            "label": "Status",
            "required": True,
            "options": ["Open", "In Progress", "Closed"],
        }
    ]

    expected_fields = {
        "status": {"enum": ["Open", "In Progress", "Closed"]},
    }

    FormModel = create_form_model(field_definitions)
    schema = FormModel.model_json_schema()

    for field_name, expected_schema in expected_fields.items():
        field_schema = schema["properties"][field_name]
        for key, value in expected_schema.items():
            assert field_schema[key] == value


@pytest.mark.unit
def test_json_schema_with_optional_fields():
    """Test json schema generation with optional fields."""
    field_definitions = [
        {"id": "comments", "type": "long_text", "label": "Comments", "required": False}
    ]

    expected_fields = {
        "comments": {"type": "string"},
    }

    FormModel = create_form_model(field_definitions)
    schema = FormModel.model_json_schema()

    for field_name, expected_schema in expected_fields.items():
        field_schema = schema["properties"][field_name]
        for key, value in expected_schema.items():
            assert field_schema[key] == value

        assert field_name not in schema.get("required", [])


@pytest.mark.unit
@pytest.mark.parametrize(
    "field_type, expected_format",
    [
        ("date", "date"),
        ("datetime", "date-time"),
        ("email", "email"),
    ],
)
def test_json_schema_with_formats(field_type, expected_format):
    """Test json schema generation with different field formats."""
    field_id = f"{field_type}_field"
    field_definitions = [
        {"id": field_id, "type": field_type, "label": "Test Field", "required": False}
    ]

    FormModel = create_form_model(field_definitions)
    schema = FormModel.model_json_schema()
    field_schema = schema["properties"][field_id]

    assert field_schema["format"] == expected_format

@pytest.mark.unit
def test_form_model_with_default_values():
    """Test dynamic Pydantic model creation with provided default values."""
    field_definitions = [
        {"id": "name", "type": "short_text", "label": "Name", "required": True},
        {
            "id": "description",
            "type": "long_text",
            "label": "Description",
            "required": False,
        },
        {"id": "priority", "type": "select", "label": "Priority", "required": True},
    ]

    # Test with default values provided
    default_values = {"name": "Default Name", "description": "Default Description"}
    FormModelWithDefaults = create_form_model(field_definitions, default_values)

    # Verify 'name' (required) uses provided default
    name_field = FormModelWithDefaults.model_fields["name"]
    assert name_field.is_required() is False  # Now has a default
    assert name_field.get_default() == "Default Name"

    # Verify 'description' (optional) uses provided default
    description_field = FormModelWithDefaults.model_fields["description"]
    assert description_field.is_required() is False
    assert description_field.get_default() == "Default Description"

    # Verify 'priority' (required) still requires a value as no default was provided
    priority_field = FormModelWithDefaults.model_fields["priority"]
    assert priority_field.is_required() is True

    # Test without default values (should revert to original behavior)
    FormModelWithoutDefaults = create_form_model(field_definitions)

    # Verify 'name' (required) is truly required
    name_field_no_default = FormModelWithoutDefaults.model_fields["name"]
    assert name_field_no_default.is_required() is True

    # Verify 'description' (optional) defaults to None
    description_field_no_default = FormModelWithoutDefaults.model_fields["description"]
    assert description_field_no_default.is_required() is False
    assert description_field_no_default.get_default() is None
