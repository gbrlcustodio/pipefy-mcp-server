"""Unit tests for AttachmentService, HttpxS3Uploader, and the upload pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from _shared.mock_clients import mock_executor
from graphql import print_ast

from pipefy_sdk.models.attachment import (
    Attachment,
    AttachmentUploadError,
    CardTarget,
    TableRecordTarget,
)
from pipefy_sdk.queries.attachment_queries import (
    CREATE_PRESIGNED_URL_MUTATION,
)
from pipefy_sdk.services.attachment_service import (
    _ALLOWED_UPLOAD_HOST_RE,
    AttachmentService,
    HttpxS3Uploader,
    HttpxUrlDownloader,
)
from pipefy_sdk.settings import PipefySettings


def _make_service(
    *,
    presigned_payload: dict | None = None,
    s3_status: int = 200,
    s3_body_snippet: str | None = None,
    card_service: MagicMock | None = None,
    table_service: MagicMock | None = None,
    url_downloader: MagicMock | None = None,
    allow_insecure_urls: bool = False,
) -> tuple[AttachmentService, MagicMock]:
    """Build an AttachmentService with mocked collaborators.

    Wires:
    - the injected GraphQL executor to return ``presigned_payload`` if given.
    - The injected ``S3Uploader`` to return ``status_code=s3_status``.
    - ``card_service`` / ``table_service`` to ``AsyncMock`` defaults.
    """
    card = card_service or MagicMock()
    if card_service is None:
        card.update_card_field = AsyncMock(return_value={"ok": True})
    table = table_service or MagicMock()
    if table_service is None:
        table.set_table_record_field_value = AsyncMock(return_value={"ok": True})

    fake_uploader = MagicMock()
    put_result: dict = {"status_code": s3_status}
    if s3_body_snippet is not None:
        put_result["body_snippet"] = s3_body_snippet
    fake_uploader.put = AsyncMock(return_value=put_result)

    executor = mock_executor(
        presigned_payload
        if presigned_payload is not None
        else {
            "createPresignedUrl": {
                "url": "https://s3.amazonaws.com/bucket/key?sig=1",
                "downloadUrl": "https://app.pipefy.com/dl/1",
            }
        }
    )
    service = AttachmentService(
        executor=executor,
        card_service=card,
        table_service=table,
        settings=PipefySettings(allow_insecure_urls=allow_insecure_urls),
        s3_uploader=fake_uploader,
        url_downloader=url_downloader,
    )
    return service, executor


def _build_attachment(tmp_path: Path, *, name: str = "report.pdf") -> Attachment:
    f = tmp_path / name
    f.write_bytes(b"%PDF-1.4")
    return Attachment(path=f)


@pytest.mark.unit
def test_create_presigned_url_mutation_document_shape():
    doc = print_ast(CREATE_PRESIGNED_URL_MUTATION.document)
    lowered = doc.lower()
    stripped_lines = {ln.strip() for ln in doc.splitlines()}
    assert "createpresignedurl" in lowered
    assert "url" in stripped_lines
    assert "downloadUrl" in stripped_lines
    assert "clientMutationId" in stripped_lines
    assert "$organizationId" in doc
    assert "$fileName" in doc
    assert "$contentType" in doc
    assert "$contentLength" in doc


@pytest.mark.unit
def test_extract_storage_path_standard_presigned_url():
    url = (
        "https://pipefy-uploads.s3.amazonaws.com/orgs/550e8400-e29b-41d4-a716-446655440000/"
        "uploads/660e8400-e29b-41d4-a716-446655440001/report.pdf"
        "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=test"
    )
    expected = (
        "orgs/550e8400-e29b-41d4-a716-446655440000/"
        "uploads/660e8400-e29b-41d4-a716-446655440001/report.pdf"
    )
    assert AttachmentService._extract_storage_path(url) == expected


@pytest.mark.unit
def test_extract_storage_path_special_characters_in_filename():
    url = (
        "https://bucket.s3.us-east-1.amazonaws.com/orgs/u1/uploads/u2/"
        "my%20file%20%C3%A9t%C3%A9.txt?signature=abc"
    )
    assert (
        AttachmentService._extract_storage_path(url)
        == "orgs/u1/uploads/u2/my file été.txt"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_url",
    [
        "https://example.com",
        "https://example.com/",
        "https://example.com/?q=1",
    ],
)
def test_extract_storage_path_empty_path_raises(bad_url):
    with pytest.raises(ValueError, match="no object path"):
        AttachmentService._extract_storage_path(bad_url)


# HttpxS3Uploader


@pytest.mark.unit
@pytest.mark.asyncio
async def test_httpx_s3_uploader_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = ""
    mock_inner = MagicMock()
    mock_inner.put = AsyncMock(return_value=mock_response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    uploader = HttpxS3Uploader(allowed_host_pattern=_ALLOWED_UPLOAD_HOST_RE)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        result = await uploader.put(
            url="https://s3.us-east-1.amazonaws.com/presigned",
            bytes_=b"hello",
            content_type=None,
        )

    assert result == {"status_code": 200}
    mock_inner.put.assert_awaited_once()
    call_kw = mock_inner.put.call_args.kwargs
    assert call_kw["content"] == b"hello"
    assert call_kw["headers"] == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_httpx_s3_uploader_forbidden_includes_body_snippet():
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "<?xml version='1.0'?><Error><Code>AccessDenied</Code></Error>"
    mock_inner = MagicMock()
    mock_inner.put = AsyncMock(return_value=mock_response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    uploader = HttpxS3Uploader(allowed_host_pattern=_ALLOWED_UPLOAD_HOST_RE)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        result = await uploader.put(
            url="https://s3.us-east-1.amazonaws.com/presigned",
            bytes_=b"x",
            content_type=None,
        )

    assert result["status_code"] == 403
    assert "body_snippet" in result
    assert "AccessDenied" in result["body_snippet"]
    assert "presigned" not in result["body_snippet"].lower()
    assert "https://" not in result["body_snippet"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_httpx_s3_uploader_sets_content_type_header():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = ""
    mock_inner = MagicMock()
    mock_inner.put = AsyncMock(return_value=mock_response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    uploader = HttpxS3Uploader(allowed_host_pattern=_ALLOWED_UPLOAD_HOST_RE)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        await uploader.put(
            url="https://s3.us-east-1.amazonaws.com/presigned",
            bytes_=b"%PDF",
            content_type="application/pdf",
        )

    call_kw = mock_inner.put.call_args.kwargs
    assert call_kw["headers"] == {"Content-Type": "application/pdf"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_httpx_s3_uploader_rejects_non_allowed_host():
    uploader = HttpxS3Uploader(allowed_host_pattern=_ALLOWED_UPLOAD_HOST_RE)
    with pytest.raises(ValueError, match="not in the allow-list"):
        await uploader.put(
            url="https://evil.example.com/upload",
            bytes_=b"data",
            content_type=None,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_httpx_s3_uploader_accepts_pipefy_host():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = ""
    mock_inner = MagicMock()
    mock_inner.put = AsyncMock(return_value=mock_response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    uploader = HttpxS3Uploader(allowed_host_pattern=_ALLOWED_UPLOAD_HOST_RE)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        result = await uploader.put(
            url="https://uploads.pipefy.com/presigned",
            bytes_=b"ok",
            content_type=None,
        )
    assert result["status_code"] == 200


# AttachmentService.upload_attachment


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_to_card_happy_path(tmp_path):
    service, executor = _make_service()
    attachment = _build_attachment(tmp_path, name="report.pdf")
    target = CardTarget(card_id="c1", field_id="title")

    result = await service.upload_attachment(
        attachment, organization_id="org-1", target=target
    )

    assert result["file_name"] == "report.pdf"
    assert result["content_type"] == "application/pdf"
    assert result["file_size"] == 8
    assert result["field_id"] == "title"
    assert result["storage_path"] == "bucket/key"
    assert result["download_url"] == "https://app.pipefy.com/dl/1"
    executor.execute_query.assert_awaited_once()
    service._card_service.update_card_field.assert_awaited_once_with(
        "c1", "title", ["bucket/key"]
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_to_table_record_happy_path(tmp_path):
    service, _ = _make_service()
    attachment = _build_attachment(tmp_path, name="data.csv")
    target = TableRecordTarget(table_record_id="tr-9", field_id="att")

    await service.upload_attachment(attachment, organization_id="org-1", target=target)

    service._card_service.update_card_field.assert_not_called()
    service._table_service.set_table_record_field_value.assert_awaited_once_with(
        "tr-9", "att", ["bucket/key"]
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_respects_explicit_content_type(tmp_path):
    """When the attachment carries an explicit content type, it is passed to presigned."""
    service, executor = _make_service()
    file = tmp_path / "x.bin"
    file.write_bytes(b"a")
    attachment = Attachment(path=file, content_type="application/octet-stream")

    await service.upload_attachment(
        attachment,
        organization_id="org-1",
        target=CardTarget(card_id="c1", field_id="f"),
    )

    variables = executor.execute_query.call_args[0][1]
    assert variables["contentType"] == "application/octet-stream"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_file_read_error_when_path_missing(tmp_path):
    service, executor = _make_service()
    attachment = Attachment(path=tmp_path / "does-not-exist.bin")

    with pytest.raises(AttachmentUploadError) as ctx:
        await service.upload_attachment(
            attachment,
            organization_id="org-1",
            target=CardTarget(card_id="c1", field_id="f"),
        )
    assert ctx.value.step == "file_read"
    assert ctx.value.__cause__ is not None
    assert "not found" in str(ctx.value).lower()
    executor.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_file_read_cause_chain_preserved(tmp_path):
    """LocalFileError lives at ``__cause__`` so surfaces can recover the raw text."""
    from pipefy_infra.filesystem import LocalFileError

    service, _ = _make_service()
    attachment = Attachment(path=tmp_path / "missing.bin")

    with pytest.raises(AttachmentUploadError) as ctx:
        await service.upload_attachment(
            attachment,
            organization_id="org-1",
            target=CardTarget(card_id="c1", field_id="f"),
        )
    assert isinstance(ctx.value.__cause__, LocalFileError)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_oversize_file_yields_file_read_step(
    tmp_path, monkeypatch
):
    """LocalFile's cap is the single enforcement point; cap breach maps to file_read."""
    monkeypatch.setattr(
        "pipefy_sdk.services.attachment_service._MAX_ATTACHMENT_SIZE_BYTES",
        4,
    )
    service, executor = _make_service()
    big = tmp_path / "big.bin"
    big.write_bytes(b"more-than-four-bytes")
    attachment = Attachment(path=big)

    with pytest.raises(AttachmentUploadError) as ctx:
        await service.upload_attachment(
            attachment,
            organization_id="org-1",
            target=CardTarget(card_id="c1", field_id="f"),
        )
    assert ctx.value.step == "file_read"
    assert "too large" in str(ctx.value).lower()
    executor.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_presigned_failure_maps_to_presigned_step(tmp_path):
    from gql.transport.exceptions import TransportQueryError

    service, executor = _make_service()
    executor.execute_query = AsyncMock(
        side_effect=TransportQueryError("x", errors=[{"message": "denied"}])
    )
    attachment = _build_attachment(tmp_path, name="a.txt")

    with pytest.raises(AttachmentUploadError) as ctx:
        await service.upload_attachment(
            attachment,
            organization_id="org-1",
            target=CardTarget(card_id="c1", field_id="f"),
        )
    assert ctx.value.step == "presigned_url"
    assert ctx.value.__cause__ is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_missing_url_raises_presigned_step(tmp_path):
    service, _ = _make_service(
        presigned_payload={"createPresignedUrl": {"url": "", "downloadUrl": None}},
    )
    attachment = _build_attachment(tmp_path, name="a.bin")

    with pytest.raises(AttachmentUploadError) as ctx:
        await service.upload_attachment(
            attachment,
            organization_id="org-1",
            target=CardTarget(card_id="c1", field_id="f"),
        )
    assert ctx.value.step == "presigned_url"
    assert ctx.value.__cause__ is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_s3_http_error_carries_snippet_and_status(tmp_path):
    service, _ = _make_service(
        s3_status=403,
        s3_body_snippet="<Error/>",
    )
    attachment = _build_attachment(tmp_path, name="a.bin")

    with pytest.raises(AttachmentUploadError) as ctx:
        await service.upload_attachment(
            attachment,
            organization_id="org-1",
            target=CardTarget(card_id="c1", field_id="f"),
        )
    assert ctx.value.step == "s3_upload"
    assert ctx.value.body_snippet == "<Error/>"
    assert ctx.value.status_code == 403


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_s3_put_exception_tagged_s3_upload(tmp_path):
    """A raising PUT (transport error, allowlist rejection) carries the step tag."""
    service, _ = _make_service()
    service._s3_uploader.put = AsyncMock(
        side_effect=ConnectionError("connection reset by peer")
    )
    attachment = _build_attachment(tmp_path, name="a.bin")

    with pytest.raises(AttachmentUploadError) as ctx:
        await service.upload_attachment(
            attachment,
            organization_id="org-1",
            target=CardTarget(card_id="c1", field_id="f"),
        )
    assert ctx.value.step == "s3_upload"
    assert "connection reset by peer" in str(ctx.value)
    assert isinstance(ctx.value.__cause__, ConnectionError)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_extract_storage_path_failure_maps_to_s3_step(tmp_path):
    """A ValueError from path parsing is reported under ``step=s3_upload``."""
    service, _ = _make_service(
        presigned_payload={
            "createPresignedUrl": {
                "url": "https://s3.amazonaws.com/?query-only",
                "downloadUrl": None,
            }
        },
    )
    attachment = _build_attachment(tmp_path, name="a.bin")

    with pytest.raises(AttachmentUploadError) as ctx:
        await service.upload_attachment(
            attachment,
            organization_id="org-1",
            target=CardTarget(card_id="c1", field_id="f"),
        )
    assert ctx.value.step == "s3_upload"
    assert isinstance(ctx.value.__cause__, ValueError)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_field_update_failure_maps_to_field_update_step(
    tmp_path,
):
    card_service = MagicMock()
    card_service.update_card_field = AsyncMock(side_effect=RuntimeError("graphql boom"))
    service, _ = _make_service(card_service=card_service)
    attachment = _build_attachment(tmp_path, name="a.bin")

    with pytest.raises(AttachmentUploadError) as ctx:
        await service.upload_attachment(
            attachment,
            organization_id="org-1",
            target=CardTarget(card_id="c1", field_id="f"),
        )
    assert ctx.value.step == "field_update"
    assert isinstance(ctx.value.__cause__, RuntimeError)


@pytest.mark.unit
def test_attachment_service_default_uploaders_are_httpx():
    """When no uploader/downloader is passed, the httpx defaults are used."""
    service = AttachmentService(
        executor=mock_executor(),
        card_service=MagicMock(),
        table_service=MagicMock(),
        settings=PipefySettings(),
    )
    assert isinstance(service._s3_uploader, HttpxS3Uploader)
    assert isinstance(service._url_downloader, HttpxUrlDownloader)


# HttpxUrlDownloader

_GUARD = (
    "pipefy_sdk.services.attachment_service.security.validate_and_assert_public_url"
)
# The connect-time transport re-validates via the DNS gate directly; patch it
# too on any test that lets a (respx-mocked) connection through.
_DNS_GUARD = "pipefy_sdk.services.attachment_service.security.assert_hostname_resolves_to_public_ips"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_url_downloader_rejects_non_https():
    """The SSRF gate runs before any fetch: http:// is rejected (allow_insecure=False)."""
    downloader = HttpxUrlDownloader(allow_insecure=False, max_size_bytes=1024)
    with pytest.raises(ValueError, match="HTTPS"):
        await downloader.download("http://files.example/report.pdf")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_url_downloader_rejects_private_ip():
    """A literal private/internal IP is rejected before any fetch."""
    downloader = HttpxUrlDownloader(allow_insecure=False, max_size_bytes=1024)
    with pytest.raises(ValueError, match="blocked range"):
        await downloader.download("https://10.0.0.1/report.pdf")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_url_downloader_downloads_bytes():
    url = "https://files.example/report.pdf"
    with (
        patch(_GUARD, new=AsyncMock()),
        patch(_DNS_GUARD, new=AsyncMock()),
        respx.mock,
    ):
        respx.get(url).mock(return_value=httpx.Response(200, content=b"PDFBYTES"))
        downloader = HttpxUrlDownloader(allow_insecure=False, max_size_bytes=1024)
        out = await downloader.download(url)
    assert out == b"PDFBYTES"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("status", [300, 304, 204, 206, 404, 500])
async def test_url_downloader_requires_200_before_reading_body(status):
    """Only a plain 200 is read as file bytes; a non-followed 3xx (300/304), a
    bodyless 2xx (204/206), or a 4xx/5xx fails status-only with no URL echoed."""
    url = "https://files.example/report.pdf?sig=secret"
    with (
        patch(_GUARD, new=AsyncMock()),
        patch(_DNS_GUARD, new=AsyncMock()),
        respx.mock,
    ):
        respx.get(url).mock(return_value=httpx.Response(status, content=b"NOPE"))
        downloader = HttpxUrlDownloader(allow_insecure=False, max_size_bytes=1024)
        with pytest.raises(
            ValueError, match=rf"^URL download failed: HTTP {status}\.$"
        ):
            await downloader.download(url)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_url_downloader_rejects_disallowed_port():
    """A non-standard port is rejected before any network call."""
    downloader = HttpxUrlDownloader(allow_insecure=False, max_size_bytes=1024)
    with pytest.raises(ValueError, match="port 8080 is not allowed"):
        await downloader.download("https://files.example:8080/report.pdf")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_url_downloader_rejects_oversize_content_length():
    url = "https://files.example/big.bin"
    with (
        patch(_GUARD, new=AsyncMock()),
        patch(_DNS_GUARD, new=AsyncMock()),
        respx.mock,
    ):
        respx.get(url).mock(return_value=httpx.Response(200, content=b"12345"))
        downloader = HttpxUrlDownloader(allow_insecure=False, max_size_bytes=4)
        with pytest.raises(ValueError, match="Content-Length"):
            await downloader.download(url)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_url_downloader_enforces_streamed_cap():
    """The streamed byte count is capped even when no Content-Length is declared."""

    class _FakeStream:
        headers: dict[str, str] = {}

        async def aiter_bytes(self):
            yield b"12"
            yield b"345"

    downloader = HttpxUrlDownloader(allow_insecure=False, max_size_bytes=4)
    with pytest.raises(ValueError, match="download exceeded"):
        await downloader._read_capped(_FakeStream())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_url_downloader_revalidates_each_redirect_hop():
    """Every redirect target is re-validated by the SSRF gate before it is followed."""
    start = "https://files.example/start"
    guard = AsyncMock(side_effect=[None, ValueError("redirect to blocked host")])
    with (
        patch(_GUARD, new=guard),
        patch(_DNS_GUARD, new=AsyncMock()),
        respx.mock,
    ):
        respx.get(start).mock(
            return_value=httpx.Response(302, headers={"location": "https://evil/x"})
        )
        downloader = HttpxUrlDownloader(allow_insecure=False, max_size_bytes=1024)
        with pytest.raises(ValueError, match="redirect to blocked host"):
            await downloader.download(start)
    assert guard.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_url_downloader_rejects_redirect_loop():
    loop = "https://files.example/loop"
    with (
        patch(_GUARD, new=AsyncMock()),
        patch(_DNS_GUARD, new=AsyncMock()),
        respx.mock,
    ):
        respx.get(loop).mock(
            return_value=httpx.Response(302, headers={"location": loop})
        )
        downloader = HttpxUrlDownloader(allow_insecure=False, max_size_bytes=1024)
        with pytest.raises(ValueError, match="Too many redirects"):
            await downloader.download(loop)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ssrf_safe_transport_blocks_internal_host_at_connect():
    """The transport re-validates the resolved host (DNS-rebinding defense)."""
    from pipefy_sdk.services.attachment_service import _SSRFSafeAsyncTransport

    transport = _SSRFSafeAsyncTransport()
    request = httpx.Request("GET", "http://127.0.0.1/x")
    with pytest.raises(ValueError, match="blocked"):
        await transport.handle_async_request(request)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ssrf_safe_transport_rejects_disallowed_port():
    """The transport rejects a non-standard port before connecting."""
    from pipefy_sdk.services.attachment_service import _SSRFSafeAsyncTransport

    transport = _SSRFSafeAsyncTransport()
    request = httpx.Request("GET", "https://example.com:8080/x")
    with pytest.raises(ValueError, match="port 8080 is not allowed"):
        await transport.handle_async_request(request)


# Service via the file_url source


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_via_url_uses_downloader():
    fake_downloader = MagicMock()
    fake_downloader.download = AsyncMock(return_value=b"PDFBYTES")
    service, _ = _make_service(url_downloader=fake_downloader)

    result = await service.upload_attachment(
        Attachment(url="https://files.example/report.pdf"),
        organization_id="org-1",
        target=CardTarget(card_id="c1", field_id="f"),
    )

    fake_downloader.download.assert_awaited_once_with(
        "https://files.example/report.pdf"
    )
    assert result["file_name"] == "report.pdf"
    assert result["file_size"] == len(b"PDFBYTES")
    assert result["storage_path"] == "bucket/key"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_attachment_url_download_failure_maps_to_download_step():
    fake_downloader = MagicMock()
    fake_downloader.download = AsyncMock(side_effect=ValueError("blocked host"))
    service, _ = _make_service(url_downloader=fake_downloader)

    with pytest.raises(AttachmentUploadError) as ctx:
        await service.upload_attachment(
            Attachment(url="https://files.example/report.pdf"),
            organization_id="org-1",
            target=CardTarget(card_id="c1", field_id="f"),
        )
    assert ctx.value.step == "download"
    assert isinstance(ctx.value.__cause__, ValueError)
