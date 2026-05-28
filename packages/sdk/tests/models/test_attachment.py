"""Tests for attachment upload Pydantic models."""

import pytest
from pydantic import ValidationError

from pipefy_sdk.models.attachment import (
    MAX_ATTACHMENT_SIZE_BYTES,
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
    assert_attachment_size_within_cap,
    infer_content_type,
)


def _base_kwargs():
    return {
        "organization_id": "org-1",
        "field_id": "field_abc",
        "file_name": "doc.pdf",
    }


@pytest.mark.unit
def test_upload_attachment_to_card_accepts_file_path():
    data = UploadAttachmentToCardInput(
        **_base_kwargs(),
        card_id=42,
        file_path="/tmp/f.pdf",
        file_content_base64=None,
    )
    assert data.card_id == "42"
    assert data.file_path == "/tmp/f.pdf"
    assert data.file_content_base64 is None


@pytest.mark.unit
def test_upload_attachment_to_card_coerces_int_card_id():
    """card_id uses PipefyId — int input should be coerced to string."""
    data = UploadAttachmentToCardInput(
        **_base_kwargs(),
        card_id=99,
        file_path="/tmp/f.pdf",
    )
    assert data.card_id == "99"


@pytest.mark.unit
def test_upload_attachment_to_card_accepts_string_card_id():
    """card_id uses PipefyId — string IDs should pass through."""
    data = UploadAttachmentToCardInput(
        **_base_kwargs(),
        card_id="Yr5RUVCi",
        file_path="/tmp/f.pdf",
    )
    assert data.card_id == "Yr5RUVCi"


@pytest.mark.unit
def test_upload_attachment_to_card_accepts_base64():
    data = UploadAttachmentToCardInput(
        **_base_kwargs(),
        card_id=1,
        file_path=None,
        file_content_base64="YWFh",
    )
    assert data.file_path is None
    assert data.file_content_base64 == "YWFh"


@pytest.mark.unit
def test_upload_attachment_to_card_rejects_both_sources():
    with pytest.raises(ValueError, match="not both"):
        UploadAttachmentToCardInput(
            **_base_kwargs(),
            card_id=1,
            file_path="/tmp/a",
            file_content_base64="YWFh",
        )


@pytest.mark.unit
def test_upload_attachment_to_card_rejects_neither_source():
    with pytest.raises(ValueError, match="exactly one"):
        UploadAttachmentToCardInput(
            **_base_kwargs(),
            card_id=1,
            file_path=None,
            file_content_base64=None,
        )


@pytest.mark.unit
def test_upload_attachment_to_card_rejects_both_empty_strings():
    with pytest.raises(ValueError, match="exactly one"):
        UploadAttachmentToCardInput(
            **_base_kwargs(),
            card_id=1,
            file_path="   ",
            file_content_base64="",
        )


@pytest.mark.unit
def test_upload_attachment_to_card_derives_file_name_from_path():
    """When file_name is omitted, the path's basename fills it in."""
    data = UploadAttachmentToCardInput(
        organization_id="o",
        card_id=1,
        field_id="f",
        file_path="/tmp/project/report-final.pdf",
    )
    assert data.file_name == "report-final.pdf"


@pytest.mark.unit
def test_upload_attachment_to_card_explicit_file_name_overrides_basename():
    """Explicit file_name wins over path basename."""
    data = UploadAttachmentToCardInput(
        organization_id="o",
        card_id=1,
        field_id="f",
        file_name="Invoice 2026.pdf",
        file_path="/tmp/abc123.pdf",
    )
    assert data.file_name == "Invoice 2026.pdf"


@pytest.mark.unit
def test_upload_attachment_to_card_base64_requires_explicit_file_name():
    """base64 source carries no path to infer from; file_name must be provided."""
    with pytest.raises(ValueError, match="file_name is required"):
        UploadAttachmentToCardInput(
            organization_id="o",
            card_id=1,
            field_id="f",
            file_content_base64="YWFh",
        )


@pytest.mark.unit
@pytest.mark.parametrize("path", ["/", "."])
def test_upload_attachment_to_card_rejects_file_path_with_empty_basename(path):
    """file_path that yields an empty basename must not silently set file_name=''."""
    with pytest.raises(ValueError, match="no basename"):
        UploadAttachmentToCardInput(
            organization_id="o",
            card_id=1,
            field_id="f",
            file_path=path,
        )


@pytest.mark.unit
def test_upload_attachment_to_card_content_type_optional_none():
    data = UploadAttachmentToCardInput(
        **_base_kwargs(),
        card_id=1,
        file_path="/tmp/x",
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
        file_path="/tmp/x",
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
            file_path="/tmp/a",
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
def test_upload_attachment_to_table_record_derives_file_name_from_path():
    data = UploadAttachmentToTableRecordInput(
        organization_id="o",
        table_record_id="tr-1",
        field_id="f",
        file_path="/var/data/export.csv",
    )
    assert data.file_name == "export.csv"


@pytest.mark.unit
def test_upload_attachment_to_table_record_missing_required_field():
    with pytest.raises(ValidationError):
        UploadAttachmentToTableRecordInput(
            organization_id="o",
            # table_record_id missing
            field_id="f",
            file_name="n",
            file_path="/tmp/x",
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
def test_upload_attachment_to_card_coerces_int_organization_id():
    data = UploadAttachmentToCardInput(
        organization_id=12345,
        card_id=42,
        field_id="field_abc",
        file_name="doc.pdf",
        file_path="/tmp/f.pdf",
    )
    assert data.organization_id == "12345"


@pytest.mark.unit
def test_upload_attachment_to_card_coerces_int_field_id():
    data = UploadAttachmentToCardInput(
        organization_id="org-1",
        card_id=42,
        field_id=999,
        file_name="doc.pdf",
        file_path="/tmp/f.pdf",
    )
    assert data.field_id == "999"


@pytest.mark.unit
def test_upload_attachment_to_table_record_coerces_int_ids():
    data = UploadAttachmentToTableRecordInput(
        organization_id=100,
        table_record_id=200,
        field_id=300,
        file_name="n.csv",
        file_path="/tmp/x",
    )
    assert data.organization_id == "100"
    assert data.table_record_id == "200"
    assert data.field_id == "300"


@pytest.mark.unit
def test_models_exported_from_package():
    from pipefy_sdk.models import (
        UploadAttachmentToCardInput as CardFromPkg,
    )
    from pipefy_sdk.models import (
        UploadAttachmentToTableRecordInput as TableFromPkg,
    )
    from pipefy_sdk.models import (
        infer_content_type as infer_from_pkg,
    )

    assert CardFromPkg is UploadAttachmentToCardInput
    assert TableFromPkg is UploadAttachmentToTableRecordInput
    assert infer_from_pkg is infer_content_type


@pytest.mark.unit
def test_assert_attachment_size_within_cap_accepts_at_or_below_cap():
    """At-cap and below-cap sizes return without raising."""
    assert_attachment_size_within_cap(0, "empty")
    assert_attachment_size_within_cap(MAX_ATTACHMENT_SIZE_BYTES, "exact")
    assert_attachment_size_within_cap(MAX_ATTACHMENT_SIZE_BYTES - 1, "just-below")


@pytest.mark.unit
def test_assert_attachment_size_within_cap_rejects_above_cap():
    """Any size above the cap raises ValueError citing the source label."""
    with pytest.raises(ValueError, match="too large") as exc_info:
        assert_attachment_size_within_cap(MAX_ATTACHMENT_SIZE_BYTES + 1, "/tmp/big.bin")
    msg = str(exc_info.value)
    assert "/tmp/big.bin" in msg
    assert "MiB" in msg
