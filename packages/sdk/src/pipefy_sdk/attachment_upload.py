"""High-level attachment upload pipeline: presigned URL → S3 PUT → field update.

The MCP and CLI surfaces both upload file bytes to Pipefy attachment fields
through the same sequence. This module centralizes the orchestration so that
source-specific concerns (base64 decode in MCP for in-memory payloads,
``Path.read_bytes`` for files on disk) live where they belong while the core
pipeline stays in one place.

Exceptions :class:`AttachmentUploadError` carry a ``step`` attribute so surfaces
can map them to step-aware error envelopes (MCP) or typer messages (CLI).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal

from typing_extensions import TypedDict

from pipefy_sdk.models.attachment import infer_content_type

if TYPE_CHECKING:
    from pipefy_sdk.client import PipefyClient


AttachmentUploadStep = Literal[
    "presigned_url",
    "s3_upload",
    "field_update",
]


class AttachmentUploadError(Exception):
    """Raised on attachment upload pipeline failure.

    The ``step`` attribute identifies which stage failed so surfaces can keep
    their existing step-aware error envelopes without parsing strings.
    """

    def __init__(
        self,
        message: str,
        *,
        step: AttachmentUploadStep,
        body_snippet: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.step = step
        self.body_snippet = body_snippet
        self.status_code = status_code
        super().__init__(message)


class AttachmentUploadResult(TypedDict):
    """Successful upload outcome — everything callers need to render their response."""

    file_name: str
    content_type: str
    file_size: int
    field_id: str
    storage_path: str
    download_url: str | None


async def upload_attachment_to_card_field(
    client: PipefyClient,
    *,
    organization_id: str,
    card_id: str,
    field_id: str,
    file_name: str,
    file_bytes: bytes,
    content_type: str | None = None,
) -> AttachmentUploadResult:
    """Upload ``file_bytes`` to a card attachment field via the standard pipeline.

    Args:
        client: Pipefy facade.
        organization_id: Organization owning the card.
        card_id: Target card.
        field_id: Attachment field slug on the card.
        file_name: File name (used for storage and MIME inference when ``content_type`` is None).
        file_bytes: Raw file content.
        content_type: Optional MIME type; inferred from ``file_name`` when omitted.

    Raises:
        AttachmentUploadError: On any pipeline failure (see ``step``).
    """

    async def update_card_field_for_upload(path: str) -> Any:
        return await client.update_card_field(card_id, field_id, [path])

    return await _upload_pipeline(
        client,
        organization_id=organization_id,
        field_id=field_id,
        file_name=file_name,
        file_bytes=file_bytes,
        content_type=content_type,
        field_update=update_card_field_for_upload,
    )


async def upload_attachment_to_table_record_field(
    client: PipefyClient,
    *,
    organization_id: str,
    table_record_id: str,
    field_id: str,
    file_name: str,
    file_bytes: bytes,
    content_type: str | None = None,
) -> AttachmentUploadResult:
    """Upload ``file_bytes`` to a table record attachment field via the standard pipeline.

    Mirrors :func:`upload_attachment_to_card_field` but the final step calls
    ``set_table_record_field_value`` instead of ``update_card_field``.

    Raises:
        AttachmentUploadError: On any pipeline failure (see ``step``).
    """

    async def set_table_record_field_for_upload(path: str) -> Any:
        return await client.set_table_record_field_value(
            table_record_id, field_id, [path]
        )

    return await _upload_pipeline(
        client,
        organization_id=organization_id,
        field_id=field_id,
        file_name=file_name,
        file_bytes=file_bytes,
        content_type=content_type,
        field_update=set_table_record_field_for_upload,
    )


async def _upload_pipeline(
    client: PipefyClient,
    *,
    organization_id: str,
    field_id: str,
    file_name: str,
    file_bytes: bytes,
    content_type: str | None,
    field_update: Callable[[str], Awaitable[Any]],
) -> AttachmentUploadResult:
    effective_type = content_type or infer_content_type(file_name)
    content_length = len(file_bytes)

    try:
        presigned = await client.create_presigned_url(
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

    put_result = await client.upload_file_to_s3(
        upload_url.strip(),
        file_bytes,
        effective_type,
    )
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
        storage_path = client.extract_storage_path(upload_url)
    except ValueError as exc:
        raise AttachmentUploadError(str(exc), step="s3_upload") from exc

    try:
        await field_update(storage_path)
    except Exception as exc:
        raise AttachmentUploadError(
            f"Field update failed: {exc}",
            step="field_update",
        ) from exc

    return AttachmentUploadResult(
        file_name=file_name,
        content_type=effective_type,
        file_size=content_length,
        field_id=field_id,
        storage_path=storage_path,
        download_url=download_url if isinstance(download_url, str) else None,
    )


__all__ = [
    "AttachmentUploadError",
    "AttachmentUploadResult",
    "AttachmentUploadStep",
    "upload_attachment_to_card_field",
    "upload_attachment_to_table_record_field",
]
