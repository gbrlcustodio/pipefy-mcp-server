from typing import Any

from pydantic import BaseModel, Field, create_model

FIELD_TYPES = {
    "short_text": str,
    "long_text": str,
    "select": str,
    "date": str,
    "number": float,
    "checkbox": bool,
}

FIELD_FORMATS = {
    "date": "date",
    "datetime": "date-time",
    "email": "email",
}


def _get_default_value(
    field_id: str,
    required: bool,
    default_values: dict[str, Any] | None = None,
) -> Any:
    """Determine the default value for a field."""
    if default_values and field_id in default_values:
        return default_values[field_id]
    return ... if required else None


def create_form_model(
    field_definitions: list, default_values: dict[str, Any] | None = None
) -> type[BaseModel]:
    """Dynamically generate a Pydantic model for form validation.

    Args:
        field_definitions: List of field definitions from Pipefy API
        default_values: A dictionary of default values for the fields.

    Returns:
        A Pydantic model class for validating form input
    """
    fields: dict[str, Any] = {}
    for field_def in field_definitions:
        field_id = field_def["id"]
        field_type = field_def["type"]
        required = field_def["required"]
        options = field_def.get("options", [])

        pydantic_type = FIELD_TYPES.get(field_type, str)
        schema_format = FIELD_FORMATS.get(field_type, None)
        default_value = _get_default_value(field_id, required, default_values)

        fields[field_id] = (
            pydantic_type,
            Field(
                default=default_value,
                title=field_def["label"],
                description=field_def.get("description", ""),
                json_schema_extra=_create_json_schema_extra(
                    options, required, schema_format
                ),
            ),
        )

    return create_model("DynamicFormModel", **fields)


def _create_json_schema_extra(options: list[str], required: bool, format: str | None):
    def schema_updater(schema: dict) -> None:
        if not required and schema.get("default") is None:
            schema.pop("default", None)
        if options:
            schema["enum"] = options
        if format:
            schema["format"] = format

    return schema_updater
