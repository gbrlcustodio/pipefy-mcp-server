"""Attachment uploads: file read, presigned URL, S3 PUT, field update."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Protocol, assert_never
from urllib.parse import unquote, urlparse

import httpx
from httpx import Timeout
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

_BODY_SNIPPET_MAX_CHARS = 500
_ALLOWED_UPLOAD_HOST_RE = re.compile(
    r"^[\w.-]+\.(amazonaws\.com|pipefy\.com)$", re.IGNORECASE
)


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


class AttachmentService:
    """Run the full attachment upload pipeline.

    The pipeline reads the local file (enforcing the size cap), requests a
    presigned URL from Pipefy, PUTs the bytes through an injected
    :class:`S3Uploader`, parses the storage path, and updates the destination
    field on either a card or a table record.

    Failures across every step surface as :class:`AttachmentUploadError`
    carrying ``step`` so surfaces can map to step-aware envelopes.
    """

    def __init__(
        self,
        *,
        executor: GraphQLExecutor,
        card_service: CardService,
        table_service: TableService,
        s3_uploader: S3Uploader | None = None,
    ) -> None:
        self._executor = executor
        self._card_service = card_service
        self._table_service = table_service
        self._s3_uploader: S3Uploader = s3_uploader or HttpxS3Uploader(
            allowed_host_pattern=_ALLOWED_UPLOAD_HOST_RE
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
        file = LocalFile(attachment.path, max_size_bytes=_MAX_ATTACHMENT_SIZE_BYTES)
        try:
            await asyncio.to_thread(file.read)
        except LocalFileError as exc:
            raise AttachmentUploadError(str(exc), step="file_read") from exc

        effective_type = attachment.content_type
        file_name = attachment.name
        content_length = file.size

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
                bytes_=file.bytes,
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
