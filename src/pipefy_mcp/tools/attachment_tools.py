"""MCP tools to upload attachments to card or table record fields."""

from __future__ import annotations

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
from pydantic import ValidationError

from pipefy_mcp.models.attachment import (
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
    infer_content_type,
)
from pipefy_mcp.models.validators import PipefyId
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.attachment_tool_helpers import (
    build_upload_error_payload,
    build_upload_success_payload,
    format_s3_upload_failure,
    map_upload_error_to_message,
)

_FILE_DOWNLOAD_TIMEOUT_SEC = 60.0
_MAX_DOWNLOAD_SIZE_BYTES = 100 * 1024 * 1024  # 100 MiB

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


def _validate_url_safe(url: str) -> None:
    """Reject URLs that target private/internal networks or non-HTTP schemes.

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
        addr_info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        msg = f"Could not resolve hostname '{hostname}': {exc}"
        raise ValueError(msg) from exc

    for _, _, _, _, sockaddr in addr_info:
        ip = ipaddress.ip_address(sockaddr[0])
        for net in _PRIVATE_NETWORKS:
            if ip in net:
                msg = f"URL resolves to a private/internal address ({ip}). Request blocked."
                raise ValueError(msg)


async def _download_file_bytes(url: str) -> bytes:
    """Fetch file body from an HTTP(S) URL with SSRF protection and size limit.

    Args:
        url: Location to download. Must be http/https and resolve to a public IP.

    Raises:
        ValueError: When the URL targets a private network or exceeds size limit.
        httpx.HTTPError: On transport/HTTP failures.
    """
    _validate_url_safe(url)

    async with httpx.AsyncClient() as http:
        async with http.stream(
            "GET",
            url,
            follow_redirects=True,
            timeout=_FILE_DOWNLOAD_TIMEOUT_SEC,
        ) as response:
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
        async def _upload_flow(
            ctx: Context[ServerSession, None],
            *,
            organization_id: str,
            field_id: str,
            file_name: str,
            file_url: str | None,
            file_content_base64: str | None,
            content_type: str | None,
            update_field_fn: Any,
            debug_prefix: str,
            success_extra: dict[str, Any],
        ) -> dict[str, Any]:
            """Shared orchestration: download/decode → presigned URL → S3 PUT → field update."""
            effective_type = content_type or infer_content_type(file_name)
            await ctx.debug(
                f"{debug_prefix}: field_id={field_id!r} "
                f"file_name={file_name!r} content_type={effective_type!r}"
            )
            try:
                if file_url:
                    await ctx.debug(f"{debug_prefix}: downloading file_url")
                    file_bytes = await _download_file_bytes(file_url.strip())
                else:
                    await ctx.debug(f"{debug_prefix}: decoding base64 payload")
                    file_bytes = _decode_base64_file(file_content_base64 or "")
            except (httpx.HTTPError, binascii.Error, ValueError) as exc:
                await ctx.debug(f"{debug_prefix}: file source error {exc!r}")
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc, "file_download"),
                    step="file_download",
                )

            content_length = len(file_bytes)
            try:
                await ctx.debug(f"{debug_prefix}: createPresignedUrl")
                presigned = await client.create_presigned_url(
                    organization_id,
                    file_name,
                    effective_type,
                    content_length,
                )
            except Exception as exc:  # noqa: BLE001
                await ctx.debug(f"{debug_prefix}: presigned URL failed {exc!r}")
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc, "presigned_url"),
                    step="presigned_url",
                )

            upload_url = presigned.get("url")
            download_url = presigned.get("download_url")
            if not isinstance(upload_url, str) or not upload_url.strip():
                return build_upload_error_payload(
                    message=(
                        "Pipefy did not return a presigned upload URL. "
                        "Check organization_id and file_name, then retry."
                    ),
                    step="presigned_url",
                )

            await ctx.debug(f"{debug_prefix}: S3 PUT")
            put_result = await client.upload_file_to_s3(
                upload_url.strip(),
                file_bytes,
                effective_type,
            )
            status = put_result.get("status_code", 0)
            if not isinstance(status, int) or status >= 400:
                return build_upload_error_payload(
                    message=format_s3_upload_failure(put_result),
                    step="s3_upload",
                )

            try:
                storage_path = client.extract_storage_path(upload_url)
            except ValueError as exc:
                return build_upload_error_payload(
                    message=str(exc),
                    step="s3_upload",
                )

            try:
                await ctx.debug(f"{debug_prefix}: field update")
                await update_field_fn(storage_path)
            except Exception as exc:  # noqa: BLE001
                await ctx.debug(f"{debug_prefix}: field update failed {exc!r}")
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc, "field_update"),
                    step="field_update",
                )

            return build_upload_success_payload(
                download_url=download_url if isinstance(download_url, str) else None,
                file_name=file_name,
                content_type=effective_type,
                file_size=content_length,
                field_id=field_id,
                **success_extra,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def upload_attachment_to_card(
            ctx: Context[ServerSession, None],
            organization_id: PipefyId,
            card_id: int,
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

            async def _update_card(path: str) -> Any:
                return await client.update_card_field(
                    data.card_id, data.field_id, [path]
                )

            return await _upload_flow(
                ctx,
                organization_id=data.organization_id,
                field_id=data.field_id,
                file_name=data.file_name,
                file_url=data.file_url,
                file_content_base64=data.file_content_base64,
                content_type=data.content_type,
                update_field_fn=_update_card,
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

            async def _update_record(path: str) -> Any:
                return await client.set_table_record_field_value(
                    data.table_record_id, data.field_id, [path]
                )

            return await _upload_flow(
                ctx,
                organization_id=data.organization_id,
                field_id=data.field_id,
                file_name=data.file_name,
                file_url=data.file_url,
                file_content_base64=data.file_content_base64,
                content_type=data.content_type,
                update_field_fn=_update_record,
                debug_prefix="upload_attachment_to_table_record",
                success_extra={"table_record_id": data.table_record_id},
            )
