"""Pipefy start-form and phase field shapes from GraphQL."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from pipefy_sdk.models.validators import NonBlankStr


class MalformedFieldDefinitionError(ValueError):
    """Raised when Pipefy field definitions cannot be used for forms or filtering."""


class FieldDefinition(BaseModel):
    """Minimum validated shape for a Pipefy field returned by GraphQL.

    Extra keys (``internal_id``, ``uuid``, ``help``, etc.) are preserved so
    callers keep the full API payload after validation.
    """

    model_config = ConfigDict(extra="allow")

    id: NonBlankStr
    type: NonBlankStr
    required: bool | None = None
    label: str | None = None
    editable: bool | None = None
    options: list[str] | None = None
    description: str | None = None
    help: str | None = None


def parse_field_definitions(
    field_definitions: list[Any],
    *,
    action: str,
) -> list[dict[str, Any]]:
    """Validate and normalize field definitions at the SDK boundary.

    Args:
        field_definitions: Raw list from ``GET_START_FORM_FIELDS_QUERY`` /
            ``GET_PHASE_FIELDS_QUERY`` (or test doubles).
        action: User-facing verb phrase, e.g. ``return start form fields``.

    Returns:
        Serialized field dicts with guaranteed non-empty ``id`` and ``type``.

    Raises:
        MalformedFieldDefinitionError: When any entry is not a dict or lacks
            ``id`` / ``type`` (including GraphQL ``null`` values).
    """
    if not field_definitions:
        return []

    parsed: list[dict[str, Any]] = []
    malformed = 0
    for raw in field_definitions:
        if not isinstance(raw, dict):
            malformed += 1
            continue
        try:
            parsed.append(
                FieldDefinition.model_validate(raw).model_dump(exclude_none=True)
            )
        except (ValidationError, TypeError):
            malformed += 1

    if malformed:
        raise MalformedFieldDefinitionError(
            f"Cannot {action}: {malformed} field "
            "definition(s) from Pipefy are missing required 'id' or 'type'. "
            "The pipe configuration may be incomplete or unsupported."
        )
    return parsed
