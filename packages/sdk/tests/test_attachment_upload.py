"""Unit tests for ``pipefy_sdk.attachment_upload`` (presigned → S3 → field update)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError

from pipefy_sdk.attachment_upload import (
    AttachmentUploadError,
    upload_attachment_to_card_field,
    upload_attachment_to_table_record_field,
)

PRESIGNED = {
    "url": "https://s3.example.com/bucket/key?sig=1",
    "download_url": "https://app.pipefy.com/dl/1",
}


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.create_presigned_url = AsyncMock(return_value=PRESIGNED)
    client.upload_file_to_s3 = AsyncMock(return_value={"status_code": 200})
    client.extract_storage_path = MagicMock(return_value="bucket/key")
    client.update_card_field = AsyncMock(return_value={"ok": True})
    client.set_table_record_field_value = AsyncMock(return_value={"ok": True})
    return client


@pytest.mark.asyncio
async def test_upload_card_happy_path_infers_content_type(mock_client):
    result = await upload_attachment_to_card_field(
        mock_client,
        organization_id="org-1",
        card_id="c1",
        field_id="title",
        file_name="report.pdf",
        file_bytes=b"%PDF-1.4",
    )
    assert result["file_name"] == "report.pdf"
    assert result["content_type"] == "application/pdf"
    assert result["file_size"] == 8
    assert result["field_id"] == "title"
    assert result["storage_path"] == "bucket/key"
    assert result["download_url"] == "https://app.pipefy.com/dl/1"
    mock_client.create_presigned_url.assert_awaited_once()
    mock_client.upload_file_to_s3.assert_awaited_once()
    mock_client.update_card_field.assert_awaited_once_with(
        "c1", "title", ["bucket/key"]
    )


@pytest.mark.asyncio
async def test_upload_card_respects_explicit_content_type(mock_client):
    await upload_attachment_to_card_field(
        mock_client,
        organization_id="org-1",
        card_id="c1",
        field_id="f",
        file_name="x.bin",
        file_bytes=b"a",
        content_type="application/octet-stream",
    )
    args = mock_client.create_presigned_url.await_args
    assert args[0][2] == "application/octet-stream"


@pytest.mark.asyncio
async def test_create_presigned_url_raises_attachment_upload_error(mock_client):
    mock_client.create_presigned_url = AsyncMock(
        side_effect=TransportQueryError("x", errors=[{"message": "denied"}])
    )
    with pytest.raises(AttachmentUploadError) as ctx:
        await upload_attachment_to_card_field(
            mock_client,
            organization_id="org-1",
            card_id="c1",
            field_id="f",
            file_name="a.txt",
            file_bytes=b"x",
        )
    assert ctx.value.step == "presigned_url"
    assert ctx.value.__cause__ is not None


@pytest.mark.asyncio
async def test_missing_upload_url_raises_presigned_step(mock_client):
    mock_client.create_presigned_url = AsyncMock(
        return_value={"url": "", "download_url": None}
    )
    with pytest.raises(AttachmentUploadError) as excinfo:
        await upload_attachment_to_card_field(
            mock_client,
            organization_id="org-1",
            card_id="c1",
            field_id="f",
            file_name="a.bin",
            file_bytes=b"x",
        )
    assert excinfo.value.step == "presigned_url"
    assert excinfo.value.__cause__ is None


@pytest.mark.asyncio
async def test_s3_http_error_carries_snippet_and_status_code(mock_client):
    mock_client.upload_file_to_s3 = AsyncMock(
        return_value={"status_code": 403, "body_snippet": "<Error/>"}
    )
    with pytest.raises(AttachmentUploadError) as ctx:
        await upload_attachment_to_card_field(
            mock_client,
            organization_id="org-1",
            card_id="c1",
            field_id="f",
            file_name="a.bin",
            file_bytes=b"x",
        )
    assert ctx.value.step == "s3_upload"
    assert ctx.value.body_snippet == "<Error/>"
    assert ctx.value.status_code == 403


@pytest.mark.asyncio
async def test_extract_storage_path_valueerror_maps_to_s3_step(mock_client):
    mock_client.extract_storage_path = MagicMock(
        side_effect=ValueError("cannot parse storage path")
    )
    with pytest.raises(AttachmentUploadError) as ctx:
        await upload_attachment_to_card_field(
            mock_client,
            organization_id="org-1",
            card_id="c1",
            field_id="f",
            file_name="a.bin",
            file_bytes=b"x",
        )
    assert ctx.value.step == "s3_upload"
    assert isinstance(ctx.value.__cause__, ValueError)


@pytest.mark.asyncio
async def test_field_update_failure_maps_to_field_update_step(mock_client):
    mock_client.update_card_field = AsyncMock(side_effect=RuntimeError("graphql boom"))
    with pytest.raises(AttachmentUploadError) as ctx:
        await upload_attachment_to_card_field(
            mock_client,
            organization_id="org-1",
            card_id="c1",
            field_id="f",
            file_name="a.bin",
            file_bytes=b"x",
        )
    assert ctx.value.step == "field_update"
    assert isinstance(ctx.value.__cause__, RuntimeError)


@pytest.mark.asyncio
async def test_upload_table_record_uses_set_table_record_field_value(mock_client):
    await upload_attachment_to_table_record_field(
        mock_client,
        organization_id="org-1",
        table_record_id="tr-9",
        field_id="att",
        file_name="data.csv",
        file_bytes=b"a,b",
    )
    mock_client.update_card_field.assert_not_called()
    mock_client.set_table_record_field_value.assert_awaited_once_with(
        "tr-9", "att", ["bucket/key"]
    )
