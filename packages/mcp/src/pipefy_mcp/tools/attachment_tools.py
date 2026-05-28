"""MCP tools to upload attachments to card or table record fields."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations
from pipefy_infra import security
from pipefy_sdk import (
    PipefyClient,
    PipefyId,
    PipefySettings,
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
)
from pipefy_sdk.attachment_upload import (
    AttachmentUploadError,
    AttachmentUploadResult,
)
from pydantic import ValidationError

from pipefy_mcp.tools.attachment_tool_helpers import (
    build_upload_error_payload,
    build_upload_success_payload,
    format_s3_upload_failure,
    map_upload_error_to_message,
)

_FILE_DOWNLOAD_TIMEOUT_SEC = 60.0
_MAX_DOWNLOAD_SIZE_BYTES = 100 * 1024 * 1024  # 100 MiB


async def _validate_url_safe(url: str, *, allow_insecure: bool) -> None:
    """Reject URLs that target private/internal networks or non-HTTP schemes.

    Delegates to :func:`security.validate_and_assert_public_url`, which runs
    the sync gate (scheme + literal-IP) and the async DNS gate together.
    ``allow_insecure`` is wired from ``PipefySettings.allow_insecure_urls``
    (``PIPEFY_ALLOW_INSECURE_URLS``) so the attachment surface honours the
    same policy switch as ``base_url`` / ``auth_url``: HTTPS-only in
    production, http + internal hosts permitted only in dev mode.

    Raises:
        ValueError: When the URL is unsafe for server-side fetch.
    """
    await security.validate_and_assert_public_url(
        url, field_label="url", allow_insecure=allow_insecure
    )


_MAX_REDIRECTS = 3


async def _download_file_bytes(url: str, *, allow_insecure: bool) -> bytes:
    """Fetch file body from an HTTP(S) URL with SSRF protection and size limit.

    Redirects are followed manually (up to ``_MAX_REDIRECTS``) so that each
    intermediate URL is validated against private-network rules — preventing
    redirect-based SSRF bypass.

    Args:
        url: Location to download. Must be http/https and resolve to a public IP.

    Raises:
        ValueError: When the URL targets a private network, exceeds size limit,
            or the redirect chain is too long.
        httpx.HTTPError: On transport/HTTP failures.
    """
    await _validate_url_safe(url, allow_insecure=allow_insecure)
    current_url = url

    async with httpx.AsyncClient() as http:
        for _ in range(_MAX_REDIRECTS + 1):
            async with http.stream(
                "GET",
                current_url,
                follow_redirects=False,
                timeout=_FILE_DOWNLOAD_TIMEOUT_SEC,
            ) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Redirect without Location header")
                    resolved = urljoin(current_url, location.strip())
                    await _validate_url_safe(resolved, allow_insecure=allow_insecure)
                    current_url = resolved
                    continue

                response.raise_for_status()

                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > _MAX_DOWNLOAD_SIZE_BYTES:
                    msg = (
                        f"File too large: Content-Length {content_length} bytes "
                        f"exceeds the {_MAX_DOWNLOAD_SIZE_BYTES // (1024 * 1024)} MiB limit."
                    )
                    raise ValueError(msg)

                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > _MAX_DOWNLOAD_SIZE_BYTES:
                        msg = (
                            f"File too large: downloaded {total} bytes, "
                            f"exceeding the {_MAX_DOWNLOAD_SIZE_BYTES // (1024 * 1024)} MiB limit."
                        )
                        raise ValueError(msg)
                    chunks.append(chunk)
                return b"".join(chunks)

        raise ValueError(f"Too many redirects (max {_MAX_REDIRECTS})")


def _decode_base64_file(payload: str) -> bytes:
    """Decode base64 file content.

    Args:
        payload: Standard base64 text (whitespace ignored).

    Raises:
        binascii.Error: When padding or alphabet is invalid.
    """
    cleaned = "".join(payload.split())
    return base64.b64decode(cleaned, validate=True)


class AttachmentTools:
    """MCP tools for orchestrated attachment uploads (presigned URL, S3 PUT, field update)."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient, settings: PipefySettings) -> None:
        # Pull the policy switch from the same ``PipefySettings`` instance that
        # built ``client`` so the attachment gate can't drift from the client
        # config when a caller constructs ``Settings`` programmatically instead
        # of relying purely on env. Matches the toggle that gates ``base_url``
        # / ``auth_url`` in ``PipefySettings`` / ``AuthSettings`` so the
        # attachment surface does not silently accept plain http on a tightened
        # deployment.
        allow_insecure_urls = settings.allow_insecure_urls

        async def _resolve_file_bytes(
            ctx: Context[ServerSession, None],
            *,
            file_url: str | None,
            file_content_base64: str | None,
            debug_prefix: str,
        ) -> tuple[bytes, dict[str, Any] | None]:
            """Resolve bytes from URL (with SSRF guard) or base64.

            Returns ``(file_bytes, None)`` on success, or ``(b"", error_payload)`` on
            file-source failure so the caller can short-circuit with the envelope.
            """
            try:
                if file_url:
                    await ctx.debug(f"{debug_prefix}: downloading file_url")
                    return (
                        await _download_file_bytes(
                            file_url.strip(), allow_insecure=allow_insecure_urls
                        ),
                        None,
                    )
                await ctx.debug(f"{debug_prefix}: decoding base64 payload")
                return _decode_base64_file(file_content_base64 or ""), None
            except (httpx.HTTPError, binascii.Error, ValueError) as exc:
                await ctx.debug(f"{debug_prefix}: file source error {exc!r}")
                return b"", build_upload_error_payload(
                    message=map_upload_error_to_message(exc, "file_download"),
                    step="file_download",
                )

        async def _upload_via_facade(
            ctx: Context[ServerSession, None],
            *,
            organization_id: str,
            field_id: str,
            file_name: str,
            file_url: str | None,
            file_content_base64: str | None,
            content_type: str | None,
            upload_call: Callable[[bytes], Awaitable[AttachmentUploadResult]],
            debug_prefix: str,
            success_extra: dict[str, Any],
        ) -> dict[str, Any]:
            """Source-aware MCP wrapper around the SDK upload pipeline.

            MCP needs to resolve bytes from a URL (with SSRF guard) or base64 before
            handing off to the SDK facade method that runs presigned → S3 → field update.
            """
            await ctx.debug(
                f"{debug_prefix}: field_id={field_id!r} file_name={file_name!r}"
            )
            file_bytes, error_payload = await _resolve_file_bytes(
                ctx,
                file_url=file_url,
                file_content_base64=file_content_base64,
                debug_prefix=debug_prefix,
            )
            if error_payload is not None:
                return error_payload

            try:
                result = await upload_call(file_bytes)
            except AttachmentUploadError as exc:
                await ctx.debug(
                    f"{debug_prefix}: pipeline failed at step={exc.step} {exc!r}"
                )
                # Surface the richer GraphQL/transport error message when the
                # SDK exception was raised from an underlying transport error
                # (the SDK preserves it via ``raise ... from``). The s3_upload
                # step gets body-snippet-aware formatting via the local helper.
                if exc.step in ("presigned_url", "field_update") and exc.__cause__:
                    rich_message = map_upload_error_to_message(exc.__cause__, exc.step)
                elif exc.step == "s3_upload" and exc.body_snippet:
                    rich_message = format_s3_upload_failure(
                        {
                            "status_code": exc.status_code,
                            "body_snippet": exc.body_snippet,
                        }
                    )
                else:
                    rich_message = str(exc)
                return build_upload_error_payload(
                    message=rich_message,
                    step=exc.step,
                )

            return build_upload_success_payload(
                download_url=result["download_url"],
                file_name=result["file_name"],
                content_type=result["content_type"],
                file_size=result["file_size"],
                field_id=result["field_id"],
                **success_extra,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def upload_attachment_to_card(
            ctx: Context[ServerSession, None],
            organization_id: PipefyId,
            card_id: PipefyId,
            field_id: PipefyId,
            file_name: str,
            file_url: str | None = None,
            file_content_base64: str | None = None,
            content_type: str | None = None,
        ) -> dict[str, Any]:
            """Upload one file to a card attachment field (presigned URL, S3 PUT, then updateCardField).

            Handles one file per call. To attach multiple files, call this tool once per file.

            Provide exactly one of ``file_url`` (HTTP download) or ``file_content_base64``. If
            ``content_type`` is omitted, it is inferred from ``file_name``.

            Args:
                organization_id: Pipefy organization id. Use ``get_organization`` or ``get_pipe`` to find it.
                card_id: Target card id.
                field_id: Attachment field slug (e.g. "document_upload"), not the uuid.
                file_name: File name including extension (used for storage and MIME guess).
                file_url: Public or reachable URL to download the file bytes (max 100 MiB).
                file_content_base64: Raw file bytes encoded as standard base64.
                content_type: Optional MIME type; sent with the S3 upload and presigned request.
            """
            try:
                data = UploadAttachmentToCardInput(
                    organization_id=organization_id,
                    card_id=card_id,
                    field_id=field_id,
                    file_name=file_name,
                    file_url=file_url,
                    file_content_base64=file_content_base64,
                    content_type=content_type,
                )
            except ValidationError as exc:
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc, "validation"),
                    step="validation",
                )

            async def _upload(file_bytes: bytes) -> Any:
                return await client.upload_attachment_to_card_field(
                    organization_id=data.organization_id,
                    card_id=data.card_id,
                    field_id=data.field_id,
                    file_name=data.file_name,
                    file_bytes=file_bytes,
                    content_type=data.content_type,
                )

            return await _upload_via_facade(
                ctx,
                organization_id=data.organization_id,
                field_id=data.field_id,
                file_name=data.file_name,
                file_url=data.file_url,
                file_content_base64=data.file_content_base64,
                content_type=data.content_type,
                upload_call=_upload,
                debug_prefix="upload_attachment_to_card",
                success_extra={"card_id": data.card_id},
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def upload_attachment_to_table_record(
            ctx: Context[ServerSession, None],
            organization_id: PipefyId,
            table_record_id: PipefyId,
            field_id: PipefyId,
            file_name: str,
            file_url: str | None = None,
            file_content_base64: str | None = None,
            content_type: str | None = None,
        ) -> dict[str, Any]:
            """Upload one file to a table record attachment field (presigned URL, S3 PUT, setTableRecordFieldValue).

            Handles one file per call. To attach multiple files, call this tool once per file.

            Provide exactly one of ``file_url`` or ``file_content_base64``. If ``content_type`` is
            omitted, it is inferred from ``file_name``.

            Args:
                organization_id: Pipefy organization id. Use ``get_organization`` or ``get_pipe`` to find it.
                table_record_id: Database table record id.
                field_id: Attachment field slug on the table record (e.g. "document_upload"), not the uuid.
                file_name: File name including extension.
                file_url: URL to download the file from (max 100 MiB).
                file_content_base64: Base64-encoded file bytes.
                content_type: Optional MIME type for storage.
            """
            try:
                data = UploadAttachmentToTableRecordInput(
                    organization_id=organization_id,
                    table_record_id=table_record_id,
                    field_id=field_id,
                    file_name=file_name,
                    file_url=file_url,
                    file_content_base64=file_content_base64,
                    content_type=content_type,
                )
            except ValidationError as exc:
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc, "validation"),
                    step="validation",
                )

            async def _upload(file_bytes: bytes) -> Any:
                return await client.upload_attachment_to_table_record_field(
                    organization_id=data.organization_id,
                    table_record_id=data.table_record_id,
                    field_id=data.field_id,
                    file_name=data.file_name,
                    file_bytes=file_bytes,
                    content_type=data.content_type,
                )

            return await _upload_via_facade(
                ctx,
                organization_id=data.organization_id,
                field_id=data.field_id,
                file_name=data.file_name,
                file_url=data.file_url,
                file_content_base64=data.file_content_base64,
                content_type=data.content_type,
                upload_call=_upload,
                debug_prefix="upload_attachment_to_table_record",
                success_extra={"table_record_id": data.table_record_id},
            )
