"""Attachment domain types, target value objects, and upload result/error.

This module owns the attachment side of the SDK's public surface:

- :class:`Attachment`: domain entity binding one file source — a local file
  path or a remote URL — to optional explicit name and content type. Pure
  setup; the service reads the file or downloads the URL at upload time.
- :class:`CardTarget` / :class:`TableRecordTarget`: bundled identifiers for
  the two upload destinations Pipefy exposes today.
- :class:`AttachmentUploadResult`: successful upload payload returned by
  the service.
- :class:`AttachmentUploadError`: single failure type carrying a ``step``
  attribute for surface-side envelope mapping.
- :class:`UploadAttachmentToCardInput` / :class:`UploadAttachmentToTableRecordInput`:
  Pydantic input DTOs for the MCP/CLI surfaces.
- :func:`infer_content_type`: utility used by both the domain object and
  the service.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import TypedDict

from pipefy_sdk.models.validators import PipefyId

APPLICATION_OCTET_STREAM = "application/octet-stream"

# Cap both sources at 100 MiB client-side, failing fast before a presigned URL
# is requested rather than surfacing an opaque rejection later. Local files are
# checked via LocalFile(max_size_bytes=...); downloaded URLs via the
# UrlDownloader (Content-Length + streamed byte count).
_MAX_ATTACHMENT_SIZE_BYTES = 100 * 1024 * 1024


# ``mimetypes`` maps ``.xyz`` to ``chemical/x-xyz`` on many systems; for generic uploads
# we treat that as unknown binary content.
_MIME_FALSE_POSITIVES_FOR_UPLOAD = frozenset({"chemical/x-xyz"})

# Suffixes where :mod:`mimetypes` is inconsistent across OS images (e.g. Linux slim
# containers return ``application/octet-stream`` for ``.docx``).
_STABLE_SUFFIX_CONTENT_TYPES: dict[str, str] = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def infer_content_type(file_name: str) -> str:
    """Infer a MIME type from ``file_name`` (typically the basename or path).

    Uses :func:`mimetypes.guess_type`, with a small suffix map for types that differ
    across platforms. Returns ``application/octet-stream`` when the type is unknown or
    a known false positive for arbitrary ``.xyz`` files.

    Args:
        file_name: File name or path whose suffix is used for guessing.

    Returns:
        A MIME type string suitable for ``Content-Type``-style headers.
    """
    suffix = Path(file_name).suffix.lower()
    if suffix in _STABLE_SUFFIX_CONTENT_TYPES:
        return _STABLE_SUFFIX_CONTENT_TYPES[suffix]
    mime, _encoding = mimetypes.guess_type(file_name)
    if mime is None or mime in _MIME_FALSE_POSITIVES_FOR_UPLOAD:
        return APPLICATION_OCTET_STREAM
    return mime


class Attachment:
    """One file source bound to an attachment, with lazy name and content type.

    The source is exactly one of a local ``path`` or a remote ``url``.
    Construction is a pure setup step. The file is read (path) or downloaded
    (url) by :meth:`pipefy_sdk.PipefyClient.upload_attachment` (via the
    service); callers do not pre-read or pass bytes.

    Name resolution (at construction): explicit ``name`` if provided
    (whitespace-only treated as absent), otherwise the basename of the path or
    the URL path. Construction raises ``ValueError`` if that leaves the name
    empty (e.g. a URL like ``.../download?id=1`` with no basename) — callers
    must then pass ``name`` explicitly, so every ``Attachment`` carries a
    non-empty name before the service requests a presigned URL.

    Content-type resolution: explicit ``content_type`` if provided, otherwise
    inferred from the resolved name via :func:`infer_content_type`.
    """

    def __init__(
        self,
        *,
        path: Path | None = None,
        url: str | None = None,
        name: str | None = None,
        content_type: str | None = None,
    ) -> None:
        cleaned_url = (url or "").strip() or None
        if (path is None) == (cleaned_url is None):
            raise ValueError("Attachment requires exactly one of path or url.")
        self._path = path
        self._url = cleaned_url
        self._explicit_content_type = content_type

        explicit = (name or "").strip()
        if explicit:
            resolved = explicit
        elif path is not None:
            resolved = path.name
        else:
            resolved = Path(urlparse(cleaned_url or "").path).name
        if not resolved:
            raise ValueError(
                "Attachment has no file name: the source has no basename "
                "(e.g. a URL like '.../download?id=1'), so pass name explicitly."
            )
        self._name = resolved

    @property
    def path(self) -> Path | None:
        """The local filesystem path, or None when the source is a URL."""
        return self._path

    @property
    def url(self) -> str | None:
        """The remote source URL, or None when the source is a local path."""
        return self._url

    @property
    def name(self) -> str:
        """The resolved, non-empty file name (explicit, or the source basename)."""
        return self._name

    @property
    def content_type(self) -> str:
        """Explicit content type if provided, else inferred from :attr:`name`."""
        return self._explicit_content_type or infer_content_type(self.name)


@dataclass(frozen=True, slots=True)
class CardTarget:
    """Card attachment field destination."""

    card_id: str
    field_id: str


@dataclass(frozen=True, slots=True)
class TableRecordTarget:
    """Table record attachment field destination."""

    table_record_id: str
    field_id: str


AttachmentTarget = CardTarget | TableRecordTarget


AttachmentUploadStep = Literal[
    "file_read",
    "download",
    "presigned_url",
    "s3_upload",
    "field_update",
]


class AttachmentUploadError(Exception):
    """Raised on attachment upload pipeline failure.

    The ``step`` attribute identifies which stage failed so surfaces can map
    it to a step-aware error envelope (MCP) or typer message (CLI) without
    parsing strings.
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
    """Successful upload outcome: everything callers need to render their response."""

    file_name: str
    content_type: str
    file_size: int
    field_id: str
    storage_path: str
    download_url: str | None


def _resolve_one_source(
    file_path: str | None, file_url: str | None
) -> tuple[str | None, str | None]:
    """Normalize blank sources to None and require exactly one to remain.

    Blank counts as absent, so downstream code can use plain truthiness and
    never sees a whitespace path masquerading as a source alongside a URL.
    """
    path = (file_path or "").strip() or None
    url = (file_url or "").strip() or None
    if (path is None) == (url is None):
        raise ValueError("Provide exactly one of file_path or file_url.")
    return path, url


class UploadAttachmentToCardInput(BaseModel):
    """Validated input for uploading an attachment to a card field."""

    model_config = ConfigDict(populate_by_name=True)

    organization_id: PipefyId
    card_id: PipefyId
    field_id: PipefyId
    file_path: str | None = None
    file_url: str | None = None
    file_name: str | None = None
    content_type: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> UploadAttachmentToCardInput:
        self.file_path, self.file_url = _resolve_one_source(
            self.file_path, self.file_url
        )
        return self


class UploadAttachmentToTableRecordInput(BaseModel):
    """Validated input for uploading an attachment to a table record field."""

    model_config = ConfigDict(populate_by_name=True)

    organization_id: PipefyId
    table_record_id: PipefyId
    field_id: PipefyId
    file_path: str | None = None
    file_url: str | None = None
    file_name: str | None = None
    content_type: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> UploadAttachmentToTableRecordInput:
        self.file_path, self.file_url = _resolve_one_source(
            self.file_path, self.file_url
        )
        return self
