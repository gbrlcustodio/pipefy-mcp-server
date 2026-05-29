"""Tests for the Attachment domain object."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pipefy_infra.filesystem import LocalFile

from pipefy_sdk.attachment import Attachment
from pipefy_sdk.attachment_upload import AttachmentUploadError


def _read_local_file(
    tmp_path: Path, name: str = "report.pdf", body: bytes = b"x"
) -> LocalFile:
    f = tmp_path / name
    f.write_bytes(body)
    file = LocalFile(f)
    file.read()
    return file


@pytest.mark.unit
def test_attachment_name_defaults_to_file_basename(tmp_path: Path):
    file = _read_local_file(tmp_path, "report.pdf")
    attachment = Attachment(file)
    assert attachment.name == "report.pdf"


@pytest.mark.unit
def test_attachment_explicit_name_wins(tmp_path: Path):
    file = _read_local_file(tmp_path, "abc123.pdf")
    attachment = Attachment(file, name="Invoice 2026.pdf")
    assert attachment.name == "Invoice 2026.pdf"


@pytest.mark.unit
def test_attachment_blank_explicit_name_falls_back_to_basename(tmp_path: Path):
    """Whitespace-only explicit name is treated as not provided."""
    file = _read_local_file(tmp_path, "report.pdf")
    attachment = Attachment(file, name="   ")
    assert attachment.name == "report.pdf"


@pytest.mark.unit
def test_attachment_content_type_inferred_from_name(tmp_path: Path):
    file = _read_local_file(tmp_path, "data.csv")
    attachment = Attachment(file)
    assert attachment.content_type == "text/csv"


@pytest.mark.unit
def test_attachment_explicit_content_type_wins(tmp_path: Path):
    file = _read_local_file(tmp_path, "data.csv")
    attachment = Attachment(file, content_type="application/octet-stream")
    assert attachment.content_type == "application/octet-stream"


@pytest.mark.unit
def test_attachment_exposes_underlying_file(tmp_path: Path):
    file = _read_local_file(tmp_path, "data.bin", body=b"abcdef")
    attachment = Attachment(file)
    assert attachment.file is file
    assert attachment.file.size == 6


@pytest.mark.unit
def test_attachment_pre_upload_result_is_none(tmp_path: Path):
    """Before any upload, ``result`` is None and the URL/path properties raise."""
    file = _read_local_file(tmp_path)
    attachment = Attachment(file)
    assert attachment.result is None
    with pytest.raises(RuntimeError, match="upload"):
        _ = attachment.download_url
    with pytest.raises(RuntimeError, match="upload"):
        _ = attachment.storage_path


@pytest.mark.anyio
async def test_attachment_upload_to_card_field_populates_result(tmp_path: Path):
    file = _read_local_file(tmp_path, "doc.pdf", body=b"pdf")
    attachment = Attachment(file)
    client = MagicMock()
    expected = {
        "file_name": "doc.pdf",
        "content_type": "application/pdf",
        "file_size": 3,
        "field_id": "f",
        "storage_path": "orgs/o/x/doc.pdf",
        "download_url": "https://app.pipefy.com/signed",
    }
    client.upload_attachment_to_card_field = AsyncMock(return_value=expected)

    result = await attachment.upload_to_card_field(
        client,
        organization_id="42",
        card_id="7",
        field_id="f",
    )

    assert result == expected
    assert attachment.result == expected
    assert attachment.download_url == "https://app.pipefy.com/signed"
    assert attachment.storage_path == "orgs/o/x/doc.pdf"
    client.upload_attachment_to_card_field.assert_awaited_once_with(
        organization_id="42",
        card_id="7",
        field_id="f",
        file_name="doc.pdf",
        file_bytes=b"pdf",
        content_type=None,
    )


@pytest.mark.anyio
async def test_attachment_upload_to_table_record_passes_explicit_content_type(
    tmp_path: Path,
):
    file = _read_local_file(tmp_path, "data.bin", body=b"abc")
    attachment = Attachment(file, name="x.bin", content_type="application/octet-stream")
    client = MagicMock()
    client.upload_attachment_to_table_record_field = AsyncMock(
        return_value={
            "file_name": "x.bin",
            "content_type": "application/octet-stream",
            "file_size": 3,
            "field_id": "tf",
            "storage_path": "orgs/o/r/x.bin",
            "download_url": None,
        }
    )

    await attachment.upload_to_table_record_field(
        client,
        organization_id="42",
        table_record_id="r1",
        field_id="tf",
    )

    client.upload_attachment_to_table_record_field.assert_awaited_once_with(
        organization_id="42",
        table_record_id="r1",
        field_id="tf",
        file_name="x.bin",
        file_bytes=b"abc",
        content_type="application/octet-stream",
    )


@pytest.mark.anyio
async def test_attachment_upload_failure_leaves_result_unset(tmp_path: Path):
    file = _read_local_file(tmp_path, "a.bin")
    attachment = Attachment(file)
    client = MagicMock()
    client.upload_attachment_to_card_field = AsyncMock(
        side_effect=AttachmentUploadError("nope", step="presigned_url"),
    )

    with pytest.raises(AttachmentUploadError):
        await attachment.upload_to_card_field(
            client,
            organization_id="42",
            card_id="1",
            field_id="f",
        )
    assert attachment.result is None
    with pytest.raises(RuntimeError, match="upload"):
        _ = attachment.download_url
