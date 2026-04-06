"""Payload builders and error strings for attachment upload MCP tools."""

from __future__ import annotations

import binascii
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from pipefy_mcp.tools.graphql_error_helpers import extract_error_strings

UploadFlowStep = Literal[
    "validation",
    "file_download",
    "presigned_url",
    "s3_upload",
    "field_update",
]


def build_upload_success_payload(
    *,
    download_url: str | None,
    file_name: str,
    content_type: str,
    file_size: int,
    field_id: str,
    card_id: int | None = None,
    table_record_id: str | None = None,
) -> dict[str, Any]:
    """Structured success payload (FR-8).

    Args:
        download_url: Permanent/signed download URL from Pipefy (may be None if API omits it).
        file_name: File name used for the upload.
        content_type: MIME type sent to storage.
        file_size: Uploaded size in bytes.
        field_id: Updated attachment field id.
        card_id: Target card id (card uploads).
        table_record_id: Target table record id (table uploads).
    """
    payload: dict[str, Any] = {
        "success": True,
        "download_url": download_url,
        "file_name": file_name,
        "content_type": content_type,
        "file_size": file_size,
        "field_id": field_id,
    }
    if card_id is not None:
        payload["card_id"] = card_id
    if table_record_id is not None:
        payload["table_record_id"] = table_record_id
    return payload


def build_upload_error_payload(
    *,
    message: str,
    step: UploadFlowStep,
) -> dict[str, Any]:
    """Structured failure payload for the upload flow.

    Args:
        message: Actionable reason for the caller.
        step: Failed stage (``file_download``, ``presigned_url``, ``s3_upload``, ``field_update``).
    """
    return {
        "success": False,
        "error": message,
        "message": message,
        "step": step,
    }


def format_s3_upload_failure(upload_result: dict[str, Any]) -> str:
    """Build an agent-facing message from ``AttachmentService.upload_file_to_s3`` output.

    Args:
        upload_result: Dict containing at least ``status_code``; may include ``body_snippet``.
    """
    code = upload_result.get("status_code")
    snippet = upload_result.get("body_snippet")
    base = f"S3 upload failed with HTTP status {code}."
    if isinstance(snippet, str) and snippet.strip():
        body = snippet.strip()[:300]
        hint = ""
        if "ExpiredToken" in snippet or "request has expired" in snippet.lower():
            hint = (
                " The presigned URL may have expired; call the upload tool again "
                "to obtain a fresh URL."
            )
        elif "SignatureDoesNotMatch" in snippet:
            hint = (
                " The request body or headers may not match what was signed "
                "(check content length and Content-Type)."
            )
        if hint:
            return f"{base} Response snippet: {body}.{hint}"
        return f"{base} Response snippet: {body}"
    return f"{base} Check content type, size, and presigned URL validity."


def map_upload_error_to_message(exc: BaseException, step: UploadFlowStep) -> str:
    """Map an exception to a short, actionable message (FR-9).

    Args:
        exc: Failure from transport, GraphQL, or validation.
        step: Current flow step where the error was observed (for context only).
    """
    if isinstance(exc, ValidationError):
        parts: list[str] = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", ()))
            msg = err.get("msg", "invalid")
            if loc:
                parts.append(f"{loc}: {msg}")
            else:
                parts.append(str(msg))
        return "; ".join(parts) if parts else "Invalid input."
    if isinstance(exc, binascii.Error):
        return "Invalid file_content_base64: could not decode base64 data."
    if isinstance(exc, httpx.HTTPStatusError):
        if step == "file_download":
            return (
                f"Could not download file_url (HTTP {exc.response.status_code}). "
                "Verify the URL is public or reachable from this server."
            )
        return (
            f"HTTP error ({exc.response.status_code}) during request. "
            "Retry or check network and URL."
        )
    if isinstance(exc, httpx.RequestError):
        if step == "file_download":
            return (
                f"Network error while downloading file_url: {exc}. "
                "Check connectivity and URL validity."
            )
        return f"Network error: {exc}"
    if isinstance(exc, ValueError):
        return str(exc)
    msgs = extract_error_strings(exc)
    if msgs:
        return "; ".join(dict.fromkeys(msgs))
    return f"{type(exc).__name__}: {exc}".strip()
