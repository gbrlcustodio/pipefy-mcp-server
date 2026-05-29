"""MCP tools to upload attachments to card or table record fields."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations
from pipefy_infra.filesystem import LocalFile, LocalFileError
from pipefy_sdk import (
    MAX_ATTACHMENT_SIZE_BYTES,
    Attachment,
    PipefyClient,
    PipefyId,
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
)
from pipefy_sdk.attachment_upload import AttachmentUploadError, AttachmentUploadResult
from pydantic import ValidationError

from pipefy_mcp.tools.attachment_tool_helpers import (
    build_upload_error_payload,
    build_upload_success_payload,
    format_s3_upload_failure,
    map_upload_error_to_message,
)


class AttachmentTools:
    """MCP tools for orchestrated attachment uploads (presigned URL, S3 PUT, field update)."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        def _upload_error_envelope(exc: AttachmentUploadError) -> dict[str, Any]:
            if exc.step == "s3_upload" and exc.body_snippet:
                message = format_s3_upload_failure(
                    {
                        "status_code": exc.status_code,
                        "body_snippet": exc.body_snippet,
                    }
                )
            elif exc.__cause__:
                message = map_upload_error_to_message(exc.__cause__)
            else:
                message = str(exc)
            return build_upload_error_payload(message=message, step=exc.step)

        def _success_envelope(
            result: AttachmentUploadResult,
            field_id: str,
            extra: dict[str, Any],
        ) -> dict[str, Any]:
            return build_upload_success_payload(
                download_url=result["download_url"],
                file_name=result["file_name"],
                content_type=result["content_type"],
                file_size=result["file_size"],
                field_id=field_id,
                **extra,
            )

        # GATED:SELF_HOSTED. This tool accepts only file_path in the
        # local-subprocess profile. Under a self-hosted profile it would also
        # accept a file_url, behind a capability flag, with SSRF + size-cap
        # guards initialized from injected settings (not from a fresh
        # PipefySettings() env read).
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def upload_attachment_to_card(
            ctx: Context[ServerSession, None],
            organization_id: PipefyId,
            card_id: PipefyId,
            field_id: PipefyId,
            file_path: str,
            file_name: str | None = None,
            content_type: str | None = None,
        ) -> dict[str, Any]:
            """Upload one file to a card attachment field (presigned URL, S3 PUT, then updateCardField).

            Handles one file per call. To attach multiple files, call this tool once per file.

            ``file_path`` is the local path the MCP server (running as the user)
            reads. ``~`` is expanded. When ``file_name`` is omitted, the path's
            basename fills it in. If ``content_type`` is omitted, it is inferred
            from the file name.

            Args:
                organization_id: Pipefy organization id. Use ``get_organization`` or ``get_pipe`` to find it.
                card_id: Target card id.
                field_id: Attachment field slug (e.g. "document_upload"), not the uuid.
                file_path: Local filesystem path. Supports ``~`` expansion.
                file_name: File name including extension. Optional; defaults to the path's basename.
                content_type: Optional MIME type; sent with the S3 upload and presigned request.
            """
            try:
                data = UploadAttachmentToCardInput(
                    organization_id=organization_id,
                    card_id=card_id,
                    field_id=field_id,
                    file_name=file_name,
                    file_path=file_path,
                    content_type=content_type,
                )
            except ValidationError as exc:
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc),
                    step="validation",
                )

            await ctx.debug(
                f"upload_attachment_to_card: field_id={data.field_id!r} file_path={data.file_path!r}"
            )

            file = LocalFile(
                Path(data.file_path), max_size_bytes=MAX_ATTACHMENT_SIZE_BYTES
            )
            try:
                await asyncio.to_thread(file.read)
            except LocalFileError as exc:
                await ctx.debug(f"upload_attachment_to_card: file source error {exc!r}")
                return build_upload_error_payload(message=str(exc), step="file_read")

            attachment = Attachment(
                file, name=data.file_name, content_type=data.content_type
            )

            try:
                result = await attachment.upload_to_card_field(
                    client,
                    organization_id=data.organization_id,
                    card_id=data.card_id,
                    field_id=data.field_id,
                )
            except AttachmentUploadError as exc:
                await ctx.debug(
                    f"upload_attachment_to_card: pipeline failed at step={exc.step} {exc!r}"
                )
                return _upload_error_envelope(exc)

            return _success_envelope(result, data.field_id, {"card_id": data.card_id})

        # GATED:SELF_HOSTED. Same gate as upload_attachment_to_card above;
        # file_url support would land here too under a hosted profile.
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def upload_attachment_to_table_record(
            ctx: Context[ServerSession, None],
            organization_id: PipefyId,
            table_record_id: PipefyId,
            field_id: PipefyId,
            file_path: str,
            file_name: str | None = None,
            content_type: str | None = None,
        ) -> dict[str, Any]:
            """Upload one file to a table record attachment field (presigned URL, S3 PUT, setTableRecordFieldValue).

            Handles one file per call. To attach multiple files, call this tool once per file.

            ``file_path`` is the local path the MCP server (running as the user)
            reads. ``~`` is expanded. When ``file_name`` is omitted, the path's
            basename fills it in. If ``content_type`` is omitted, it is inferred
            from the file name.

            Args:
                organization_id: Pipefy organization id. Use ``get_organization`` or ``get_pipe`` to find it.
                table_record_id: Database table record id.
                field_id: Attachment field slug on the table record (e.g. "document_upload"), not the uuid.
                file_path: Local filesystem path. Supports ``~`` expansion.
                file_name: File name including extension. Optional; defaults to the path's basename.
                content_type: Optional MIME type for storage.
            """
            try:
                data = UploadAttachmentToTableRecordInput(
                    organization_id=organization_id,
                    table_record_id=table_record_id,
                    field_id=field_id,
                    file_name=file_name,
                    file_path=file_path,
                    content_type=content_type,
                )
            except ValidationError as exc:
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc),
                    step="validation",
                )

            await ctx.debug(
                f"upload_attachment_to_table_record: field_id={data.field_id!r} file_path={data.file_path!r}"
            )

            file = LocalFile(
                Path(data.file_path), max_size_bytes=MAX_ATTACHMENT_SIZE_BYTES
            )
            try:
                await asyncio.to_thread(file.read)
            except LocalFileError as exc:
                await ctx.debug(
                    f"upload_attachment_to_table_record: file source error {exc!r}"
                )
                return build_upload_error_payload(message=str(exc), step="file_read")

            attachment = Attachment(
                file, name=data.file_name, content_type=data.content_type
            )

            try:
                result = await attachment.upload_to_table_record_field(
                    client,
                    organization_id=data.organization_id,
                    table_record_id=data.table_record_id,
                    field_id=data.field_id,
                )
            except AttachmentUploadError as exc:
                await ctx.debug(
                    f"upload_attachment_to_table_record: pipeline failed at step={exc.step} {exc!r}"
                )
                return _upload_error_envelope(exc)

            return _success_envelope(
                result,
                data.field_id,
                {"table_record_id": data.table_record_id},
            )
