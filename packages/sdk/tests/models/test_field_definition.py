from __future__ import annotations

import pytest

from pipefy_sdk.models.field_definition import (
    MalformedFieldDefinitionError,
    parse_field_definitions,
)


@pytest.mark.unit
def test_parse_field_definitions_rejects_null_id():
    with pytest.raises(MalformedFieldDefinitionError):
        parse_field_definitions(
            [{"id": None, "type": "select"}],
            action="validate fields",
        )


@pytest.mark.unit
def test_parse_field_definitions_preserves_extra_keys():
    raw = [
        {
            "id": "title",
            "type": "short_text",
            "internal_id": "99",
            "uuid": "abc",
        }
    ]
    parsed = parse_field_definitions(raw, action="test")
    assert parsed[0]["internal_id"] == "99"
    assert parsed[0]["uuid"] == "abc"


@pytest.mark.unit
def test_parse_field_definitions_accepts_null_required():
    parsed = parse_field_definitions(
        [{"id": "title", "type": "short_text", "required": None}],
        action="test",
    )
    assert "required" not in parsed[0]


@pytest.mark.unit
def test_parse_field_definitions_raises_with_action():
    with pytest.raises(MalformedFieldDefinitionError, match="filter phase fields"):
        parse_field_definitions(
            [{"label": "Status", "type": "select"}],
            action="filter phase fields",
        )


@pytest.mark.unit
@pytest.mark.parametrize("message", ["", "   "])
def test_malformed_field_definition_error_rejects_blank_message(message: str):
    with pytest.raises(ValueError, match="non-blank message"):
        MalformedFieldDefinitionError(message)
