"""Pydantic models for knowledge base data lookup inputs.

A data lookup's conditions are validated here, at the boundary, because the
backend only checks ``field`` and ``operator`` at write time: a static
condition saved without a ``value`` (or with a non-string one) is accepted by
the API and then breaks the lookup when an agent runs it. Parsing into
:class:`DataLookupCondition` up front keeps definitions that cannot work from
ever being persisted.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipefy_sdk.models.validators import NonBlankStr

# Attribute name → camelCase alias, so error messages name the field the same
# way the tool/docs teach it (``inputName``, not ``input_name``).
_FILL_WITH_AI_FIELDS = {
    "input_name": "inputName",
    "input_type": "inputType",
    "input_description": "inputDescription",
}


class DataLookupCondition(BaseModel):
    """One record-filter condition of a knowledge base data lookup.

    Accepts snake_case or camelCase keys (``usingFillWithAi``, ``inputName``,
    …); unknown keys are rejected so a typo cannot silently drop a constraint.
    Two mutually exclusive shapes exist:

    - **Static** (``using_fill_with_ai`` false, the default): ``value`` is
      required and must be a non-blank string — the agent runtime compares
      string values and rejects a condition saved without one.
    - **AI-filled** (``using_fill_with_ai`` true): ``input_name``,
      ``input_type``, and ``input_description`` are required (they describe
      the input the AI asks for at runtime) and ``value`` must be omitted
      (the runtime replaces it with the AI-provided input, so a static value
      here would be silently ignored).

    ``operator`` is an opaque backend string (e.g. ``"eq"``, ``"contains"``);
    ``input_type`` likewise (e.g. ``"text"``, ``"number"``). ``attribute`` and
    ``field_uuid`` are optional passthrough keys used by backend-specific
    search modes; ``field`` is required either way (the backend rejects a
    condition without one).
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    field: NonBlankStr
    operator: NonBlankStr
    value: NonBlankStr | None = None
    using_fill_with_ai: bool = Field(default=False, alias="usingFillWithAi")
    input_name: NonBlankStr | None = Field(default=None, alias="inputName")
    input_type: NonBlankStr | None = Field(default=None, alias="inputType")
    input_description: NonBlankStr | None = Field(
        default=None, alias="inputDescription"
    )
    attribute: NonBlankStr | None = None
    field_uuid: NonBlankStr | None = Field(default=None, alias="fieldUuid")

    @model_validator(mode="after")
    def _check_shape(self) -> DataLookupCondition:
        if self.using_fill_with_ai:
            missing = [
                alias
                for name, alias in _FILL_WITH_AI_FIELDS.items()
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(
                    "an AI-filled condition (usingFillWithAi=true) requires "
                    f"non-blank {', '.join(missing)}"
                )
            if self.value is not None:
                raise ValueError(
                    "an AI-filled condition (usingFillWithAi=true) must not set "
                    "'value'; the AI provides it at runtime"
                )
        else:
            if self.value is None:
                raise ValueError(
                    "a static condition requires a non-blank string 'value' "
                    "(or set usingFillWithAi=true with inputName/inputType/"
                    "inputDescription)"
                )
            extras = [
                alias
                for name, alias in _FILL_WITH_AI_FIELDS.items()
                if getattr(self, name) is not None
            ]
            if extras:
                raise ValueError(
                    f"{', '.join(extras)} only apply to AI-filled conditions; "
                    "set usingFillWithAi=true or drop them"
                )
        return self

    def to_input(self) -> dict[str, Any]:
        """Serialize to the GraphQL condition input (camelCase, no nulls)."""
        return self.model_dump(by_alias=True, exclude_none=True)
