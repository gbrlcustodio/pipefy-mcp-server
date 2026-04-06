"""Tests for attachment upload Pydantic models."""

import pytest
from pydantic import ValidationError

from pipefy_mcp.models.attachment import (
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
    infer_content_type,
)


def _base_kwargs():
    return {
        "organization_id": "org-1",
        "field_id": "field_abc",
        "file_name": "doc.pdf",
    }


@pytest.mark.unit
def test_upload_attachment_to_card_accepts_file_url():
    data = UploadAttachmentToCardInput(
        **_base_kwargs(),
        card_id=42,
        file_url="https://example.com/f.pdf",
        file_content_base64=None,
    )
    assert data.file_url == "https://example.com/f.pdf"
    assert data.file_content_base64 is None


@pytest.mark.unit
def test_upload_attachment_to_card_accepts_base64():
    data = UploadAttachmentToCardInput(
        **_base_kwargs(),
        card_id=1,
        file_url=None,
        file_content_base64="YWFh",
    )
    assert data.file_url is None
    assert data.file_content_base64 == "YWFh"


@pytest.mark.unit
def test_upload_attachment_to_card_rejects_both_sources():
    with pytest.raises(ValueError, match="not both"):
        UploadAttachmentToCardInput(
            **_base_kwargs(),
            card_id=1,
            file_url="https://example.com/a",
            file_content_base64="YWFh",
        )


@pytest.mark.unit
def test_upload_attachment_to_card_rejects_neither_source():
    with pytest.raises(ValueError, match="exactly one"):
        UploadAttachmentToCardInput(
            **_base_kwargs(),
            card_id=1,
            file_url=None,
            file_content_base64=None,
        )


@pytest.mark.unit
def test_upload_attachment_to_card_rejects_both_empty_strings():
    with pytest.raises(ValueError, match="exactly one"):
        UploadAttachmentToCardInput(
            **_base_kwargs(),
            card_id=1,
            file_url="   ",
            file_content_base64="",
        )


@pytest.mark.unit
def test_upload_attachment_to_card_missing_required_field():
    with pytest.raises(ValidationError):
        UploadAttachmentToCardInput(
            organization_id="o",
            card_id=1,
            field_id="f",
            # file_name missing
            file_url="https://x",
        )


@pytest.mark.unit
def test_upload_attachment_to_card_content_type_optional_none():
    data = UploadAttachmentToCardInput(
        **_base_kwargs(),
        card_id=1,
        file_url="https://example.com/x",
        content_type=None,
    )
    assert data.content_type is None


@pytest.mark.unit
def test_upload_attachment_to_table_record_uses_table_record_id_not_card_id():
    data = UploadAttachmentToTableRecordInput(
        organization_id="org-1",
        table_record_id="tr-999",
        field_id="f",
        file_name="n.csv",
        file_url="https://example.com/x",
    )
    assert data.table_record_id == "tr-999"
    assert not hasattr(data, "card_id")


@pytest.mark.unit
def test_upload_attachment_to_table_record_accepts_base64():
    data = UploadAttachmentToTableRecordInput(
        organization_id="o",
        table_record_id="tr-1",
        field_id="f",
        file_name="n.bin",
        file_content_base64="QQ==",
    )
    assert data.file_content_base64 == "QQ=="


@pytest.mark.unit
def test_upload_attachment_to_table_record_rejects_both_sources():
    with pytest.raises(ValueError, match="not both"):
        UploadAttachmentToTableRecordInput(
            organization_id="o",
            table_record_id="tr-1",
            field_id="f",
            file_name="n",
            file_url="https://a",
            file_content_base64="YQ==",
        )


@pytest.mark.unit
def test_upload_attachment_to_table_record_rejects_neither_source():
    with pytest.raises(ValueError, match="exactly one"):
        UploadAttachmentToTableRecordInput(
            organization_id="o",
            table_record_id="tr-1",
            field_id="f",
            file_name="n",
        )


@pytest.mark.unit
def test_upload_attachment_to_table_record_missing_required_field():
    with pytest.raises(ValidationError):
        UploadAttachmentToTableRecordInput(
            organization_id="o",
            # table_record_id missing
            field_id="f",
            file_name="n",
            file_url="https://x",
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "file_name,expected",
    [
        ("report.pdf", "application/pdf"),
        ("data.csv", "text/csv"),
        ("img.png", "image/png"),
        ("photo.jpg", "image/jpeg"),
        (
            "letter.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("unknown.xyz", "application/octet-stream"),
        ("noextension", "application/octet-stream"),
    ],
)
def test_infer_content_type(file_name, expected):
    assert infer_content_type(file_name) == expected


@pytest.mark.unit
def test_models_exported_from_package():
    from pipefy_mcp.models import (
        UploadAttachmentToCardInput as CardFromPkg,
    )
    from pipefy_mcp.models import (
        UploadAttachmentToTableRecordInput as TableFromPkg,
    )
    from pipefy_mcp.models import (
        infer_content_type as infer_from_pkg,
    )

    assert CardFromPkg is UploadAttachmentToCardInput
    assert TableFromPkg is UploadAttachmentToTableRecordInput
    assert infer_from_pkg is infer_content_type
