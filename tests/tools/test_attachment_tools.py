"""Tests for attachment MCP tools (mocked PipefyClient)."""

import base64
import socket
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.attachment_tools import (
    AttachmentTools,
    _download_file_bytes,
    _validate_url_safe,
)

PRESIGNED_PUT_URL = (
    "https://s3.example.com/orgs/o/u/f/report.pdf"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=abc"
)

# Patch target for SSRF validation (bypassed in tool-level tests that use mocked httpx)
_VALIDATE_PATCH = "pipefy_mcp.tools.attachment_tools._validate_url_safe"


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


def _httpx_stream_cm_mock(content=b"hello-bytes", headers=None):
    """Build a mock that mimics httpx streaming (AsyncClient → stream → aiter_bytes)."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = headers or {}

    async def _aiter_bytes():
        yield content

    mock_response.aiter_bytes = _aiter_bytes

    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    stream_cm.__aexit__ = AsyncMock(return_value=False)

    mock_inner = MagicMock()
    mock_inner.stream = MagicMock(return_value=stream_cm)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


# ---------------------------------------------------------------------------
# _validate_url_safe unit tests (RF-01: SSRF protection)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestValidateUrlSafe:
    async def test_rejects_file_scheme(self):
        with pytest.raises(ValueError, match="Only http and https"):
            await _validate_url_safe("file:///etc/passwd")

    async def test_rejects_ftp_scheme(self):
        with pytest.raises(ValueError, match="Only http and https"):
            await _validate_url_safe("ftp://internal/data")

    async def test_rejects_no_hostname(self):
        with pytest.raises(ValueError, match="no hostname"):
            await _validate_url_safe("https://")

    @patch("pipefy_mcp.tools.attachment_tools.socket.getaddrinfo")
    async def test_rejects_localhost(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(None, None, None, None, ("127.0.0.1", 0))]
        with pytest.raises(ValueError, match="private/internal"):
            await _validate_url_safe("https://localhost/secret")

    @patch("pipefy_mcp.tools.attachment_tools.socket.getaddrinfo")
    async def test_rejects_metadata_endpoint(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (None, None, None, None, ("169.254.169.254", 0))
        ]
        with pytest.raises(ValueError, match="private/internal"):
            await _validate_url_safe("http://169.254.169.254/latest/meta-data/")

    @patch("pipefy_mcp.tools.attachment_tools.socket.getaddrinfo")
    async def test_rejects_private_10_range(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(None, None, None, None, ("10.0.0.1", 0))]
        with pytest.raises(ValueError, match="private/internal"):
            await _validate_url_safe("https://internal.corp/file.pdf")

    @patch("pipefy_mcp.tools.attachment_tools.socket.getaddrinfo")
    async def test_rejects_private_172_range(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(None, None, None, None, ("172.16.0.1", 0))]
        with pytest.raises(ValueError, match="private/internal"):
            await _validate_url_safe("https://internal.corp/file.pdf")

    @patch("pipefy_mcp.tools.attachment_tools.socket.getaddrinfo")
    async def test_rejects_private_192_range(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(None, None, None, None, ("192.168.1.1", 0))]
        with pytest.raises(ValueError, match="private/internal"):
            await _validate_url_safe("https://home.lan/file.pdf")

    @patch("pipefy_mcp.tools.attachment_tools.socket.getaddrinfo")
    async def test_rejects_ipv6_loopback(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(None, None, None, None, ("::1", 0, 0, 0))]
        with pytest.raises(ValueError, match="private/internal"):
            await _validate_url_safe("https://[::1]/file.pdf")

    @patch("pipefy_mcp.tools.attachment_tools.socket.getaddrinfo")
    async def test_accepts_public_ip(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(None, None, None, None, ("93.184.216.34", 0))]
        await _validate_url_safe("https://example.com/file.pdf")  # should not raise

    @patch("pipefy_mcp.tools.attachment_tools.socket.getaddrinfo")
    async def test_rejects_unresolvable_hostname(self, mock_getaddrinfo):
        mock_getaddrinfo.side_effect = socket.gaierror("DNS resolution failed")
        with pytest.raises(ValueError, match="Could not resolve hostname"):
            await _validate_url_safe("https://nope.invalid/file.pdf")


# ---------------------------------------------------------------------------
# _download_file_bytes redirect + streaming-size protections
# ---------------------------------------------------------------------------


def _httpx_multi_response_cm_mock(*responses):
    """Build an AsyncClient mock whose .stream() yields the supplied responses in order."""
    mock_inner = MagicMock()
    iter_ = iter(responses)

    def _next_stream(*_args, **_kwargs):
        resp = next(iter_)
        stream_cm = MagicMock()
        stream_cm.__aenter__ = AsyncMock(return_value=resp)
        stream_cm.__aexit__ = AsyncMock(return_value=False)
        return stream_cm

    mock_inner.stream = MagicMock(side_effect=_next_stream)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


def _make_response(*, status_code=200, headers=None, body=b"hello"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()

    async def _aiter():
        yield body

    resp.aiter_bytes = _aiter
    return resp


@pytest.mark.anyio
async def test_download_rejects_redirect_without_location_header():
    """A 302 without a Location header is treated as unsafe."""
    resp = _make_response(status_code=302, headers={})
    mock_cm = _httpx_multi_response_cm_mock(resp)
    with (
        patch(
            "pipefy_mcp.tools.attachment_tools.httpx.AsyncClient", return_value=mock_cm
        ),
        patch(_VALIDATE_PATCH),
    ):
        with pytest.raises(ValueError, match="Redirect without Location header"):
            await _download_file_bytes("https://example.com/a")


@pytest.mark.anyio
async def test_download_follows_safe_redirect_chain():
    """Redirects are followed up to the limit and intermediate hops are SSRF-validated."""
    r1 = _make_response(status_code=301, headers={"location": "https://example.com/b"})
    r2 = _make_response(status_code=200, headers={}, body=b"final-bytes")
    mock_cm = _httpx_multi_response_cm_mock(r1, r2)
    with (
        patch(
            "pipefy_mcp.tools.attachment_tools.httpx.AsyncClient", return_value=mock_cm
        ),
        patch(_VALIDATE_PATCH) as mock_validate,
    ):
        result = await _download_file_bytes("https://example.com/a")
    assert result == b"final-bytes"
    # Both the initial URL and the redirect target must go through _validate_url_safe.
    assert mock_validate.await_count == 2


@pytest.mark.anyio
async def test_download_rejects_too_many_redirects():
    """Redirect loop / chain longer than _MAX_REDIRECTS is rejected."""
    # 5 redirects, all pointing forward — exceeds _MAX_REDIRECTS = 3.
    redirects = [
        _make_response(
            status_code=302, headers={"location": f"https://example.com/hop{i}"}
        )
        for i in range(5)
    ]
    mock_cm = _httpx_multi_response_cm_mock(*redirects)
    with (
        patch(
            "pipefy_mcp.tools.attachment_tools.httpx.AsyncClient", return_value=mock_cm
        ),
        patch(_VALIDATE_PATCH),
    ):
        with pytest.raises(ValueError, match="Too many redirects"):
            await _download_file_bytes("https://example.com/a")


@pytest.mark.anyio
async def test_download_rejects_streaming_body_exceeding_size_limit():
    """Body size is enforced during streaming even when Content-Length is absent."""
    large_chunk = b"x" * (101 * 1024 * 1024)  # 101 MiB > 100 MiB limit

    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}  # no Content-Length → must rely on streaming accumulator
    resp.raise_for_status = MagicMock()

    async def _aiter():
        yield large_chunk

    resp.aiter_bytes = _aiter
    mock_cm = _httpx_multi_response_cm_mock(resp)
    with (
        patch(
            "pipefy_mcp.tools.attachment_tools.httpx.AsyncClient", return_value=mock_cm
        ),
        patch(_VALIDATE_PATCH),
    ):
        with pytest.raises(ValueError, match="File too large"):
            await _download_file_bytes("https://example.com/huge.bin")


@pytest.mark.anyio
async def test_upload_attachment_to_card_file_url_success(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    mock_cm = _httpx_stream_cm_mock()
    with (
        patch(
            "pipefy_mcp.tools.attachment_tools.httpx.AsyncClient", return_value=mock_cm
        ),
        patch(_VALIDATE_PATCH),
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
    assert payload["card_id"] == "7"
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
        "7",
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
    mock_cm = _httpx_stream_cm_mock(b"tbl")
    with (
        patch(
            "pipefy_mcp.tools.attachment_tools.httpx.AsyncClient", return_value=mock_cm
        ),
        patch(_VALIDATE_PATCH),
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


# ---------------------------------------------------------------------------
# RF-01: SSRF rejection at tool level
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_upload_attachment_to_card_rejects_ssrf_url(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    """Private IP URL should fail at file_download step, never reaching presigned URL."""
    with patch(
        "pipefy_mcp.tools.attachment_tools.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("169.254.169.254", 0))],
    ):
        async with attachment_session as session:
            result = await session.call_tool(
                "upload_attachment_to_card",
                {
                    "organization_id": "42",
                    "card_id": 1,
                    "field_id": "f",
                    "file_name": "secret.txt",
                    "file_url": "http://169.254.169.254/latest/meta-data/",
                },
            )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "file_download"
    assert (
        "private" in payload["error"].lower() or "internal" in payload["error"].lower()
    )
    mock_attachment_client.create_presigned_url.assert_not_called()


@pytest.mark.anyio
async def test_upload_attachment_to_card_rejects_file_scheme(
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
                "file_name": "passwd.txt",
                "file_url": "file:///etc/passwd",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "file_download"
    assert "http" in payload["error"].lower()
    mock_attachment_client.create_presigned_url.assert_not_called()


# ---------------------------------------------------------------------------
# RF-02: File size limit
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_upload_attachment_to_card_rejects_oversized_content_length(
    attachment_session,
    mock_attachment_client,
    extract_payload,
):
    """Content-Length header exceeding limit should fail before downloading body."""
    oversized = str(200 * 1024 * 1024)  # 200 MiB
    mock_cm = _httpx_stream_cm_mock(
        content=b"small",
        headers={"content-length": oversized},
    )
    with (
        patch(
            "pipefy_mcp.tools.attachment_tools.httpx.AsyncClient", return_value=mock_cm
        ),
        patch(_VALIDATE_PATCH),
    ):
        async with attachment_session as session:
            result = await session.call_tool(
                "upload_attachment_to_card",
                {
                    "organization_id": "42",
                    "card_id": 1,
                    "field_id": "f",
                    "file_name": "huge.bin",
                    "file_url": "https://files.example.com/huge.bin",
                },
            )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["step"] == "file_download"
    assert (
        "too large" in payload["error"].lower() or "limit" in payload["error"].lower()
    )
    mock_attachment_client.create_presigned_url.assert_not_called()


## ---------------------------------------------------------------------------
## PipefyId coercion: int → str through MCP transport (mcporter mitigation)
## ---------------------------------------------------------------------------


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
    mock_attachment_client.create_presigned_url.assert_awaited_once_with(
        "42", "note.txt", "text/plain", 5
    )
    mock_attachment_client.update_card_field.assert_awaited_once_with(
        "7", "999", ["orgs/o/u/f/report.pdf"]
    )


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
    mock_attachment_client.create_presigned_url.assert_awaited_once_with(
        "42", "data.csv", "text/csv", 5
    )
    mock_attachment_client.set_table_record_field_value.assert_awaited_once_with(
        "200", "300", ["orgs/o/u/f/report.pdf"]
    )
