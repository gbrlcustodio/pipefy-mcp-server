"""Pydantic models for attachment upload input validation."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipefy_sdk.models.validators import NonBlankStr, PipefyId

APPLICATION_OCTET_STREAM = "application/octet-stream"

# Pipefy's direct-upload size policy is not documented; failing fast at 100 MiB
# before issuing a presigned URL avoids a confusing S3-side rejection for very
# large payloads. Applies to both MCP and CLI surfaces.
MAX_ATTACHMENT_SIZE_BYTES = 100 * 1024 * 1024


def assert_attachment_size_within_cap(size: int, source: str) -> None:
    """Raise :class:`ValueError` if ``size`` exceeds :data:`MAX_ATTACHMENT_SIZE_BYTES`.

    Both attachment surfaces (MCP ``file_path``, CLI ``--file``) gate on this
    cap before issuing a presigned URL. The helper centralizes the message so
    the callers stay aligned.

    Args:
        size: Resolved byte count (e.g. ``Path.stat().st_size``).
        source: Short label for the error message, typically the file path.
    """
    if size > MAX_ATTACHMENT_SIZE_BYTES:
        cap_mib = MAX_ATTACHMENT_SIZE_BYTES // (1024 * 1024)
        raise ValueError(
            f"File too large: {source} is {size} bytes, exceeding the "
            f"{cap_mib} MiB cap."
        )


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


class UploadAttachmentToCardInput(BaseModel):
    """Validated input for uploading an attachment to a card field."""

    model_config = ConfigDict(populate_by_name=True)

    organization_id: PipefyId
    card_id: PipefyId
    field_id: PipefyId
    file_path: NonBlankStr
    file_name: str | None = None
    content_type: str | None = None


class UploadAttachmentToTableRecordInput(BaseModel):
    """Validated input for uploading an attachment to a table record field."""

    model_config = ConfigDict(populate_by_name=True)

    organization_id: PipefyId
    table_record_id: PipefyId
    field_id: PipefyId
    file_path: NonBlankStr
    file_name: str | None = None
    content_type: str | None = None
