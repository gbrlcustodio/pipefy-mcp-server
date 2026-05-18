"""Pydantic models for attachment upload input validation."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from pipefy_sdk.models.validators import PipefyId

APPLICATION_OCTET_STREAM = "application/octet-stream"

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


def _source_nonempty(value: str | None) -> bool:
    return bool(value and value.strip())


def _raise_unless_exactly_one_file_source(
    file_url: str | None,
    file_content_base64: str | None,
) -> None:
    """Ensure exactly one of URL or base64 payload is non-empty.

    Raises:
        ValueError: When both or neither source is provided with non-empty content.
    """
    has_url = _source_nonempty(file_url)
    has_b64 = _source_nonempty(file_content_base64)
    if has_url and has_b64:
        raise ValueError(
            "Provide exactly one of file_url or file_content_base64, not both."
        )
    if not has_url and not has_b64:
        raise ValueError(
            "Provide exactly one of file_url or file_content_base64 (non-empty)."
        )


class UploadAttachmentToCardInput(BaseModel):
    """Validated input for uploading an attachment to a card field."""

    model_config = ConfigDict(populate_by_name=True)

    organization_id: PipefyId
    card_id: PipefyId
    field_id: PipefyId
    file_name: str
    file_url: str | None = None
    file_content_base64: str | None = None
    content_type: str | None = None

    @model_validator(mode="after")
    def exactly_one_file_source(self) -> Self:
        """Require exactly one of ``file_url`` or ``file_content_base64`` with non-empty value."""
        _raise_unless_exactly_one_file_source(self.file_url, self.file_content_base64)
        return self


class UploadAttachmentToTableRecordInput(BaseModel):
    """Validated input for uploading an attachment to a table record field."""

    model_config = ConfigDict(populate_by_name=True)

    organization_id: PipefyId
    table_record_id: PipefyId
    field_id: PipefyId
    file_name: str
    file_url: str | None = None
    file_content_base64: str | None = None
    content_type: str | None = None

    @model_validator(mode="after")
    def exactly_one_file_source(self) -> Self:
        """Require exactly one of ``file_url`` or ``file_content_base64`` with non-empty value."""
        _raise_unless_exactly_one_file_source(self.file_url, self.file_content_base64)
        return self
