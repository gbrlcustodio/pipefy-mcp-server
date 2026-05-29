"""Pipefy attachment domain object.

:class:`Attachment` binds a local file (read into bytes via
:class:`pipefy_infra.filesystem.LocalFile`) to a target Pipefy field and runs the
upload pipeline: presigned URL → S3 PUT → field update. After a successful
upload, the attachment carries the resulting download URL, storage path, and
full :class:`pipefy_sdk.attachment_upload.AttachmentUploadResult`.

Surface-agnostic: MCP, CLI, and direct SDK users share it. Each surface owns
its own input validation and error envelope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipefy_infra.filesystem import LocalFile

from pipefy_sdk.attachment_upload import AttachmentUploadResult
from pipefy_sdk.models.attachment import infer_content_type

if TYPE_CHECKING:
    from pipefy_sdk.client import PipefyClient


__all__ = ["Attachment"]


class Attachment:
    """An attachment bound to a target Pipefy field, ready to upload.

    Construction is a pure setup step. Reading the file is the caller's job:
    call :meth:`LocalFile.read` on the underlying file before invoking
    :meth:`upload_to_card_field` or :meth:`upload_to_table_record_field`.

    After a successful upload, :attr:`result` holds the raw response and
    :attr:`download_url` / :attr:`storage_path` expose its fields. Reading
    those properties before an upload raises :class:`RuntimeError`; use
    ``attachment.result is not None`` to test for upload completion.

    Name resolution (lazy, at attribute access): explicit ``name`` if given,
    otherwise the file's basename.

    Content-type resolution (lazy, at attribute access): explicit
    ``content_type`` if given, otherwise inferred from :attr:`name`.
    """

    def __init__(
        self,
        file: LocalFile,
        *,
        name: str | None = None,
        content_type: str | None = None,
    ):
        self._file = file
        self._explicit_name = (name or "").strip() or None
        self._explicit_content_type = content_type
        self._result: AttachmentUploadResult | None = None

    @property
    def file(self) -> LocalFile:
        """The underlying file source."""
        return self._file

    @property
    def name(self) -> str:
        """Explicit name if provided, else the file's basename.

        Requires that :meth:`LocalFile.read` has been called on the underlying
        file when no explicit name was supplied.
        """
        return self._explicit_name or self._file.name

    @property
    def content_type(self) -> str:
        """Explicit content type if provided, else inferred from :attr:`name`."""
        return self._explicit_content_type or infer_content_type(self.name)

    @property
    def result(self) -> AttachmentUploadResult | None:
        """Full upload result; ``None`` before a successful upload."""
        return self._result

    @property
    def download_url(self) -> str | None:
        """Signed download URL Pipefy returned. May be ``None`` if the server
        omitted it. Raises :class:`RuntimeError` if no upload has run.
        """
        if self._result is None:
            raise RuntimeError(
                "Attachment.download_url is unavailable until upload completes."
            )
        return self._result["download_url"]

    @property
    def storage_path(self) -> str | None:
        """Storage path Pipefy assigned. Raises :class:`RuntimeError` if no
        upload has run.
        """
        if self._result is None:
            raise RuntimeError(
                "Attachment.storage_path is unavailable until upload completes."
            )
        return self._result["storage_path"]

    async def upload_to_card_field(
        self,
        client: PipefyClient,
        *,
        organization_id: str,
        card_id: str,
        field_id: str,
    ) -> AttachmentUploadResult:
        """Run presigned URL → S3 PUT → ``updateCardField``.

        Stores the result on the attachment and returns it.

        Raises:
            AttachmentUploadError: When any pipeline step fails. ``step``
                attribute identifies which (``presigned_url``, ``s3_upload``,
                ``field_update``).
        """
        self._result = await client.upload_attachment_to_card_field(
            organization_id=organization_id,
            card_id=card_id,
            field_id=field_id,
            file_name=self.name,
            file_bytes=self._file.bytes,
            content_type=self._explicit_content_type,
        )
        return self._result

    async def upload_to_table_record_field(
        self,
        client: PipefyClient,
        *,
        organization_id: str,
        table_record_id: str,
        field_id: str,
    ) -> AttachmentUploadResult:
        """Run presigned URL → S3 PUT → ``setTableRecordFieldValue``.

        Stores the result on the attachment and returns it.

        Raises:
            AttachmentUploadError: When any pipeline step fails.
        """
        self._result = await client.upload_attachment_to_table_record_field(
            organization_id=organization_id,
            table_record_id=table_record_id,
            field_id=field_id,
            file_name=self.name,
            file_bytes=self._file.bytes,
            content_type=self._explicit_content_type,
        )
        return self._result
