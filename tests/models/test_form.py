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
def test_json_schema_with_date_format():
    """Test json schema generation with date field format."""
    field_definitions = [
        {"id": "start_date", "type": "date", "label": "Start Date", "required": True}
    ]

    expected_fields = {
        "start_date": {"format": "date"},
    }

    FormModel = create_form_model(field_definitions)
    schema = FormModel.model_json_schema()

    for field_name, expected_schema in expected_fields.items():
        field_schema = schema["properties"][field_name]
        for key, value in expected_schema.items():
            assert field_schema[key] == value


@pytest.mark.unit
def test_json_schema_with_datetime_format():
    """Test json schema generation with datetime field format."""
    field_definitions = [
        {
            "id": "event_time",
            "type": "datetime",
            "label": "Event Time",
            "required": True,
        }
    ]

    expected_fields = {
        "event_time": {"format": "date-time"},
    }

    FormModel = create_form_model(field_definitions)
    schema = FormModel.model_json_schema()

    for field_name, expected_schema in expected_fields.items():
        field_schema = schema["properties"][field_name]
        for key, value in expected_schema.items():
            assert field_schema[key] == value


@pytest.mark.unit
def test_json_schema_with_email_format():
    """Test json schema generation with email field format."""
    field_definitions = [
        {
            "id": "contact_email",
            "type": "email",
            "label": "Contact Email",
            "required": True,
        }
    ]

    expected_fields = {
        "contact_email": {"format": "email"},
    }

    FormModel = create_form_model(field_definitions)
    schema = FormModel.model_json_schema()

    for field_name, expected_schema in expected_fields.items():
        field_schema = schema["properties"][field_name]
        for key, value in expected_schema.items():
            assert field_schema[key] == value
