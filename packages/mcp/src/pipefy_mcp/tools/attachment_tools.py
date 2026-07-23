"""MCP tools to upload attachments to card or table record fields."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations
from pipefy_sdk import (
    Attachment,
    AttachmentUploadError,
    AttachmentUploadResult,
    CardTarget,
    PipefyId,
    TableRecordTarget,
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
)
from pydantic import ValidationError

from pipefy_mcp.tools.attachment_tool_helpers import (
    build_upload_error_payload,
    build_upload_success_payload,
    format_s3_upload_failure,
    map_upload_error_to_message,
)
from pipefy_mcp.tools.remote_profile import REMOTE
from pipefy_mcp.tools.tool_context import get_pipefy_client, is_remote_profile

# Appended to a file_read error so an agent whose files live elsewhere (a hosted
# server, or a co-located client whose sandbox differs from the server's host)
# knows the path is read on the server's machine and where to turn instead.
_FILE_READ_TOPOLOGY_HINT = (
    " The path is read on the machine running the MCP server, which may not be "
    "the agent's own environment; if the file is elsewhere, pass file_url instead."
)

# file_path reads the server's own disk, which has no meaning on a multi-user
# hosted server; the input restriction is enforced per call (exposure vs input
# restriction, package CLAUDE.md), mirroring create_ipaas_connection's $env case.
_REMOTE_FILE_PATH_REJECTION = (
    "file_path is not available on the hosted server (it reads the server's "
    "local disk); pass file_url instead."
)


def _redact_url_query(url: str | None) -> str | None:
    """Drop the query string from a URL so a signed source URL's tokens never hit logs."""
    if not url:
        return url
    return urlparse(url)._replace(query="", fragment="").geturl()


def _build_attachment(
    *,
    file_path: str | None,
    file_url: str | None,
    file_name: str | None,
    content_type: str | None,
) -> Attachment:
    """Build an :class:`Attachment` from validated tool input.

    The input DTO already guarantees exactly one of ``file_path`` / ``file_url``.
    :class:`Attachment` raises ``ValueError`` when the name cannot be resolved
    (a URL with no basename and no explicit ``file_name``); callers map that to
    a ``step=validation`` envelope.
    """
    return Attachment(
        path=Path(file_path) if file_path else None,
        url=file_url,
        name=file_name,
        content_type=content_type,
    )


class AttachmentTools:
    """MCP tools for orchestrated attachment uploads (presigned URL, S3 PUT, field update)."""

    @staticmethod
    def register(mcp: FastMCP) -> None:
        def _upload_error_envelope(exc: AttachmentUploadError) -> dict[str, Any]:
            if exc.step == "file_read":
                # Preserve the original LocalFileError message (no type prefix or
                # GraphQL mapper rewrite); the cause chain carries it verbatim.
                # Append the topology hint so the reader knows whose disk is read.
                base = str(exc.__cause__) if exc.__cause__ else str(exc)
                message = base + _FILE_READ_TOPOLOGY_HINT
            elif exc.step == "s3_upload" and exc.body_snippet:
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

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
            meta=REMOTE,
        )
        async def upload_attachment_to_card(
            ctx: Context[ServerSession, None],
            organization_id: PipefyId,
            card_id: PipefyId,
            field_id: PipefyId,
            file_path: str | None = None,
            file_url: str | None = None,
            file_name: str | None = None,
            content_type: str | None = None,
        ) -> dict[str, Any]:
            """Upload one file to a card attachment field (presigned URL, S3 PUT, then updateCardField).

            Handles one file per call. To attach multiple files, call this tool once per file.

            Provide exactly one source: ``file_path`` (a local path the MCP
            server reads; local profile only) or ``file_url`` (a URL the server
            downloads under an SSRF guard and 100 MiB cap; works on any profile).
            On the hosted server ``file_path`` is rejected — pass ``file_url``.
            ``~`` is expanded in ``file_path``. When ``file_name`` is omitted it
            defaults to the source basename; if ``content_type`` is omitted it is
            inferred from the file name.

            Args:
                organization_id: Pipefy organization id. Use ``get_organization`` or ``get_pipe`` to find it.
                card_id: Target card id.
                field_id: Attachment field slug (e.g. "document_upload"), not the uuid.
                file_path: Local filesystem path. Supports ``~`` expansion. Local profile only.
                file_url: HTTPS URL to download from (http only if the deployment enables insecure URLs); max 100 MiB. Required on the hosted server.
                file_name: File name including extension. Optional; defaults to the source basename.
                content_type: Optional MIME type; sent with the S3 upload and presigned request.
            """
            client = get_pipefy_client(ctx)
            try:
                data = UploadAttachmentToCardInput(
                    organization_id=organization_id,
                    card_id=card_id,
                    field_id=field_id,
                    file_name=file_name,
                    file_path=file_path,
                    file_url=file_url,
                    content_type=content_type,
                )
            except ValidationError as exc:
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc),
                    step="validation",
                )

            if data.file_path and is_remote_profile(ctx):
                return build_upload_error_payload(
                    message=_REMOTE_FILE_PATH_REJECTION,
                    step="validation",
                )

            await ctx.debug(
                f"upload_attachment_to_card: field_id={data.field_id!r} "
                f"file_path={data.file_path!r} file_url={_redact_url_query(data.file_url)!r}"
            )

            try:
                attachment = _build_attachment(
                    file_path=data.file_path,
                    file_url=data.file_url,
                    file_name=data.file_name,
                    content_type=data.content_type,
                )
            except ValueError as exc:
                return build_upload_error_payload(message=str(exc), step="validation")
            target = CardTarget(card_id=data.card_id, field_id=data.field_id)

            try:
                result = await client.upload_attachment(
                    attachment,
                    organization_id=data.organization_id,
                    target=target,
                )
            except AttachmentUploadError as exc:
                await ctx.debug(
                    f"upload_attachment_to_card: pipeline failed at step={exc.step} {exc!r}"
                )
                return _upload_error_envelope(exc)

            return _success_envelope(result, data.field_id, {"card_id": data.card_id})

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
            meta=REMOTE,
        )
        async def upload_attachment_to_table_record(
            ctx: Context[ServerSession, None],
            organization_id: PipefyId,
            table_record_id: PipefyId,
            field_id: PipefyId,
            file_path: str | None = None,
            file_url: str | None = None,
            file_name: str | None = None,
            content_type: str | None = None,
        ) -> dict[str, Any]:
            """Upload one file to a table record attachment field (presigned URL, S3 PUT, setTableRecordFieldValue).

            Handles one file per call. To attach multiple files, call this tool once per file.

            Provide exactly one source: ``file_path`` (a local path the MCP
            server reads; local profile only) or ``file_url`` (a URL the server
            downloads under an SSRF guard and 100 MiB cap; works on any profile).
            On the hosted server ``file_path`` is rejected — pass ``file_url``.
            ``~`` is expanded in ``file_path``. When ``file_name`` is omitted it
            defaults to the source basename; if ``content_type`` is omitted it is
            inferred from the file name.

            Args:
                organization_id: Pipefy organization id. Use ``get_organization`` or ``get_pipe`` to find it.
                table_record_id: Database table record id.
                field_id: Attachment field slug on the table record (e.g. "document_upload"), not the uuid.
                file_path: Local filesystem path. Supports ``~`` expansion. Local profile only.
                file_url: HTTPS URL to download from (http only if the deployment enables insecure URLs); max 100 MiB. Required on the hosted server.
                file_name: File name including extension. Optional; defaults to the source basename.
                content_type: Optional MIME type for storage.
            """
            client = get_pipefy_client(ctx)
            try:
                data = UploadAttachmentToTableRecordInput(
                    organization_id=organization_id,
                    table_record_id=table_record_id,
                    field_id=field_id,
                    file_name=file_name,
                    file_path=file_path,
                    file_url=file_url,
                    content_type=content_type,
                )
            except ValidationError as exc:
                return build_upload_error_payload(
                    message=map_upload_error_to_message(exc),
                    step="validation",
                )

            if data.file_path and is_remote_profile(ctx):
                return build_upload_error_payload(
                    message=_REMOTE_FILE_PATH_REJECTION,
                    step="validation",
                )

            await ctx.debug(
                f"upload_attachment_to_table_record: field_id={data.field_id!r} "
                f"file_path={data.file_path!r} file_url={_redact_url_query(data.file_url)!r}"
            )

            try:
                attachment = _build_attachment(
                    file_path=data.file_path,
                    file_url=data.file_url,
                    file_name=data.file_name,
                    content_type=data.content_type,
                )
            except ValueError as exc:
                return build_upload_error_payload(message=str(exc), step="validation")
            target = TableRecordTarget(
                table_record_id=data.table_record_id, field_id=data.field_id
            )

            try:
                result = await client.upload_attachment(
                    attachment,
                    organization_id=data.organization_id,
                    target=target,
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
