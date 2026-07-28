"""Tests for attachment domain types and Pydantic input DTOs."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from pipefy_sdk.models.attachment import (
    Attachment,
    AttachmentTarget,
    CardTarget,
    TableRecordTarget,
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
def test_upload_attachment_to_card_accepts_file_path():
    data = UploadAttachmentToCardInput(
        **_base_kwargs(),
        card_id=42,
        file_path="/tmp/f.pdf",
    )
    assert data.card_id == "42"
    assert data.file_path == "/tmp/f.pdf"


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
def test_upload_attachment_to_card_requires_a_source():
    """Neither file_path nor file_url provided is rejected (exactly-one-of)."""
    with pytest.raises(ValidationError, match="exactly one of file_path or file_url"):
        UploadAttachmentToCardInput(
            **_base_kwargs(),
            card_id=1,
        )


@pytest.mark.unit
def test_upload_attachment_to_card_rejects_blank_source():
    """A whitespace-only source counts as absent, so it fails exactly-one-of."""
    with pytest.raises(ValidationError, match="exactly one of file_path or file_url"):
        UploadAttachmentToCardInput(
            **_base_kwargs(),
            card_id=1,
            file_path="   ",
        )


@pytest.mark.unit
def test_upload_attachment_to_card_accepts_file_url():
    data = UploadAttachmentToCardInput(
        **_base_kwargs(),
        card_id=1,
        file_url="https://files.example/report.pdf",
    )
    assert data.file_url == "https://files.example/report.pdf"
    assert data.file_path is None


@pytest.mark.unit
def test_upload_attachment_to_card_blank_path_beside_url_normalizes_to_none():
    """A blank file_path alongside a real file_url normalizes to a single source."""
    data = UploadAttachmentToCardInput(
        **_base_kwargs(),
        card_id=1,
        file_path="   ",
        file_url="https://files.example/report.pdf",
    )
    assert data.file_path is None
    assert data.file_url == "https://files.example/report.pdf"


@pytest.mark.unit
def test_upload_attachment_to_card_rejects_both_sources():
    """Providing both file_path and file_url is rejected (exactly-one-of)."""
    with pytest.raises(ValidationError, match="exactly one of file_path or file_url"):
        UploadAttachmentToCardInput(
            **_base_kwargs(),
            card_id=1,
            file_path="/tmp/f.pdf",
            file_url="https://files.example/report.pdf",
        )


@pytest.mark.unit
def test_upload_attachment_to_card_file_name_optional():
    data = UploadAttachmentToCardInput(
        organization_id="o",
        card_id=1,
        field_id="f",
        file_path="/tmp/report.pdf",
    )
    assert data.file_name is None


@pytest.mark.unit
def test_upload_attachment_to_card_content_type_optional_none():
    data = UploadAttachmentToCardInput(
        **_base_kwargs(),
        card_id=1,
        file_path="/tmp/x.pdf",
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
        file_path="/tmp/x.csv",
    )
    assert data.table_record_id == "tr-999"
    assert not hasattr(data, "card_id")


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


# Attachment domain class


@pytest.mark.unit
def test_attachment_name_defaults_to_path_basename():
    attachment = Attachment(path=Path("/tmp/report.pdf"))
    assert attachment.name == "report.pdf"


@pytest.mark.unit
def test_attachment_explicit_name_wins():
    attachment = Attachment(path=Path("/tmp/abc123.pdf"), name="Invoice 2026.pdf")
    assert attachment.name == "Invoice 2026.pdf"


@pytest.mark.unit
def test_attachment_blank_explicit_name_falls_back_to_basename():
    """Whitespace-only explicit name is treated as not provided."""
    attachment = Attachment(path=Path("/tmp/report.pdf"), name="   ")
    assert attachment.name == "report.pdf"


@pytest.mark.unit
def test_attachment_content_type_inferred_from_name():
    attachment = Attachment(path=Path("/tmp/data.csv"))
    assert attachment.content_type == "text/csv"


@pytest.mark.unit
def test_attachment_explicit_content_type_wins():
    attachment = Attachment(
        path=Path("/tmp/data.csv"),
        content_type="application/octet-stream",
    )
    assert attachment.content_type == "application/octet-stream"


@pytest.mark.unit
def test_attachment_construction_stays_pure_for_missing_path():
    """Construction does not touch the filesystem; the path is recorded as-is."""
    attachment = Attachment(path=Path("/does/not/exist/anywhere.bin"))
    assert attachment.path == Path("/does/not/exist/anywhere.bin")
    assert attachment.url is None
    assert attachment.name == "anywhere.bin"


@pytest.mark.unit
def test_attachment_url_source_name_from_url_basename():
    attachment = Attachment(url="https://files.example/a/b/report.pdf?sig=abc")
    assert attachment.path is None
    assert attachment.url == "https://files.example/a/b/report.pdf?sig=abc"
    assert attachment.name == "report.pdf"
    assert attachment.content_type == "application/pdf"


@pytest.mark.unit
def test_attachment_url_source_explicit_name_wins():
    attachment = Attachment(url="https://files.example/", name="invoice.csv")
    assert attachment.name == "invoice.csv"
    assert attachment.content_type == "text/csv"


@pytest.mark.unit
def test_attachment_url_without_basename_raises():
    """A URL whose path has no basename (and no explicit name) is rejected at construction."""
    with pytest.raises(ValueError, match="file name"):
        Attachment(url="https://files.example/")


@pytest.mark.unit
@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"path": Path("/tmp/f.pdf"), "url": "https://files.example/f.pdf"},
        {"url": "   "},
    ],
)
def test_attachment_requires_exactly_one_source(kwargs):
    with pytest.raises(ValueError, match="exactly one of path or url"):
        Attachment(**kwargs)


# Target value objects


@pytest.mark.unit
def test_card_target_is_frozen():
    target = CardTarget(card_id="c1", field_id="f1")
    assert target.card_id == "c1"
    assert target.field_id == "f1"
    with pytest.raises(Exception):
        target.card_id = "c2"  # type: ignore[misc]


@pytest.mark.unit
def test_table_record_target_is_frozen():
    target = TableRecordTarget(table_record_id="tr-1", field_id="f1")
    assert target.table_record_id == "tr-1"
    assert target.field_id == "f1"
    with pytest.raises(Exception):
        target.table_record_id = "tr-2"  # type: ignore[misc]


@pytest.mark.unit
def test_attachment_target_alias_includes_both_variants():
    """The union alias holds both dataclasses; `match` can dispatch on either."""
    cases: list[AttachmentTarget] = [
        CardTarget(card_id="c", field_id="f"),
        TableRecordTarget(table_record_id="r", field_id="f"),
    ]
    for case in cases:
        assert case.field_id == "f"
