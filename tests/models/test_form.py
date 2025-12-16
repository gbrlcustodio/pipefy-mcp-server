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
        "description": (str | None, None),
        "priority": (str, ...),
        "due_date": (str | None, None),
        "amount": (float, ...),
        "is_active": (bool | None, None),
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
def test_form_model_creation_optional_fields():
    """Test dynamic Pydantic model creation with all optional fields."""
    field_definitions = [
        {"id": "nickname", "type": "short_text", "label": "Nickname", "required": False}
    ]

    FormModel = create_form_model(field_definitions)
    assert FormModel(nickname=None)


@pytest.mark.unit
def test_form_model_creation_with_multiple_fields():
    field_definitions = [
        {
            "id": "name",
            "label": "Name",
            "type": "short_text",
            "required": False,
            "editable": True,
            "options": [],
            "description": "",
            "help": "",
        },
        {
            "id": "email",
            "label": "Email",
            "type": "email",
            "required": False,
            "editable": True,
            "options": [],
            "description": "",
            "help": "",
        },
        {
            "id": "phone",
            "label": "Phone",
            "type": "phone",
            "required": False,
            "editable": True,
            "options": [],
            "description": "",
            "help": "",
        },
        {
            "id": "company",
            "label": "Company",
            "type": "short_text",
            "required": True,
            "editable": True,
            "options": [],
            "description": "",
            "help": "",
        },
        {
            "id": "company_industry",
            "label": "Company industry",
            "type": "select",
            "required": False,
            "editable": True,
            "options": [
                "Auditing",
                "Automotive",
                "Consulting",
                "Education",
                "Energy & Utilities",
                "Financial Services",
                "Health",
                "Manufaturing",
                "Marketing, Media & Entertainment",
                "Public Sector",
                "Retail",
                "Software",
                "Technology",
                "Telecom",
                "Others",
            ],
            "description": "",
            "help": "",
        },
        {
            "id": "observations",
            "label": "Observations",
            "type": "long_text",
            "required": False,
            "editable": True,
            "options": [],
            "description": "",
            "help": "",
        },
    ]

    FormModel = create_form_model(field_definitions)
    print(FormModel.model_fields)
