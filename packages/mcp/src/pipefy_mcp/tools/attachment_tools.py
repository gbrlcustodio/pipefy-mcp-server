"""MCP tools to upload attachments to card or table record fields."""

from __future__ import annotations

import asyncio
import base64
import binascii
import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations
from pipefy_sdk import (
    PipefyClient,
    PipefyId,
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
)
from pipefy_sdk.attachment_upload import AttachmentUploadError
from pydantic import ValidationError

from pipefy_mcp.tools.attachment_tool_helpers import (
    build_upload_error_payload,
    build_upload_success_payload,
    format_s3_upload_failure,
    map_upload_error_to_message,
)

_FILE_DOWNLOAD_TIMEOUT_SEC = 60.0
_MAX_DOWNLOAD_SIZE_BYTES = 100 * 1024 * 1024  # 100 MiB


def _parse_s3_status_from_message(message: str) -> int | None:
    """Extract HTTP status code from ``AttachmentUploadError`` s3 message."""
    import re

    m = re.search(r"HTTP (\d+)", message)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fd00::/8"),
    ipaddress.ip_network("fe80::/10"),
)


async def _validate_url_safe(url: str) -> None:
    """Reject URLs that target private/internal networks or non-HTTP schemes.

    DNS resolution is offloaded to a thread executor so it does not block the
    async event loop.

    Raises:
        ValueError: When the URL is unsafe for server-side fetch.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        msg = f"Only http and https URLs are allowed, got '{parsed.scheme}'."
        raise ValueError(msg)

    hostname = parsed.hostname
    if not hostname:
        msg = "URL has no hostname."
        raise ValueError(msg)

    try:
        loop = asyncio.get_event_loop()
        addr_info = await loop.run_in_executor(
            None, socket.getaddrinfo, hostname, None, 0, socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        msg = f"Could not resolve hostname '{hostname}': {exc}"
        raise ValueError(msg) from exc

    for _, _, _, _, sockaddr in addr_info:
        ip = ipaddress.ip_address(sockaddr[0])
        for net in _PRIVATE_NETWORKS:
            if ip in net:
                msg = f"URL resolves to a private/internal address ({ip}). Request blocked."
                raise ValueError(msg)


_MAX_REDIRECTS = 3


async def _download_file_bytes(url: str) -> bytes:
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
    await _validate_url_safe(url)
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
                    await _validate_url_safe(location)
                    current_url = location
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
    def register(mcp: FastMCP, client: PipefyClient) -> None:
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
                    return await _download_file_bytes(file_url.strip()), None
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
            upload_call,
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
                            "status_code": _parse_s3_status_from_message(str(exc)),
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
