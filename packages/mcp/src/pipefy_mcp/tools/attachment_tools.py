"""MCP tools to upload attachments to card or table record fields."""

from __future__ import annotations

import asyncio
import base64
import binascii
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations
from pipefy_sdk import (
    PipefyClient,
    PipefyId,
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
    assert_attachment_size_within_cap,
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
        async def _read_local_or_decode(
            ctx: Context[ServerSession, None],
            *,
            file_path: str | None,
            file_content_base64: str | None,
            debug_prefix: str,
        ) -> tuple[bytes, dict[str, Any] | None]:
            """Resolve bytes from a local file path or a base64 payload.

            Returns ``(file_bytes, None)`` on success, or ``(b"", error_payload)``
            when the source is unusable so the caller can short-circuit with the
            envelope.
            """
            try:
                # Match the SDK validator's whitespace-aware source check
                # (`_source_nonempty`): a whitespace-only `file_path` is treated
                # as no path, so the base64 source takes over.
                if file_path and file_path.strip():
                    await ctx.debug(f"{debug_prefix}: reading file_path")
                    p = Path(file_path.strip()).expanduser()
                    if not p.is_file():
                        raise ValueError(f"File not found or not a regular file: {p}")
                    assert_attachment_size_within_cap(p.stat().st_size, str(p))
                    data = await asyncio.to_thread(p.read_bytes)
                    return data, None
                await ctx.debug(f"{debug_prefix}: decoding base64 payload")
                decoded = _decode_base64_file(file_content_base64 or "")
                assert_attachment_size_within_cap(len(decoded), "file_content_base64")
                return decoded, None
            except (OSError, binascii.Error, ValueError) as exc:
                await ctx.debug(f"{debug_prefix}: file source error {exc!r}")
                return b"", build_upload_error_payload(
                    message=map_upload_error_to_message(exc),
                    step="file_read",
                )

        async def _upload_via_facade(
            ctx: Context[ServerSession, None],
            *,
            field_id: str,
            file_name: str,
            file_path: str | None,
            file_content_base64: str | None,
            upload_call: Callable[[bytes], Awaitable[AttachmentUploadResult]],
            debug_prefix: str,
            success_extra: dict[str, Any],
        ) -> dict[str, Any]:
            """Source-aware MCP wrapper around the SDK upload pipeline.

            MCP reads bytes from a local file or decodes base64 before handing
            off to the SDK facade method that runs presigned URL → S3 PUT →
            field update.
            """
            await ctx.debug(
                f"{debug_prefix}: field_id={field_id!r} file_name={file_name!r}"
            )
            file_bytes, error_payload = await _read_local_or_decode(
                ctx,
                file_path=file_path,
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
                if exc.step == "s3_upload" and exc.body_snippet:
                    rich_message = format_s3_upload_failure(
                        {
                            "status_code": exc.status_code,
                            "body_snippet": exc.body_snippet,
                        }
                    )
                elif exc.__cause__:
                    rich_message = map_upload_error_to_message(exc.__cause__)
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

        # GATED:SELF_HOSTED. This tool accepts only file_path / file_content_base64
        # in the local-subprocess profile. Under a self-hosted profile it would
        # also accept a file_url, behind a capability flag, with SSRF + size-cap
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
            file_name: str | None = None,
            file_path: str | None = None,
            file_content_base64: str | None = None,
            content_type: str | None = None,
        ) -> dict[str, Any]:
            """Upload one file to a card attachment field (presigned URL, S3 PUT, then updateCardField).

            Handles one file per call. To attach multiple files, call this tool once per file.

            Provide exactly one of ``file_path`` (local filesystem path the MCP server
            can read; supports ``~`` expansion) or ``file_content_base64`` (in-memory
            bytes the agent never wrote to disk). When ``file_path`` is provided and
            ``file_name`` is omitted, the path's basename fills it in. If
            ``content_type`` is omitted, it is inferred from the file name.

            Args:
                organization_id: Pipefy organization id. Use ``get_organization`` or ``get_pipe`` to find it.
                card_id: Target card id.
                field_id: Attachment field slug (e.g. "document_upload"), not the uuid.
                file_name: File name including extension. Optional when ``file_path`` is provided; required for base64.
                file_path: Local filesystem path. Read by the MCP server (which runs locally as the user).
                file_content_base64: Raw file bytes encoded as standard base64.
                content_type: Optional MIME type; sent with the S3 upload and presigned request.
            """
            try:
                data = UploadAttachmentToCardInput(
                    organization_id=organization_id,
                    card_id=card_id,
                    field_id=field_id,
                    file_name=file_name,
                    file_path=file_path,
                    file_content_base64=file_content_base64,
                    content_type=content_type,
                )
            except ValidationError as exc:
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc),
                    step="validation",
                )

            resolved_file_name = cast(str, data.file_name)

            async def _upload(file_bytes: bytes) -> Any:
                return await client.upload_attachment_to_card_field(
                    organization_id=data.organization_id,
                    card_id=data.card_id,
                    field_id=data.field_id,
                    file_name=resolved_file_name,
                    file_bytes=file_bytes,
                    content_type=data.content_type,
                )

            return await _upload_via_facade(
                ctx,
                field_id=data.field_id,
                file_name=resolved_file_name,
                file_path=data.file_path,
                file_content_base64=data.file_content_base64,
                upload_call=_upload,
                debug_prefix="upload_attachment_to_card",
                success_extra={"card_id": data.card_id},
            )

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
            file_name: str | None = None,
            file_path: str | None = None,
            file_content_base64: str | None = None,
            content_type: str | None = None,
        ) -> dict[str, Any]:
            """Upload one file to a table record attachment field (presigned URL, S3 PUT, setTableRecordFieldValue).

            Handles one file per call. To attach multiple files, call this tool once per file.

            Provide exactly one of ``file_path`` or ``file_content_base64``. When
            ``file_path`` is provided and ``file_name`` is omitted, the path's
            basename fills it in. If ``content_type`` is omitted, it is inferred
            from the file name.

            Args:
                organization_id: Pipefy organization id. Use ``get_organization`` or ``get_pipe`` to find it.
                table_record_id: Database table record id.
                field_id: Attachment field slug on the table record (e.g. "document_upload"), not the uuid.
                file_name: File name including extension. Optional when ``file_path`` is provided; required for base64.
                file_path: Local filesystem path. Read by the MCP server (which runs locally as the user).
                file_content_base64: Base64-encoded file bytes.
                content_type: Optional MIME type for storage.
            """
            try:
                data = UploadAttachmentToTableRecordInput(
                    organization_id=organization_id,
                    table_record_id=table_record_id,
                    field_id=field_id,
                    file_name=file_name,
                    file_path=file_path,
                    file_content_base64=file_content_base64,
                    content_type=content_type,
                )
            except ValidationError as exc:
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc),
                    step="validation",
                )

            resolved_file_name = cast(str, data.file_name)

            async def _upload(file_bytes: bytes) -> Any:
                return await client.upload_attachment_to_table_record_field(
                    organization_id=data.organization_id,
                    table_record_id=data.table_record_id,
                    field_id=data.field_id,
                    file_name=resolved_file_name,
                    file_bytes=file_bytes,
                    content_type=data.content_type,
                )

            return await _upload_via_facade(
                ctx,
                field_id=data.field_id,
                file_name=resolved_file_name,
                file_path=data.file_path,
                file_content_base64=data.file_content_base64,
                upload_call=_upload,
                debug_prefix="upload_attachment_to_table_record",
                success_extra={"table_record_id": data.table_record_id},
            )
