"""Tests for attachment MCP tools (mocked PipefyClient)."""

import base64
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import PipefyClient
from pipefy_sdk.attachment_upload import AttachmentUploadError

from pipefy_mcp.tools.attachment_tools import AttachmentTools
from pipefy_mcp.tools.tool_error_envelope import tool_error_message


@pytest.fixture
def mock_attachment_client():
    from pipefy_sdk.models.attachment import infer_content_type

    client = MagicMock(PipefyClient)

    async def _upload_card(**kwargs):
        fb = kwargs["file_bytes"]
        fn = kwargs["file_name"]
        ct = kwargs.get("content_type") or infer_content_type(fn)
        return {
            "file_name": fn,
            "content_type": ct,
            "file_size": len(fb),
            "field_id": kwargs["field_id"],
            "storage_path": "orgs/o/u/f/report.pdf",
            "download_url": "https://app.pipefy.com/storage/v1/signed/z",
        }

    async def _upload_record(**kwargs):
        fb = kwargs["file_bytes"]
        fn = kwargs["file_name"]
        ct = kwargs.get("content_type") or infer_content_type(fn)
        return {
            "file_name": fn,
            "content_type": ct,
            "file_size": len(fb),
            "field_id": kwargs["field_id"],
            "storage_path": "orgs/o/u/f/report.pdf",
            "download_url": "https://app.pipefy.com/storage/v1/signed/z",
        }

    client.upload_attachment_to_card_field = AsyncMock(side_effect=_upload_card)
    client.upload_attachment_to_table_record_field = AsyncMock(
        side_effect=_upload_record
    )
    return client


@pytest.fixture
def attachment_mcp_server(mock_attachment_client):
    mcp = FastMCP("Attachment Tools Test")
    AttachmentTools.register(mcp, mock_attachment_client)
    return mcp


@pytest.fixture
def attachment_session(attachment_mcp_server):
    return create_client_session(
        attachment_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )


# ---------------------------------------------------------------------------
# file_path: happy paths
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_upload_attachment_to_card_file_path_success(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    f = tmp_path / "report.pdf"
    f.write_bytes(b"pdf-bytes")

    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 7,
                "field_id": "field-uuid",
                "file_path": str(f),
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["card_id"] == "7"
    assert payload["field_id"] == "field-uuid"
    assert payload["file_name"] == "report.pdf"
    assert payload["content_type"] == "application/pdf"
    assert payload["file_size"] == len(b"pdf-bytes")
    assert "download_url" in payload

    mock_attachment_client.upload_attachment_to_card_field.assert_awaited_once()
    call_kw = mock_attachment_client.upload_attachment_to_card_field.await_args.kwargs
    assert call_kw["file_name"] == "report.pdf"
    assert call_kw["file_bytes"] == b"pdf-bytes"


@pytest.mark.anyio
async def test_upload_attachment_to_card_file_path_explicit_file_name_overrides(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    f = tmp_path / "abc123.pdf"
    f.write_bytes(b"data")

    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 7,
                "field_id": "f",
                "file_name": "Invoice 2026.pdf",
                "file_path": str(f),
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["file_name"] == "Invoice 2026.pdf"


@pytest.mark.anyio
async def test_upload_attachment_to_card_file_path_expands_tilde(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
    monkeypatch,
):
    """``~`` in file_path resolves against HOME so programmatic callers work."""
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "tilde.bin"
    f.write_bytes(b"home-bytes")

    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "1",
                "card_id": 1,
                "field_id": "f",
                "file_path": "~/tilde.bin",
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["file_name"] == "tilde.bin"
    call_kw = mock_attachment_client.upload_attachment_to_card_field.await_args.kwargs
    assert call_kw["file_bytes"] == b"home-bytes"


@pytest.mark.anyio
async def test_upload_attachment_to_table_record_file_path_success(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    f = tmp_path / "data.csv"
    f.write_bytes(b"id,name\n1,foo\n")

    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_table_record",
            {
                "organization_id": "42",
                "table_record_id": "999",
                "field_id": "tf",
                "file_path": str(f),
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["table_record_id"] == "999"
    assert payload["content_type"] == "text/csv"
    assert payload["file_name"] == "data.csv"
    call_kw = (
        mock_attachment_client.upload_attachment_to_table_record_field.await_args.kwargs
    )
    assert call_kw["table_record_id"] == "999"
    assert call_kw["file_bytes"] == b"id,name\n1,foo\n"


# ---------------------------------------------------------------------------
# file_path: failure modes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_upload_attachment_to_card_file_path_missing(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    """A non-existent path fails at file_read step, never reaches presigned URL."""
    missing = tmp_path / "does-not-exist.pdf"
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
                "file_path": str(missing),
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "file_read"
    assert "not found" in tool_error_message(payload).lower()
    mock_attachment_client.upload_attachment_to_card_field.assert_not_called()


@pytest.mark.anyio
async def test_upload_attachment_to_card_file_path_is_directory(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    """A directory is not a regular file — same file_read failure."""
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
                "file_path": str(tmp_path),
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "file_read"
    mock_attachment_client.upload_attachment_to_card_field.assert_not_called()


# ---------------------------------------------------------------------------
# Base64 path: behavior unchanged by the file_path refactor
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_upload_attachment_to_card_base64_success(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    raw = b"hello"
    b64 = base64.b64encode(raw).decode("ascii")

    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 7,
                "field_id": "f1",
                "file_name": "note.txt",
                "file_content_base64": b64,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["file_size"] == 5
    mock_attachment_client.upload_attachment_to_card_field.assert_awaited_once()
    call_kw = mock_attachment_client.upload_attachment_to_card_field.await_args.kwargs
    assert call_kw["organization_id"] == "42"
    assert call_kw["file_name"] == "note.txt"
    assert call_kw["file_bytes"] == raw


@pytest.mark.anyio
async def test_upload_attachment_to_card_base64_requires_file_name(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    """base64 source has no path to infer file_name from; validator should fail."""
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
                "file_content_base64": base64.b64encode(b"x").decode("ascii"),
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "validation"
    mock_attachment_client.upload_attachment_to_card_field.assert_not_called()


@pytest.mark.anyio
async def test_upload_attachment_to_card_rejects_oversize_file_path(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
    monkeypatch,
):
    """A file larger than the cap fails at file_read; SDK upload never runs."""
    monkeypatch.setattr(
        "pipefy_sdk.models.attachment.MAX_ATTACHMENT_SIZE_BYTES",
        10,
    )
    f = tmp_path / "big.bin"
    f.write_bytes(b"more-than-ten-bytes")

    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
                "file_path": str(f),
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "file_read"
    assert "too large" in tool_error_message(payload).lower()
    mock_attachment_client.upload_attachment_to_card_field.assert_not_called()


@pytest.mark.anyio
async def test_upload_attachment_to_card_rejects_oversize_base64(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    monkeypatch,
):
    """Decoded base64 above the cap fails at file_read; SDK upload never runs."""
    monkeypatch.setattr(
        "pipefy_sdk.models.attachment.MAX_ATTACHMENT_SIZE_BYTES",
        4,
    )
    b64 = base64.b64encode(b"more-than-four-bytes").decode("ascii")

    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
                "file_name": "x.bin",
                "file_content_base64": b64,
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "file_read"
    assert "too large" in tool_error_message(payload).lower()
    mock_attachment_client.upload_attachment_to_card_field.assert_not_called()


@pytest.mark.anyio
async def test_upload_attachment_to_card_whitespace_file_path_falls_through_to_base64(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    """Whitespace-only file_path is treated as no path (matching SDK validator's
    `_source_nonempty`), so the base64 source is used instead of failing with
    a misleading file_read error.
    """
    raw = b"fallback-bytes"
    b64 = base64.b64encode(raw).decode("ascii")

    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
                "file_name": "note.txt",
                "file_path": "  ",
                "file_content_base64": b64,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    call_kw = mock_attachment_client.upload_attachment_to_card_field.await_args.kwargs
    assert call_kw["file_bytes"] == raw
    assert call_kw["file_name"] == "note.txt"


# ---------------------------------------------------------------------------
# SDK pipeline failures propagate as step-aware envelopes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_upload_attachment_to_card_presigned_url_missing(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_attachment_client.upload_attachment_to_card_field = AsyncMock(
        side_effect=AttachmentUploadError(
            "Pipefy did not return a presigned upload URL.",
            step="presigned_url",
        )
    )
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
                "file_name": "a.bin",
                "file_content_base64": "YWIj",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "presigned_url"
    mock_attachment_client.upload_attachment_to_card_field.assert_awaited_once()


@pytest.mark.anyio
async def test_upload_attachment_to_card_presigned_graphql_error(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    def _raise_upload(*_a, **_k):
        gql_exc = TransportQueryError("x", errors=[{"message": "org denied"}])
        raise AttachmentUploadError(
            f"Presigned URL request failed: {gql_exc}",
            step="presigned_url",
        ) from gql_exc

    mock_attachment_client.upload_attachment_to_card_field = AsyncMock(
        side_effect=_raise_upload
    )
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
                "file_name": "a.bin",
                "file_content_base64": "YWIj",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "presigned_url"
    assert "denied" in tool_error_message(payload)


@pytest.mark.anyio
async def test_upload_attachment_to_card_s3_failure(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_attachment_client.upload_attachment_to_card_field = AsyncMock(
        side_effect=AttachmentUploadError(
            "S3 upload failed with HTTP 403.",
            step="s3_upload",
            body_snippet="<Error/>",
            status_code=403,
        )
    )
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
                "file_name": "a.bin",
                "file_content_base64": "YWIj",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "s3_upload"


@pytest.mark.anyio
async def test_upload_attachment_to_card_field_update_failure(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    def _raise_field(*_a, **_k):
        inner = TransportQueryError(
            "x", errors=[{"message": "field must be attachment"}]
        )
        raise AttachmentUploadError(
            f"Field update failed: {inner}",
            step="field_update",
        ) from inner

    mock_attachment_client.upload_attachment_to_card_field = AsyncMock(
        side_effect=_raise_field
    )
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
                "file_name": "a.bin",
                "file_content_base64": "YWIj",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "field_update"
    assert "attachment" in tool_error_message(payload)


@pytest.mark.anyio
async def test_upload_attachment_to_card_validation_both_sources(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
                "file_name": "a.bin",
                "file_path": str(f),
                "file_content_base64": base64.b64encode(b"x").decode("ascii"),
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "validation"
    mock_attachment_client.upload_attachment_to_card_field.assert_not_called()


@pytest.mark.anyio
async def test_upload_attachment_to_table_record_base64_and_presigned_error(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_attachment_client.upload_attachment_to_table_record_field = AsyncMock(
        side_effect=AttachmentUploadError(
            "Pipefy did not return a presigned upload URL.",
            step="presigned_url",
        )
    )
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_table_record",
            {
                "organization_id": "42",
                "table_record_id": "r1",
                "field_id": "tf",
                "file_name": "x.bin",
                "file_content_base64": "QQ==",
            },
        )
    payload = extract_payload(result)
    assert payload["step"] == "presigned_url"


@pytest.mark.anyio
async def test_upload_attachment_to_table_record_s3_failure(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_attachment_client.upload_attachment_to_table_record_field = AsyncMock(
        side_effect=AttachmentUploadError(
            "S3 upload failed with HTTP 500.",
            step="s3_upload",
            status_code=500,
        )
    )
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_table_record",
            {
                "organization_id": "42",
                "table_record_id": "r1",
                "field_id": "tf",
                "file_name": "x.bin",
                "file_content_base64": "QQ==",
            },
        )
    payload = extract_payload(result)
    assert payload["step"] == "s3_upload"


@pytest.mark.anyio
async def test_upload_attachment_to_table_field_update_failure(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    def _raise_field(*_a, **_k):
        inner = TransportQueryError("e", errors=[{"message": "invalid field"}])
        raise AttachmentUploadError(
            f"Field update failed: {inner}",
            step="field_update",
        ) from inner

    mock_attachment_client.upload_attachment_to_table_record_field = AsyncMock(
        side_effect=_raise_field
    )
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_table_record",
            {
                "organization_id": "42",
                "table_record_id": "r1",
                "field_id": "tf",
                "file_name": "x.bin",
                "file_content_base64": "QQ==",
            },
        )
    payload = extract_payload(result)
    assert payload["step"] == "field_update"


# ---------------------------------------------------------------------------
# PipefyId coercion: int → str through MCP transport (mcporter mitigation)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_upload_attachment_to_card_coerces_int_ids(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    raw = b"hello"
    b64 = base64.b64encode(raw).decode("ascii")

    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": 42,
                "card_id": 7,
                "field_id": 999,
                "file_name": "note.txt",
                "file_content_base64": b64,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    mock_attachment_client.upload_attachment_to_card_field.assert_awaited_once()
    call_kw = mock_attachment_client.upload_attachment_to_card_field.await_args.kwargs
    assert call_kw["organization_id"] == "42"
    assert call_kw["card_id"] == "7"
    assert call_kw["field_id"] == "999"
    assert call_kw["file_bytes"] == raw


@pytest.mark.anyio
async def test_upload_attachment_to_table_record_coerces_int_ids(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    raw = b"hello"
    b64 = base64.b64encode(raw).decode("ascii")

    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_table_record",
            {
                "organization_id": 42,
                "table_record_id": 200,
                "field_id": 300,
                "file_name": "data.csv",
                "file_content_base64": b64,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    mock_attachment_client.upload_attachment_to_table_record_field.assert_awaited_once()
    call_kw = (
        mock_attachment_client.upload_attachment_to_table_record_field.await_args.kwargs
    )
    assert call_kw["organization_id"] == "42"
    assert call_kw["table_record_id"] == "200"
    assert call_kw["field_id"] == "300"
    assert call_kw["file_bytes"] == raw
