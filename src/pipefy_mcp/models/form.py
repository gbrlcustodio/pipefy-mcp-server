from pydantic import BaseModel, Field, create_model

FIELD_TYPES = {
    "short_text": str,
    "long_text": str,
    "select": str,
    "date": str,
    "number": float,
    "checkbox": bool,
}


def create_form_model(field_definitions: list) -> type[BaseModel]:
    """Dynamically generate a Pydantic model for form validation.

    Args:
        field_definitions: List of field definitions from Pipefy API

    Returns:
        A Pydantic model class for validating form input
    """
    fields = {}
    for field_def in field_definitions:
        field_id = field_def["id"]
        field_type = field_def["type"]
        required = field_def["required"]
        options = field_def.get("options", [])

        pydantic_type = FIELD_TYPES.get(field_type, str)

        fields[field_id] = (
            pydantic_type,
            Field(
                default=... if required else None,
                title=field_def["label"],
                description=field_def.get("description", ""),
                json_schema_extra=lambda schema, opts=options: (
                    schema.pop("default", None) if not required else None,
                    schema.update({"enum": [opt for opt in opts]}) if opts else None,
                ),
            ),
        )

    return create_model("DynamicFormModel", **fields)
