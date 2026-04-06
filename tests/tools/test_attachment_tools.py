"""Tests for attachment MCP tools (mocked PipefyClient)."""

import base64
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.attachment_tools import AttachmentTools

PRESIGNED_PUT_URL = (
    "https://s3.example.com/orgs/o/u/f/report.pdf"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=abc"
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_attachment_client():
    client = MagicMock(PipefyClient)
    client.create_presigned_url = AsyncMock(
        return_value={
            "url": PRESIGNED_PUT_URL,
            "download_url": "https://app.pipefy.com/storage/v1/signed/z",
        }
    )
    client.upload_file_to_s3 = AsyncMock(return_value={"status_code": 200})
    client.extract_storage_path = MagicMock(return_value="orgs/o/u/f/report.pdf")
    client.update_card_field = AsyncMock(return_value={"ok": True})
    client.set_table_record_field_value = AsyncMock(return_value={"ok": True})
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


def _httpx_download_cm_mock(content=b"hello-bytes"):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content = content
    mock_inner = MagicMock()
    mock_inner.get = AsyncMock(return_value=mock_response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


@pytest.mark.anyio
async def test_upload_attachment_to_card_file_url_success(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_cm = _httpx_download_cm_mock()
    with patch(
        "pipefy_mcp.tools.attachment_tools.httpx.AsyncClient", return_value=mock_cm
    ):
        async with attachment_session as session:
            result = await session.call_tool(
                "upload_attachment_to_card",
                {
                    "organization_id": "42",
                    "card_id": 7,
                    "field_id": "field-uuid",
                    "file_name": "report.pdf",
                    "file_url": "https://files.example.com/report.pdf",
                },
            )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["card_id"] == 7
    assert payload["field_id"] == "field-uuid"
    assert payload["file_name"] == "report.pdf"
    assert payload["content_type"] == "application/pdf"
    assert payload["file_size"] == len(b"hello-bytes")
    assert "download_url" in payload

    mock_attachment_client.create_presigned_url.assert_awaited_once_with(
        "42",
        "report.pdf",
        "application/pdf",
        len(b"hello-bytes"),
    )
    mock_attachment_client.upload_file_to_s3.assert_awaited_once()
    mock_attachment_client.update_card_field.assert_awaited_once_with(
        7,
        "field-uuid",
        ["orgs/o/u/f/report.pdf"],
    )


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
    mock_attachment_client.create_presigned_url.assert_awaited_once_with(
        "42",
        "note.txt",
        "text/plain",
        5,
    )


@pytest.mark.anyio
async def test_upload_attachment_to_card_presigned_url_missing(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_attachment_client.create_presigned_url = AsyncMock(
        return_value={"url": None, "download_url": None}
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
    mock_attachment_client.upload_file_to_s3.assert_not_called()


@pytest.mark.anyio
async def test_upload_attachment_to_card_presigned_graphql_error(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_attachment_client.create_presigned_url = AsyncMock(
        side_effect=TransportQueryError("x", errors=[{"message": "org denied"}])
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
    assert "denied" in payload["error"]


@pytest.mark.anyio
async def test_upload_attachment_to_card_s3_failure(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_attachment_client.upload_file_to_s3 = AsyncMock(
        return_value={"status_code": 403, "body_snippet": "<Error/>"}
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
    mock_attachment_client.update_card_field.assert_not_called()


@pytest.mark.anyio
async def test_upload_attachment_to_card_field_update_failure(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_attachment_client.update_card_field = AsyncMock(
        side_effect=TransportQueryError(
            "x", errors=[{"message": "field must be attachment"}]
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
    assert payload["step"] == "field_update"
    assert "attachment" in payload["error"]


@pytest.mark.anyio
async def test_upload_attachment_to_card_validation_both_sources(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    async with attachment_session as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": "42",
                "card_id": 1,
                "field_id": "f",
                "file_name": "a.bin",
                "file_url": "https://x",
                "file_content_base64": base64.b64encode(b"x").decode("ascii"),
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "validation"
    mock_attachment_client.create_presigned_url.assert_not_called()


@pytest.mark.anyio
async def test_upload_attachment_to_table_record_file_url_success(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_cm = _httpx_download_cm_mock(b"tbl")
    with patch(
        "pipefy_mcp.tools.attachment_tools.httpx.AsyncClient", return_value=mock_cm
    ):
        async with attachment_session as session:
            result = await session.call_tool(
                "upload_attachment_to_table_record",
                {
                    "organization_id": "42",
                    "table_record_id": "999",
                    "field_id": "tf",
                    "file_name": "data.csv",
                    "file_url": "https://files.example.com/data.csv",
                },
            )

    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["table_record_id"] == "999"
    assert payload["content_type"] == "text/csv"
    mock_attachment_client.set_table_record_field_value.assert_awaited_once_with(
        "999",
        "tf",
        ["orgs/o/u/f/report.pdf"],
    )


@pytest.mark.anyio
async def test_upload_attachment_to_table_record_base64_and_presigned_error(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_attachment_client.create_presigned_url = AsyncMock(
        return_value={"url": "", "download_url": None}
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
    mock_attachment_client.upload_file_to_s3 = AsyncMock(
        return_value={"status_code": 500}
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
    mock_attachment_client.set_table_record_field_value = AsyncMock(
        side_effect=TransportQueryError("e", errors=[{"message": "invalid field"}])
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
