"""Unit tests for portal Pydantic input models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipefy_sdk.models.portal import (
    CreatePortalElementInput,
    UpdatePortalElementInput,
    UpdatePortalInput,
)

_PORTAL_UUID = "portal-created-uuid"
_PAGE_ID = "page-uuid-1"
_ELEMENT_ID = "el-uuid-1"
_EXAMPLE_PIPE_REPO_ID = "987654321"

_VALID_FORMS_METADATA = {"name": "Request form", "defaultValues": {}}
_VALID_FORMS_DATA_SOURCES = [{"repo_uuid": _EXAMPLE_PIPE_REPO_ID}]
_VALID_LINK_METADATA = {
    "linkName": "Open Pipefy",
    "linkUrl": "https://example.com/pipefy",
}
_VALID_LINK_METADATA_NAME_ONLY = {
    "linkName": "Open Pipefy",
    "gridMap": {"height": 64, "columns": 4, "minColumns": 4},
}
_VALID_SUB_PORTAL_METADATA: dict[str, str] = {}


@pytest.mark.unit
def test_create_portal_element_input_accepts_forms_with_data_sources() -> None:
    """forms elements require name; optional data_sources mirrors createElement input."""
    element_input = CreatePortalElementInput(
        page_id=_PAGE_ID,
        type="forms",
        metadata=_VALID_FORMS_METADATA,
        data_sources=_VALID_FORMS_DATA_SOURCES,
    )
    assert element_input.type == "forms"
    assert element_input.metadata["name"] == "Request form"
    assert element_input.data_sources == _VALID_FORMS_DATA_SOURCES


@pytest.mark.unit
def test_create_portal_element_input_accepts_sub_portal_type() -> None:
    """subPortal create validates metadata shape (empty until wired via internal_api)."""
    element_input = CreatePortalElementInput(
        page_id=_PAGE_ID,
        type="subPortal",
        metadata=_VALID_SUB_PORTAL_METADATA,
    )
    assert element_input.type == "subPortal"
    assert element_input.metadata == {}


@pytest.mark.unit
def test_create_portal_element_input_accepts_link_metadata() -> None:
    """link elements require linkName; linkUrl is optional (live stored shape)."""
    element_input = CreatePortalElementInput(
        page_id=_PAGE_ID,
        type="link",
        metadata=_VALID_LINK_METADATA,
    )
    assert element_input.metadata["linkName"] == "Open Pipefy"
    assert element_input.metadata["linkUrl"] == "https://example.com/pipefy"


@pytest.mark.unit
def test_create_portal_element_input_accepts_link_metadata_with_name_only() -> None:
    """Template links often expose only linkName + gridMap on read."""
    element_input = CreatePortalElementInput(
        page_id=_PAGE_ID,
        type="link",
        metadata=_VALID_LINK_METADATA_NAME_ONLY,
    )
    assert element_input.metadata["linkName"] == "Open Pipefy"


@pytest.mark.unit
@pytest.mark.parametrize(
    "element_type",
    [
        "text",
        "table",
        "field",
        "embedLink",
        "embedVideo",
        "embedImage",
        "button",
        "divider",
        "pages",
        "automationButton",
        "contentBlock",
        "document",
    ],
)
def test_create_portal_element_input_accepts_all_interface_page_element_types(
    element_type: str,
) -> None:
    """InterfacePageElementType Literal must allow all 15 enum values."""
    element_input = CreatePortalElementInput(
        page_id=_PAGE_ID,
        type=element_type,  # type: ignore[arg-type]
        metadata={},
    )
    assert element_input.type == element_type


@pytest.mark.unit
def test_create_portal_element_input_rejects_unknown_element_type() -> None:
    with pytest.raises(ValidationError, match="type"):
        CreatePortalElementInput(
            page_id=_PAGE_ID,
            type="pipe",  # type: ignore[arg-type]
            metadata={},
        )


@pytest.mark.unit
def test_create_portal_element_input_rejects_forms_metadata_missing_name() -> None:
    with pytest.raises(ValidationError, match="name"):
        CreatePortalElementInput(
            page_id=_PAGE_ID,
            type="forms",
            metadata={},
        )


@pytest.mark.unit
@pytest.mark.parametrize("name", ["", "   "])
def test_create_portal_element_input_rejects_blank_forms_name(name: str) -> None:
    with pytest.raises(ValidationError, match="name"):
        CreatePortalElementInput(
            page_id=_PAGE_ID,
            type="forms",
            metadata={"name": name},
        )


@pytest.mark.unit
def test_create_portal_element_input_rejects_link_metadata_missing_link_name() -> None:
    with pytest.raises(ValidationError, match="linkName"):
        CreatePortalElementInput(
            page_id=_PAGE_ID,
            type="link",
            metadata={"linkUrl": "https://example.com"},
        )


@pytest.mark.unit
@pytest.mark.parametrize("link_url", ["", "   "])
def test_create_portal_element_input_rejects_blank_link_url(link_url: str) -> None:
    with pytest.raises(ValidationError, match="linkUrl"):
        CreatePortalElementInput(
            page_id=_PAGE_ID,
            type="link",
            metadata={"linkUrl": link_url, "linkName": "Label"},
        )


@pytest.mark.unit
@pytest.mark.parametrize("link_name", ["", "   "])
def test_create_portal_element_input_rejects_blank_link_name(link_name: str) -> None:
    with pytest.raises(ValidationError, match="linkName"):
        CreatePortalElementInput(
            page_id=_PAGE_ID,
            type="link",
            metadata={"linkUrl": "https://example.com", "linkName": link_name},
        )


@pytest.mark.unit
def test_create_portal_element_input_rejects_blank_page_id() -> None:
    with pytest.raises(ValidationError, match="page_id"):
        CreatePortalElementInput(
            page_id="   ",
            type="text",
            metadata={},
        )


@pytest.mark.unit
def test_update_portal_element_input_accepts_forms_metadata() -> None:
    element_input = UpdatePortalElementInput(
        element_id=_ELEMENT_ID,
        page_id=_PAGE_ID,
        type="forms",
        metadata=_VALID_FORMS_METADATA,
        data_sources=_VALID_FORMS_DATA_SOURCES,
    )
    assert element_input.metadata["name"] == "Request form"


@pytest.mark.unit
def test_update_portal_element_input_accepts_link_metadata() -> None:
    element_input = UpdatePortalElementInput(
        element_id=_ELEMENT_ID,
        page_id=_PAGE_ID,
        type="link",
        metadata=_VALID_LINK_METADATA,
    )
    assert element_input.metadata["linkUrl"] == "https://example.com/pipefy"


@pytest.mark.unit
def test_update_portal_element_input_rejects_blank_element_id() -> None:
    with pytest.raises(ValidationError, match="element_id"):
        UpdatePortalElementInput(
            element_id="   ",
            page_id=_PAGE_ID,
            type="link",
            metadata=_VALID_LINK_METADATA,
        )


@pytest.mark.unit
def test_update_portal_element_input_rejects_invalid_link_metadata() -> None:
    with pytest.raises(ValidationError, match="linkName"):
        UpdatePortalElementInput(
            element_id=_ELEMENT_ID,
            page_id=_PAGE_ID,
            type="link",
            metadata={},
        )


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
