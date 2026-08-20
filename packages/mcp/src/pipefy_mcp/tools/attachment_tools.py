"""MCP tools to upload attachments to card or table record fields."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp.server.mcpserver import Context, MCPServer
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
    build_presigned_success_payload,
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
    def register(mcp: MCPServer) -> None:
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
            ctx: Context,
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
            ctx: Context,
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

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
            meta=REMOTE,
        )
        async def create_attachment_presigned_url(
            ctx: Context,
            organization_id: PipefyId,
            file_name: str,
            content_type: str | None = None,
            content_length: int | None = None,
        ) -> dict[str, Any]:
            """Mint a presigned S3 upload target for an attachment — no bytes uploaded.

            Use this to attach a file the MCP server itself cannot read: a local
            file on the hosted server, or bytes too large to inline. The client
            does the upload; three steps:

            1. Call this to get ``upload_url`` (the S3 PUT url) and ``storage_path``
               (the object key to store).
            2. From an environment that can reach the upload host, HTTP ``PUT`` the
               file bytes to ``upload_url`` within ``expires_in_seconds`` (send
               ``Content-Type`` / ``Content-Length`` matching what you passed here).
            3. Set the attachment field to ``[storage_path]`` via ``update_card_field``
               or ``set_table_record_field_value``. Store ``storage_path``, never the url.

            Args:
                organization_id: Pipefy organization id (numeric or uuid). Use ``get_organization`` or ``get_pipe`` to find it.
                file_name: File name including extension; names the stored object.
                content_type: Optional MIME type to sign into the upload.
                content_length: Optional exact byte length to sign into the upload.
            """
            client = get_pipefy_client(ctx)
            if not file_name or not file_name.strip():
                return build_upload_error_payload(
                    message="file_name must be a non-empty string.",
                    step="validation",
                )
            await ctx.debug(
                f"create_attachment_presigned_url: org={organization_id!r} file_name={file_name!r}"
            )
            try:
                target = await client.create_attachment_presigned_url(
                    organization_id=organization_id,
                    file_name=file_name.strip(),
                    content_type=content_type,
                    content_length=content_length,
                )
            except AttachmentUploadError as exc:
                return _upload_error_envelope(exc)
            return build_presigned_success_payload(target)
