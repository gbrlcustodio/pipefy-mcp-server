"""Attachment uploads: read/download source, presigned URL, S3 PUT, field update."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Protocol, assert_never
from urllib.parse import unquote, urljoin, urlparse

import httpx
from httpx import Timeout
from pipefy_infra import security
from pipefy_infra.coerce import optional_int
from pipefy_infra.filesystem import LocalFile, LocalFileError

from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.models.attachment import (
    _MAX_ATTACHMENT_SIZE_BYTES,
    Attachment,
    AttachmentTarget,
    AttachmentUploadError,
    AttachmentUploadResult,
    CardTarget,
    TableRecordTarget,
)
from pipefy_sdk.queries.attachment_queries import (
    CREATE_PRESIGNED_URL_MUTATION,
)
from pipefy_sdk.services.card_service import CardService
from pipefy_sdk.services.table_service import TableService
from pipefy_sdk.settings import PipefySettings

_BODY_SNIPPET_MAX_CHARS = 500
_ALLOWED_UPLOAD_HOST_RE = re.compile(
    r"^[\w.-]+\.(amazonaws\.com|pipefy\.com)$", re.IGNORECASE
)
_DOWNLOAD_TIMEOUT_SECONDS = 60.0
_MAX_REDIRECTS = 3
_REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})
# Standard HTTP(S) ports only: a public host can still front an internal service
# on an odd port, so restrict the fetch to where files are actually served.
_ALLOWED_PORTS = frozenset({None, 80, 443})


def _assert_port_allowed(url: str) -> None:
    """Reject a URL whose port is not a standard HTTP(S) port."""
    port = urlparse(url).port
    if port not in _ALLOWED_PORTS:
        raise ValueError(f"file_url: port {port} is not allowed (only 80 and 443).")


class _SSRFSafeAsyncTransport(httpx.AsyncHTTPTransport):
    """Re-validate the destination at the moment httpx opens the connection.

    The pre-flight and per-redirect checks resolve the hostname, but httpx
    resolves again when it connects; a DNS-rebinding record (public on the
    check, internal on the connect) could differ between the two. Re-running
    the port and public-IP checks here — on every request the client issues,
    immediately before the socket — closes that window. Mirrors the transport
    guard used by the sibling web-scraping/MCP egress path.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        _assert_port_allowed(str(request.url))
        await security.assert_hostname_resolves_to_public_ips(request.url.host or "")
        return await super().handle_async_request(request)


class S3Uploader(Protocol):
    """PUTs file bytes to a presigned URL and returns the HTTP outcome.

    Implementations enforce whatever host policy they need; the service only
    cares about ``status_code`` and the optional ``body_snippet`` on failure.
    """

    async def put(
        self,
        *,
        url: str,
        bytes_: bytes,
        content_type: str | None,
    ) -> dict[str, Any]: ...


class HttpxS3Uploader:
    """Default :class:`S3Uploader` backed by ``httpx.AsyncClient``.

    Enforces a host allow-list before issuing the PUT so that a tampered
    presigned URL cannot send file bytes to an arbitrary host.
    """

    def __init__(
        self,
        *,
        allowed_host_pattern: re.Pattern[str],
        timeout_seconds: int = 60,
    ) -> None:
        self._allowed_host_pattern = allowed_host_pattern
        self._timeout_seconds = timeout_seconds

    async def put(
        self,
        *,
        url: str,
        bytes_: bytes,
        content_type: str | None,
    ) -> dict[str, Any]:
        host = urlparse(url).hostname or ""
        if not self._allowed_host_pattern.match(host):
            raise ValueError(
                f"Upload URL host '{host}' is not in the allow-list "
                "(*.amazonaws.com, *.pipefy.com)."
            )
        headers: dict[str, str] = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        async with httpx.AsyncClient(
            timeout=Timeout(timeout=self._timeout_seconds),
        ) as client:
            response = await client.put(url, content=bytes_, headers=headers)
        result: dict[str, Any] = {"status_code": response.status_code}
        if response.status_code >= 400:
            result["body_snippet"] = response.text[:_BODY_SNIPPET_MAX_CHARS]
        return result


class UrlDownloader(Protocol):
    """Fetches file bytes from a client-supplied URL.

    Implementations own their own SSRF policy and size cap; the service only
    hands over the URL and receives the bytes (or a raised error).
    """

    async def download(self, url: str) -> bytes: ...


class HttpxUrlDownloader:
    """Default :class:`UrlDownloader` backed by ``httpx.AsyncClient``.

    Guards a server-side fetch of an untrusted URL across four layers:

    - scheme + DNS-resolved public-IP check (:mod:`pipefy_infra.security`),
    - a standard-port allow-list (80/443), so a public host cannot front an
      internal service on an odd port,
    - the same checks re-run at connect time via :class:`_SSRFSafeAsyncTransport`
      (DNS-rebinding defense) on every request, including redirects, which are
      followed manually so an intermediate URL cannot bypass the gate,
    - a size cap on both the ``Content-Length`` header and the streamed bytes.

    ``allow_insecure`` comes from ``PipefySettings.allow_insecure_urls``, a
    per-deployment flag: HTTPS-only in production, ``http`` permitted only when
    a deployment opts in (internal IPs stay blocked by the DNS gate regardless).
    """

    def __init__(
        self,
        *,
        allow_insecure: bool,
        max_size_bytes: int,
        timeout_seconds: float = _DOWNLOAD_TIMEOUT_SECONDS,
        max_redirects: int = _MAX_REDIRECTS,
    ) -> None:
        self._allow_insecure = allow_insecure
        self._max_size_bytes = max_size_bytes
        self._timeout_seconds = timeout_seconds
        self._max_redirects = max_redirects

    async def download(self, url: str) -> bytes:
        await self._validate_fetch_target(url)
        current_url = url
        async with httpx.AsyncClient(transport=_SSRFSafeAsyncTransport()) as client:
            for _ in range(self._max_redirects + 1):
                async with client.stream(
                    "GET",
                    current_url,
                    follow_redirects=False,
                    timeout=Timeout(timeout=self._timeout_seconds),
                ) as response:
                    if response.status_code in _REDIRECT_STATUS:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("Redirect without a Location header.")
                        current_url = urljoin(current_url, location.strip())
                        await self._validate_fetch_target(current_url)
                        continue
                    if response.status_code != 200:
                        # Only a plain 200 carries a body to treat as the file:
                        # an unfollowed 3xx (300/304), a bodyless 2xx (204/206),
                        # or a 4xx/5xx must not upload as file bytes.
                        # Status only — never echo the (possibly signed) source URL.
                        raise ValueError(
                            f"URL download failed: HTTP {response.status_code}."
                        )
                    return await self._read_capped(response)
        raise ValueError(f"Too many redirects (max {self._max_redirects}).")

    async def _validate_fetch_target(self, url: str) -> None:
        """Scheme + port + public-IP checks for a URL before it is fetched."""
        _assert_port_allowed(url)
        await security.validate_and_assert_public_url(
            url, field_label="file_url", allow_insecure=self._allow_insecure
        )

    async def _read_capped(self, response: httpx.Response) -> bytes:
        cap_mib = self._max_size_bytes // (1024 * 1024)
        # A malformed Content-Length coerces to None and falls through to the
        # streamed byte-count cap below, rather than raising a cryptic int() error.
        declared = optional_int(response.headers.get("content-length"))
        if declared is not None and declared > self._max_size_bytes:
            raise ValueError(
                f"File too large: Content-Length {declared} bytes exceeds "
                f"the {cap_mib} MiB limit."
            )
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > self._max_size_bytes:
                raise ValueError(
                    f"File too large: download exceeded the {cap_mib} MiB limit."
                )
            chunks.append(chunk)
        return b"".join(chunks)


class AttachmentService:
    """Run the full attachment upload pipeline.

    The pipeline resolves the source bytes (reading a local file, or
    downloading a URL through the injected :class:`UrlDownloader`, both
    enforcing the size cap), requests a presigned URL from Pipefy, PUTs the
    bytes through an injected :class:`S3Uploader`, parses the storage path,
    and updates the destination field on either a card or a table record.

    Failures across every step surface as :class:`AttachmentUploadError`
    carrying ``step`` so surfaces can map to step-aware envelopes.
    """

    def __init__(
        self,
        *,
        executor: GraphQLExecutor,
        card_service: CardService,
        table_service: TableService,
        settings: PipefySettings,
        s3_uploader: S3Uploader | None = None,
        url_downloader: UrlDownloader | None = None,
    ) -> None:
        self._executor = executor
        self._card_service = card_service
        self._table_service = table_service
        self._s3_uploader: S3Uploader = s3_uploader or HttpxS3Uploader(
            allowed_host_pattern=_ALLOWED_UPLOAD_HOST_RE
        )
        # allow_insecure comes from the deployment's settings, mirroring the
        # webhook service; a hosted deployment leaves it False (HTTPS + public
        # hosts only).
        self._url_downloader: UrlDownloader = url_downloader or HttpxUrlDownloader(
            allow_insecure=settings.allow_insecure_urls,
            max_size_bytes=_MAX_ATTACHMENT_SIZE_BYTES,
        )

    async def upload_attachment(
        self,
        attachment: Attachment,
        *,
        organization_id: str,
        target: AttachmentTarget,
    ) -> AttachmentUploadResult:
        """Upload ``attachment`` to ``target`` via the standard pipeline.

        Raises:
            AttachmentUploadError: On any pipeline failure (``step`` identifies
                which stage).
        """
        file_bytes = await self._resolve_source_bytes(attachment)

        effective_type = attachment.content_type
        file_name = attachment.name
        content_length = len(file_bytes)

        try:
            presigned = await self._create_presigned_url(
                organization_id,
                file_name,
                effective_type,
                content_length,
            )
        except Exception as exc:
            raise AttachmentUploadError(
                f"Presigned URL request failed: {exc}",
                step="presigned_url",
            ) from exc

        upload_url = presigned.get("url")
        download_url = presigned.get("download_url")
        if not isinstance(upload_url, str) or not upload_url.strip():
            raise AttachmentUploadError(
                "Pipefy did not return a presigned upload URL. "
                "Check organization_id and file_name, then retry.",
                step="presigned_url",
            )
        upload_url = upload_url.strip()

        try:
            put_result = await self._s3_uploader.put(
                url=upload_url,
                bytes_=file_bytes,
                content_type=effective_type,
            )
        except Exception as exc:
            # Transport errors and the uploader's host-allowlist rejection are
            # s3_upload-stage failures; tag them so the step contract holds.
            raise AttachmentUploadError(
                f"S3 upload failed: {exc}", step="s3_upload"
            ) from exc
        status = put_result.get("status_code", 0)
        if not isinstance(status, int) or status >= 400:
            body_snippet = put_result.get("body_snippet")
            raise AttachmentUploadError(
                f"S3 upload failed with HTTP {status}.",
                step="s3_upload",
                body_snippet=body_snippet if isinstance(body_snippet, str) else None,
                status_code=status if isinstance(status, int) else None,
            )

        try:
            storage_path = self._extract_storage_path(upload_url)
        except ValueError as exc:
            raise AttachmentUploadError(str(exc), step="s3_upload") from exc

        try:
            match target:
                case CardTarget(card_id=card_id, field_id=field_id):
                    await self._card_service.update_card_field(
                        card_id, field_id, [storage_path]
                    )
                case TableRecordTarget(
                    table_record_id=table_record_id, field_id=field_id
                ):
                    await self._table_service.set_table_record_field_value(
                        table_record_id, field_id, [storage_path]
                    )
                case _:
                    assert_never(target)
        except Exception as exc:
            raise AttachmentUploadError(
                f"Field update failed: {exc}",
                step="field_update",
            ) from exc

        return AttachmentUploadResult(
            file_name=file_name,
            content_type=effective_type,
            file_size=content_length,
            field_id=target.field_id,
            storage_path=storage_path,
            download_url=download_url if isinstance(download_url, str) else None,
        )

    async def _resolve_source_bytes(self, attachment: Attachment) -> bytes:
        """Return the attachment bytes from its single source (URL or local path).

        Raises:
            AttachmentUploadError: ``step="download"`` when a URL fetch fails
                its SSRF gate, size cap, or transport; ``step="file_read"``
                when a local read fails.
        """
        if attachment.url is not None:
            try:
                return await self._url_downloader.download(attachment.url)
            except (ValueError, httpx.HTTPError) as exc:
                raise AttachmentUploadError(str(exc), step="download") from exc

        local_path = attachment.path
        if local_path is None:  # Attachment guarantees exactly one source.
            raise AttachmentUploadError("Attachment has no source.", step="file_read")
        file = LocalFile(local_path, max_size_bytes=_MAX_ATTACHMENT_SIZE_BYTES)
        try:
            await asyncio.to_thread(file.read)
        except LocalFileError as exc:
            raise AttachmentUploadError(str(exc), step="file_read") from exc
        return file.bytes

    async def _create_presigned_url(
        self,
        organization_id: str,
        file_name: str,
        content_type: str | None = None,
        content_length: int | None = None,
    ) -> dict[str, Any]:
        """Request a presigned upload URL from Pipefy."""
        payload = await self._executor.execute_query(
            CREATE_PRESIGNED_URL_MUTATION,
            {
                "organizationId": organization_id,
                "fileName": file_name,
                "contentType": content_type,
                "contentLength": content_length,
            },
        )
        node = payload.get("createPresignedUrl")
        if not isinstance(node, dict):
            return {"url": None, "download_url": None}
        return {
            "url": node.get("url"),
            "download_url": node.get("downloadUrl"),
        }

    @staticmethod
    def _extract_storage_path(presigned_url: str) -> str:
        """Return the object key path from a presigned URL.

        Raises:
            ValueError: If the URL has no non-empty path.
        """
        parsed = urlparse(presigned_url)
        path = unquote(parsed.path or "").lstrip("/")
        if not path:
            raise ValueError("Presigned URL has no object path.")
        return path
