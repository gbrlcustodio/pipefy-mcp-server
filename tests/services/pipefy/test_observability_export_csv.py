"""Unit tests for observability export CSV helpers."""

import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from openpyxl import Workbook

from pipefy_mcp.services.pipefy.observability_export_csv import (
    download_bytes,
    is_allowed_pipefy_export_download_url,
    xlsx_first_sheet_to_csv_limited,
)


@pytest.fixture(autouse=True)
def _skip_real_dns_for_download_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid real DNS in download_bytes tests; url_ssrf is covered separately."""

    async def _ok(_hostname: str) -> None:
        return None

    monkeypatch.setattr(
        "pipefy_mcp.services.pipefy.observability_export_csv.assert_hostname_resolves_to_public_ips",
        _ok,
    )


def _minimal_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Jobs"
    ws.append(["col_a", "col_b"])
    ws.append([1, 2])
    ws.append(["x", "y"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.unit
def test_is_allowed_pipefy_https_storage_url():
    url = "https://app.pipefy.com/storage/v1/signed/foo.xlsx?sig=1"
    assert is_allowed_pipefy_export_download_url(url) is True


@pytest.mark.unit
def test_is_allowed_rejects_http():
    assert is_allowed_pipefy_export_download_url("http://app.pipefy.com/x") is False


@pytest.mark.unit
def test_is_allowed_rejects_non_pipefy_host():
    assert is_allowed_pipefy_export_download_url("https://evil.com/x") is False


@pytest.mark.unit
def test_xlsx_first_sheet_to_csv():
    data = _minimal_xlsx_bytes()
    csv_text, rows, title, truncated = xlsx_first_sheet_to_csv_limited(
        data, max_output_chars=10_000
    )
    assert title == "Jobs"
    assert truncated is False
    assert rows == 3
    assert "col_a,col_b" in csv_text
    assert "1,2" in csv_text


@pytest.mark.unit
def test_xlsx_csv_truncated_by_char_cap():
    data = _minimal_xlsx_bytes()
    csv_text, rows, _title, truncated = xlsx_first_sheet_to_csv_limited(
        data, max_output_chars=5
    )
    assert truncated is True
    assert rows < 3
    assert "truncated" in csv_text.lower()


@pytest.mark.unit
def test_xlsx_first_sheet_rejects_zero_max_chars():
    with pytest.raises(ValueError, match="at least 1"):
        xlsx_first_sheet_to_csv_limited(b"", max_output_chars=0)


# --- download_bytes tests (lines 93-123) ---


@pytest.mark.asyncio
async def test_download_bytes_rejects_http_scheme():
    with pytest.raises(ValueError, match="not an allowed Pipefy https URL"):
        await download_bytes("http://app.pipefy.com/export.xlsx", max_bytes=1024)


@pytest.mark.asyncio
async def test_download_bytes_rejects_non_pipefy_domain():
    with pytest.raises(ValueError, match="not an allowed Pipefy https URL"):
        await download_bytes("https://evil.com/export.xlsx", max_bytes=1024)


@pytest.mark.asyncio
async def test_download_bytes_rejects_content_length_exceeding_max():
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {"content-length": "5000"}
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "pipefy_mcp.services.pipefy.observability_export_csv.httpx.AsyncClient",
        return_value=mock_client,
    ):
        with pytest.raises(ValueError, match="exceeds max_download_bytes"):
            await download_bytes("https://app.pipefy.com/export.xlsx", max_bytes=1024)


@pytest.mark.asyncio
async def test_download_bytes_rejects_streaming_body_exceeding_max():
    async def fake_aiter_bytes():
        yield b"a" * 600
        yield b"b" * 600

    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {}
    mock_response.aiter_bytes = fake_aiter_bytes
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "pipefy_mcp.services.pipefy.observability_export_csv.httpx.AsyncClient",
        return_value=mock_client,
    ):
        with pytest.raises(ValueError, match="exceeds max_download_bytes"):
            await download_bytes("https://app.pipefy.com/export.xlsx", max_bytes=1000)


def _mock_stream_client_for_redirect(
    *,
    status_code: int,
    location: str | None,
    final_body: bytes | None = None,
) -> MagicMock:
    """Build AsyncClient mock: first response may be redirect; then optional 200 body."""

    call_count = {"n": 0}

    def make_stream(*_args: Any, **_kwargs: Any) -> AsyncMock:
        mock_response = AsyncMock()
        n = call_count["n"]
        call_count["n"] = n + 1

        if n == 0 and status_code in (301, 302, 303, 307, 308):
            mock_response.status_code = status_code
            mock_response.headers = {"location": location or ""}
            mock_response.raise_for_status = MagicMock()
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=False)
            return mock_response

        mock_response.status_code = 200
        mock_response.headers = (
            {"content-length": str(len(final_body))}
            if final_body is not None
            else {}
        )
        mock_response.raise_for_status = MagicMock()

        async def aiter() -> Any:
            if final_body:
                yield final_body

        mock_response.aiter_bytes = aiter
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        return mock_response

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(side_effect=make_stream)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.mark.asyncio
async def test_download_bytes_rejects_redirect_to_localhost():
    mock_client = _mock_stream_client_for_redirect(
        status_code=302,
        location="http://127.0.0.1/internal",
    )
    with patch(
        "pipefy_mcp.services.pipefy.observability_export_csv.httpx.AsyncClient",
        return_value=mock_client,
    ):
        with pytest.raises(ValueError, match="not an allowed Pipefy https URL"):
            await download_bytes("https://app.pipefy.com/export.xlsx", max_bytes=1024)


@pytest.mark.asyncio
async def test_download_bytes_rejects_redirect_to_imds():
    mock_client = _mock_stream_client_for_redirect(
        status_code=302,
        location="http://169.254.169.254/latest/meta-data/",
    )
    with patch(
        "pipefy_mcp.services.pipefy.observability_export_csv.httpx.AsyncClient",
        return_value=mock_client,
    ):
        with pytest.raises(ValueError, match="not an allowed Pipefy https URL"):
            await download_bytes("https://app.pipefy.com/export.xlsx", max_bytes=1024)


@pytest.mark.asyncio
async def test_download_bytes_follows_safe_relative_redirect():
    body = b"xlsx-bytes"
    mock_client = _mock_stream_client_for_redirect(
        status_code=302,
        location="/other/export.xlsx",
        final_body=body,
    )

    with patch(
        "pipefy_mcp.services.pipefy.observability_export_csv.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await download_bytes("https://app.pipefy.com/a.xlsx", max_bytes=1024)
    assert result == body
    assert mock_client.stream.call_count == 2


@pytest.mark.asyncio
async def test_download_bytes_propagates_httpx_errors():
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("GET", "https://app.pipefy.com/x"),
            response=httpx.Response(500),
        )
    )
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "pipefy_mcp.services.pipefy.observability_export_csv.httpx.AsyncClient",
        return_value=mock_client,
    ):
        with pytest.raises(httpx.HTTPStatusError):
            await download_bytes("https://app.pipefy.com/export.xlsx", max_bytes=1024)
