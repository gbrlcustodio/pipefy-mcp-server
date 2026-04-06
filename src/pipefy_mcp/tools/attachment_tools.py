"""MCP tools to upload attachments to card or table record fields."""

from __future__ import annotations

import base64
import binascii
from typing import Any

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
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.attachment_tool_helpers import (
    build_upload_error_payload,
    build_upload_success_payload,
    format_s3_upload_failure,
    map_upload_error_to_message,
)

_FILE_DOWNLOAD_TIMEOUT_SEC = 60.0


async def _download_file_bytes(url: str) -> bytes:
    """Fetch file body from an HTTP(S) URL.

    Args:
        url: Location to download.
    """
    async with httpx.AsyncClient() as http:
        response = await http.get(
            url,
            follow_redirects=True,
            timeout=_FILE_DOWNLOAD_TIMEOUT_SEC,
        )
        response.raise_for_status()
        return response.content


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
        async def _upload_to_card_flow(
            ctx: Context[ServerSession, None],
            data: UploadAttachmentToCardInput,
        ) -> dict[str, Any]:
            file_name = data.file_name
            effective_type = data.content_type or infer_content_type(file_name)
            await ctx.debug(
                f"upload_attachment_to_card: card_id={data.card_id} field_id={data.field_id!r} "
                f"file_name={file_name!r} content_type={effective_type!r}"
            )
            try:
                if data.file_url:
                    await ctx.debug("upload_attachment_to_card: downloading file_url")
                    file_bytes = await _download_file_bytes(data.file_url.strip())
                else:
                    await ctx.debug(
                        "upload_attachment_to_card: decoding base64 payload"
                    )
                    file_bytes = _decode_base64_file(data.file_content_base64 or "")
            except httpx.HTTPError as exc:
                await ctx.debug(f"upload_attachment_to_card: file source error {exc!r}")
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc, "file_download"),
                    step="file_download",
                )
            except binascii.Error as exc:
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc, "file_download"),
                    step="file_download",
                )

            content_length = len(file_bytes)
            try:
                await ctx.debug("upload_attachment_to_card: createPresignedUrl")
                presigned = await client.create_presigned_url(
                    data.organization_id,
                    file_name,
                    effective_type,
                    content_length,
                )
            except Exception as exc:  # noqa: BLE001
                await ctx.debug(
                    f"upload_attachment_to_card: presigned URL failed {exc!r}"
                )
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

            await ctx.debug("upload_attachment_to_card: S3 PUT")
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
                await ctx.debug("upload_attachment_to_card: updateCardField")
                await client.update_card_field(
                    data.card_id,
                    data.field_id,
                    [storage_path],
                )
            except Exception as exc:  # noqa: BLE001
                await ctx.debug(
                    f"upload_attachment_to_card: field update failed {exc!r}"
                )
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc, "field_update"),
                    step="field_update",
                )

            return build_upload_success_payload(
                download_url=download_url if isinstance(download_url, str) else None,
                file_name=file_name,
                content_type=effective_type,
                file_size=content_length,
                field_id=data.field_id,
                card_id=data.card_id,
            )

        async def _upload_to_table_flow(
            ctx: Context[ServerSession, None],
            data: UploadAttachmentToTableRecordInput,
        ) -> dict[str, Any]:
            file_name = data.file_name
            effective_type = data.content_type or infer_content_type(file_name)
            await ctx.debug(
                f"upload_attachment_to_table_record: record_id={data.table_record_id!r} "
                f"field_id={data.field_id!r} file_name={file_name!r}"
            )
            try:
                if data.file_url:
                    file_bytes = await _download_file_bytes(data.file_url.strip())
                else:
                    file_bytes = _decode_base64_file(data.file_content_base64 or "")
            except httpx.HTTPError as exc:
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc, "file_download"),
                    step="file_download",
                )
            except binascii.Error as exc:
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc, "file_download"),
                    step="file_download",
                )

            content_length = len(file_bytes)
            try:
                await ctx.debug("upload_attachment_to_table_record: createPresignedUrl")
                presigned = await client.create_presigned_url(
                    data.organization_id,
                    file_name,
                    effective_type,
                    content_length,
                )
            except Exception as exc:  # noqa: BLE001
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
                await ctx.debug(
                    "upload_attachment_to_table_record: setTableRecordFieldValue"
                )
                await client.set_table_record_field_value(
                    data.table_record_id,
                    data.field_id,
                    [storage_path],
                )
            except Exception as exc:  # noqa: BLE001
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc, "field_update"),
                    step="field_update",
                )

            return build_upload_success_payload(
                download_url=download_url if isinstance(download_url, str) else None,
                file_name=file_name,
                content_type=effective_type,
                file_size=content_length,
                field_id=data.field_id,
                table_record_id=data.table_record_id,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def upload_attachment_to_card(
            ctx: Context[ServerSession, None],
            organization_id: str,
            card_id: int,
            field_id: str,
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
                organization_id: Pipefy organization id (string).
                card_id: Target card id.
                field_id: Attachment field slug (e.g. "document_upload"), not the uuid.
                file_name: File name including extension (used for storage and MIME guess).
                file_url: Public or reachable URL to download the file bytes.
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
            return await _upload_to_card_flow(ctx, data)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def upload_attachment_to_table_record(
            ctx: Context[ServerSession, None],
            organization_id: str,
            table_record_id: str,
            field_id: str,
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
                organization_id: Pipefy organization id (string).
                table_record_id: Database table record id.
                field_id: Attachment field slug on the table record (e.g. "document_upload"), not the uuid.
                file_name: File name including extension.
                file_url: URL to download the file from.
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
            return await _upload_to_table_flow(ctx, data)
