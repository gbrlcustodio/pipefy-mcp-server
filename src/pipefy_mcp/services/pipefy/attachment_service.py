"""Presigned URL creation, storage path parsing, and S3 upload via HTTP PUT."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
from httpx import Timeout
from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.attachment_queries import (
    CREATE_PRESIGNED_URL_MUTATION,
)
from pipefy_mcp.settings import PipefySettings

_BODY_SNIPPET_MAX_CHARS = 500
_ALLOWED_UPLOAD_HOST_RE = re.compile(
    r"^[\w.-]+\.(amazonaws\.com|pipefy\.com)$", re.IGNORECASE
)


class AttachmentService(BasePipefyClient):
    """Create upload URLs and PUT file bytes to object storage."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    async def create_presigned_url(
        self,
        organization_id: str,
        file_name: str,
        content_type: str | None = None,
        content_length: int | None = None,
    ) -> dict[str, Any]:
        """Request a presigned upload URL from Pipefy.

        Args:
            organization_id: Organization ID.
            file_name: Target file name for the upload.
            content_type: Optional MIME type for the object.
            content_length: Optional size in bytes.
        """
        payload = await self.execute_query(
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
    def extract_storage_path(presigned_url: str) -> str:
        """Return the object key path from a presigned URL (no host, query, or leading slash).

        Args:
            presigned_url: Full HTTPS URL including path and optional query string.

        Raises:
            ValueError: If the URL has no non-empty path.
        """
        parsed = urlparse(presigned_url)
        path = unquote(parsed.path or "").lstrip("/")
        if not path:
            raise ValueError("Presigned URL has no object path.")
        return path

    async def upload_file_to_s3(
        self,
        presigned_url: str,
        file_bytes: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """PUT file bytes to the given presigned URL.

        Args:
            presigned_url: Destination URL (not echoed back on failure).
            file_bytes: Raw file content.
            content_type: Optional ``Content-Type`` header for the request.
        """
        host = urlparse(presigned_url).hostname or ""
        if not _ALLOWED_UPLOAD_HOST_RE.match(host):
            raise ValueError(
                f"Upload URL host '{host}' is not in the allow-list "
                "(*.amazonaws.com, *.pipefy.com)."
            )
        headers: dict[str, str] = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        async with httpx.AsyncClient(
            timeout=Timeout(timeout=60),
        ) as client:
            response = await client.put(
                presigned_url, content=file_bytes, headers=headers
            )
        result: dict[str, Any] = {"status_code": response.status_code}
        if response.status_code >= 400:
            result["body_snippet"] = response.text[:_BODY_SNIPPET_MAX_CHARS]
        return result
