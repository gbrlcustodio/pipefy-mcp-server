"""Tests for attachment MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_infra.filesystem import LocalFileError
from pipefy_sdk import (
    AttachmentUploadError,
    CardTarget,
    PipefyClient,
    TableRecordTarget,
)
from pipefy_sdk.models.attachment import infer_content_type

from pipefy_mcp.core.tool_error_envelope import tool_error_message
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.attachment_tools import AttachmentTools
from tools.conftest import build_tool_test_server


@pytest.fixture
def mock_attachment_client():
    client = MagicMock(PipefyClient)

    async def _upload(attachment, *, organization_id, target):
        path = attachment.path
        if path is not None and path.exists():
            body = path.read_bytes()
        else:
            body = b"downloaded-bytes"
        field_id = target.field_id
        return {
            "file_name": attachment.name,
            "content_type": attachment.content_type
            or infer_content_type(attachment.name),
            "file_size": len(body),
            "field_id": field_id,
            "storage_path": "orgs/o/u/f/report.pdf",
            "download_url": "https://app.pipefy.com/storage/v1/signed/z",
        }

    client.upload_attachment = AsyncMock(side_effect=_upload)
    return client


@pytest.fixture
def attachment_mcp_server(mock_attachment_client):
    return build_tool_test_server(
        "Attachment Tools Test", AttachmentTools.register, mock_attachment_client
    )


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

    mock_attachment_client.upload_attachment.assert_awaited_once()
    call_kw = mock_attachment_client.upload_attachment.await_args.kwargs
    assert call_kw["organization_id"] == "42"
    assert isinstance(call_kw["target"], CardTarget)
    assert call_kw["target"].card_id == "7"
    assert call_kw["target"].field_id == "field-uuid"
    attachment_arg = mock_attachment_client.upload_attachment.await_args.args[0]
    assert attachment_arg.name == "report.pdf"
    assert attachment_arg.path == f


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
async def test_upload_attachment_to_card_file_path_passes_tilde_to_service(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    """``~`` in file_path is left for the service's ``LocalFile.read`` to expand."""
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
    attachment_arg = mock_attachment_client.upload_attachment.await_args.args[0]
    assert str(attachment_arg.path) == "~/tilde.bin"


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
    call_kw = mock_attachment_client.upload_attachment.await_args.kwargs
    assert isinstance(call_kw["target"], TableRecordTarget)
    assert call_kw["target"].table_record_id == "999"
    assert call_kw["target"].field_id == "tf"


# ---------------------------------------------------------------------------
# file_path: failure modes (file_read step now raised inside the service)
# ---------------------------------------------------------------------------


def _file_read_error(message: str) -> AttachmentUploadError:
    """Build the same AttachmentUploadError shape the service raises for file_read."""
    cause = LocalFileError(message)
    exc = AttachmentUploadError(message, step="file_read")
    exc.__cause__ = cause
    return exc


@pytest.mark.anyio
async def test_upload_attachment_to_card_file_path_missing(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    """A non-existent path fails at file_read step (raised inside the service)."""
    missing = tmp_path / "does-not-exist.pdf"
    mock_attachment_client.upload_attachment = AsyncMock(
        side_effect=_file_read_error(f"File not found or not a regular file: {missing}")
    )
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


@pytest.mark.anyio
async def test_upload_attachment_to_card_file_path_unknown_user(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    """``~unknownuser`` raises in expanduser; surfaces as a file_read envelope."""
    mock_attachment_client.upload_attachment = AsyncMock(
        side_effect=_file_read_error(
            "Cannot expand ~ in ~ghost_user_does_not_exist_xyz/foo.bin: "
            "Could not determine home directory."
        )
    )
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "1",
                "card_id": 1,
                "field_id": "f",
                "file_path": "~ghost_user_does_not_exist_xyz/foo.bin",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "file_read"
    assert "expand" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_upload_attachment_to_card_oversize_file_path(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    """A file larger than the cap fails at file_read."""
    f = tmp_path / "big.bin"
    f.write_bytes(b"more-than-ten-bytes")
    mock_attachment_client.upload_attachment = AsyncMock(
        side_effect=_file_read_error(
            f"File too large: {f} is 19 bytes, exceeding the 0 MiB cap."
        )
    )

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


@pytest.mark.anyio
async def test_upload_attachment_to_card_validation_blank_file_path(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    """An empty file_path is a model-level validation error before any read."""
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
                "file_path": "  ",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "validation"
    mock_attachment_client.upload_attachment.assert_not_called()


@pytest.mark.anyio
async def test_upload_attachment_to_card_validation_missing_source(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    """Omitting both file_path and file_url yields the exactly-one-of envelope.

    Both sources are optional args, so arg-coercion succeeds and the DTO's
    exactly-one-of validator fires in the body as a ``step=validation`` error
    (not the FastMCP arg-coercion INVALID_ARGUMENTS shape).
    """
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "validation"
    assert "exactly one of file_path or file_url" in payload["error"]["message"]
    mock_attachment_client.upload_attachment.assert_not_called()


# ---------------------------------------------------------------------------
# SDK pipeline failures propagate as step-aware envelopes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_upload_attachment_to_card_presigned_url_missing(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    f = tmp_path / "a.bin"
    f.write_bytes(b"a")
    mock_attachment_client.upload_attachment = AsyncMock(
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
                "file_path": str(f),
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "presigned_url"
    mock_attachment_client.upload_attachment.assert_awaited_once()


@pytest.mark.anyio
async def test_upload_attachment_to_card_presigned_graphql_error(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    f = tmp_path / "a.bin"
    f.write_bytes(b"a")

    def _raise_upload(*_a, **_k):
        gql_exc = TransportQueryError("x", errors=[{"message": "org denied"}])
        raise AttachmentUploadError(
            f"Presigned URL request failed: {gql_exc}",
            step="presigned_url",
        ) from gql_exc

    mock_attachment_client.upload_attachment = AsyncMock(side_effect=_raise_upload)
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
    assert payload["step"] == "presigned_url"
    assert "denied" in tool_error_message(payload)


@pytest.mark.anyio
async def test_upload_attachment_to_card_s3_failure(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    f = tmp_path / "a.bin"
    f.write_bytes(b"a")
    mock_attachment_client.upload_attachment = AsyncMock(
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
                "file_path": str(f),
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
    tmp_path: Path,
):
    f = tmp_path / "a.bin"
    f.write_bytes(b"a")

    def _raise_field(*_a, **_k):
        inner = TransportQueryError(
            "x", errors=[{"message": "field must be attachment"}]
        )
        raise AttachmentUploadError(
            f"Field update failed: {inner}",
            step="field_update",
        ) from inner

    mock_attachment_client.upload_attachment = AsyncMock(side_effect=_raise_field)
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
    assert payload["step"] == "field_update"
    assert "attachment" in tool_error_message(payload)


@pytest.mark.anyio
async def test_upload_attachment_to_table_record_presigned_error(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    mock_attachment_client.upload_attachment = AsyncMock(
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
                "file_path": str(f),
            },
        )
    payload = extract_payload(result)
    assert payload["step"] == "presigned_url"


@pytest.mark.anyio
async def test_upload_attachment_to_table_record_s3_failure(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    mock_attachment_client.upload_attachment = AsyncMock(
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
                "file_path": str(f),
            },
        )
    payload = extract_payload(result)
    assert payload["step"] == "s3_upload"


@pytest.mark.anyio
async def test_upload_attachment_to_table_record_field_update_failure(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")

    def _raise_field(*_a, **_k):
        inner = TransportQueryError("e", errors=[{"message": "invalid field"}])
        raise AttachmentUploadError(
            f"Field update failed: {inner}",
            step="field_update",
        ) from inner

    mock_attachment_client.upload_attachment = AsyncMock(side_effect=_raise_field)
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_table_record",
            {
                "organization_id": "42",
                "table_record_id": "r1",
                "field_id": "tf",
                "file_path": str(f),
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
    tmp_path: Path,
):
    f = tmp_path / "note.txt"
    f.write_bytes(b"hello")

    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": 42,
                "card_id": 7,
                "field_id": 999,
                "file_path": str(f),
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    mock_attachment_client.upload_attachment.assert_awaited_once()
    call_kw = mock_attachment_client.upload_attachment.await_args.kwargs
    assert call_kw["organization_id"] == "42"
    assert call_kw["target"].card_id == "7"
    assert call_kw["target"].field_id == "999"


@pytest.mark.anyio
async def test_upload_attachment_to_table_record_coerces_int_ids(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    f = tmp_path / "data.csv"
    f.write_bytes(b"hello")

    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_table_record",
            {
                "organization_id": 42,
                "table_record_id": 200,
                "field_id": 300,
                "file_path": str(f),
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    mock_attachment_client.upload_attachment.assert_awaited_once()
    call_kw = mock_attachment_client.upload_attachment.await_args.kwargs
    assert call_kw["organization_id"] == "42"
    assert call_kw["target"].table_record_id == "200"
    assert call_kw["target"].field_id == "300"


# ---------------------------------------------------------------------------
# file_url: happy paths, remote gating, and the download step
# ---------------------------------------------------------------------------


def _remote_attachment_session(client):
    """A session whose runtime reports the hosted (remote) profile."""
    server = build_tool_test_server(
        "Attachment Remote Test", AttachmentTools.register, client
    )
    return create_client_session(
        server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )


@pytest.mark.anyio
async def test_upload_attachment_to_card_file_url_success(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    url = "https://files.example/report.pdf"
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 7,
                "field_id": "field-uuid",
                "file_url": url,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["file_name"] == "report.pdf"

    mock_attachment_client.upload_attachment.assert_awaited_once()
    attachment = mock_attachment_client.upload_attachment.await_args.args[0]
    assert attachment.url == url
    assert attachment.path is None


@pytest.mark.anyio
async def test_upload_attachment_to_card_rejects_file_path_on_remote(
    mock_attachment_client,
    extract_payload,
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(settings.mcp, "profile", "remote")
    f = tmp_path / "report.pdf"
    f.write_bytes(b"pdf-bytes")

    async with _remote_attachment_session(mock_attachment_client) as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 7,
                "field_id": "f",
                "file_path": str(f),
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "validation"
    assert "hosted server" in payload["error"]["message"]
    assert "file_url" in payload["error"]["message"]
    mock_attachment_client.upload_attachment.assert_not_called()


@pytest.mark.anyio
async def test_upload_attachment_to_card_allows_file_url_on_remote(
    mock_attachment_client,
    extract_payload,
    monkeypatch,
):
    monkeypatch.setattr(settings.mcp, "profile", "remote")

    async with _remote_attachment_session(mock_attachment_client) as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 7,
                "field_id": "f",
                "file_url": "https://files.example/report.pdf",
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    mock_attachment_client.upload_attachment.assert_awaited_once()


@pytest.mark.anyio
async def test_upload_attachment_to_card_blank_file_path_with_url_on_remote(
    mock_attachment_client,
    extract_payload,
    monkeypatch,
):
    """A blank file_path beside a real file_url is not treated as a file_path source."""
    monkeypatch.setattr(settings.mcp, "profile", "remote")

    async with _remote_attachment_session(mock_attachment_client) as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 7,
                "field_id": "f",
                "file_path": "   ",
                "file_url": "https://files.example/report.pdf",
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is True
    mock_attachment_client.upload_attachment.assert_awaited_once()


@pytest.mark.anyio
async def test_upload_attachment_to_card_download_failure_maps_to_download_step(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_attachment_client.upload_attachment = AsyncMock(
        side_effect=AttachmentUploadError(
            "file_url: must use HTTPS (got http://).",
            step="download",
        )
    )
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 7,
                "field_id": "f",
                "file_url": "http://files.example/report.pdf",
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "download"


@pytest.mark.anyio
async def test_upload_attachment_to_card_file_url_without_name_is_rejected(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    """A URL whose path has no basename and no explicit file_name is rejected."""
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 7,
                "field_id": "f",
                "file_url": "https://files.example/",
            },
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "validation"
    assert "file name" in payload["error"]["message"].lower()
    mock_attachment_client.upload_attachment.assert_not_called()


@pytest.mark.anyio
async def test_upload_attachment_to_card_file_read_error_carries_topology_hint(
    attachment_session,
    mock_attachment_client,
    extract_payload,
    tmp_path: Path,
):
    mock_attachment_client.upload_attachment = AsyncMock(
        side_effect=AttachmentUploadError(
            "File not found or not a regular file: /nope.pdf",
            step="file_read",
        )
    )
    f = tmp_path / "report.pdf"
    f.write_bytes(b"pdf-bytes")
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 7,
                "field_id": "f",
                "file_path": str(f),
            },
        )

    payload = extract_payload(result)
    assert payload["step"] == "file_read"
    message = payload["error"]["message"]
    assert "File not found" in message
    assert "machine running the MCP server" in message


# ---------------------------------------------------------------------------
# table-record twin: file_url + remote gating parity
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_upload_attachment_to_table_record_file_url_success(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    url = "https://files.example/export.csv"
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_table_record",
            {
                "organization_id": "42",
                "table_record_id": "999",
                "field_id": "tf",
                "file_url": url,
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["table_record_id"] == "999"
    attachment = mock_attachment_client.upload_attachment.await_args.args[0]
    assert attachment.url == url
    assert attachment.path is None


@pytest.mark.anyio
async def test_upload_attachment_to_table_record_rejects_file_path_on_remote(
    mock_attachment_client,
    extract_payload,
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(settings.mcp, "profile", "remote")
    f = tmp_path / "export.csv"
    f.write_bytes(b"id,name\n1,foo\n")

    async with _remote_attachment_session(mock_attachment_client) as session:
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
    assert payload["success"] is False
    assert payload["step"] == "validation"
    assert "hosted server" in payload["error"]["message"]
    mock_attachment_client.upload_attachment.assert_not_called()


# ---------------------------------------------------------------------------
# create_attachment_presigned_url (handshake)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_attachment_presigned_url_success(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_attachment_client.create_attachment_presigned_url = AsyncMock(
        return_value={
            "upload_url": "https://pipefy-uploads.s3.amazonaws.com/orgs/o/uploads/u/r.pdf?X-Amz-Expires=300",
            "storage_path": "orgs/o/uploads/u/r.pdf",
            "expires_in_seconds": 300,
        }
    )
    async with attachment_session as session:
        result = await session.call_tool(
            "create_attachment_presigned_url",
            {"organization_id": "42", "file_name": "r.pdf"},
        )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["storage_path"] == "orgs/o/uploads/u/r.pdf"
    assert payload["expires_in_seconds"] == 300
    assert payload["upload_url"].startswith("https://pipefy-uploads.s3.amazonaws.com/")
    mock_attachment_client.create_attachment_presigned_url.assert_awaited_once()


@pytest.mark.anyio
async def test_create_attachment_presigned_url_blank_file_name(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_attachment_client.create_attachment_presigned_url = AsyncMock()
    async with attachment_session as session:
        result = await session.call_tool(
            "create_attachment_presigned_url",
            {"organization_id": "42", "file_name": "   "},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "validation"
    assert "file_name" in payload["error"]["message"]
    mock_attachment_client.create_attachment_presigned_url.assert_not_awaited()


@pytest.mark.anyio
async def test_create_attachment_presigned_url_presigned_failure(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_attachment_client.create_attachment_presigned_url = AsyncMock(
        side_effect=AttachmentUploadError(
            "Pipefy did not return a presigned upload URL.",
            step="presigned_url",
        )
    )
    async with attachment_session as session:
        result = await session.call_tool(
            "create_attachment_presigned_url",
            {"organization_id": "42", "file_name": "r.pdf"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "presigned_url"
