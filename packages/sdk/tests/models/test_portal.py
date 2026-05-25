"""Unit tests for portal Pydantic input models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipefy_sdk.models.portal import UpdatePortalInput

_PORTAL_UUID = "portal-created-uuid"


@pytest.mark.unit
def test_update_portal_input_dump_uses_camel_case_for_display_pipefy_header() -> None:
    """Interfaces schema expects displayPipefyHeader, not display_pipefy_header."""
    portal_input = UpdatePortalInput(
        interface_uuid=_PORTAL_UUID,
        name="Renamed",
        visibility="public",
        color="#112233",
        icon="star",
        display_pipefy_header=False,
    )
    dumped = portal_input.model_dump(
        exclude_unset=True,
        exclude_none=True,
        by_alias=True,
    )
    assert dumped == {
        "interface_uuid": _PORTAL_UUID,
        "name": "Renamed",
        "visibility": "public",
        "color": "#112233",
        "icon": "star",
        "displayPipefyHeader": False,
    }
    assert "display_pipefy_header" not in dumped


@pytest.mark.unit
def test_update_portal_input_rejects_invalid_visibility() -> None:
    """visibility is validated by Pydantic Literal before GraphQL."""
    with pytest.raises(ValidationError):
        UpdatePortalInput(
            interface_uuid=_PORTAL_UUID,
            visibility="public_visibility",  # type: ignore[arg-type]
        )
