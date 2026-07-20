"""Unit tests for attachment_tool_helpers."""

import pytest
from gql.transport.exceptions import TransportQueryError
from pipefy_sdk.models.attachment import UploadAttachmentToCardInput
from pydantic import ValidationError

from pipefy_mcp.core.tool_error_envelope import tool_error
from pipefy_mcp.tools.attachment_tool_helpers import (
    build_upload_error_payload,
    build_upload_success_payload,
    format_s3_upload_failure,
    map_upload_error_to_message,
)


@pytest.mark.unit
def test_build_upload_success_payload_card():
    out = build_upload_success_payload(
        download_url="https://app.pipefy.com/storage/v1/signed/x",
        file_name="doc.pdf",
        content_type="application/pdf",
        file_size=12,
        field_id="f1",
        card_id=99,
    )
    assert out["success"] is True
    assert out["download_url"] == "https://app.pipefy.com/storage/v1/signed/x"
    assert out["file_name"] == "doc.pdf"
    assert out["content_type"] == "application/pdf"
    assert out["file_size"] == 12
    assert out["field_id"] == "f1"
    assert out["card_id"] == 99
    assert "table_record_id" not in out


@pytest.mark.unit
def test_build_upload_success_payload_table():
    out = build_upload_success_payload(
        download_url=None,
        file_name="a.csv",
        content_type="text/csv",
        file_size=3,
        field_id="tf",
        table_record_id="401",
    )
    assert out["success"] is True
    assert out["download_url"] is None
    assert out["table_record_id"] == "401"
    assert "card_id" not in out


@pytest.mark.unit
def test_build_upload_error_payload_shape():
    out = build_upload_error_payload(message="failed", step="s3_upload")
    err = tool_error("failed")
    err["step"] = "s3_upload"
    assert out == err


@pytest.mark.unit
def test_format_s3_upload_failure_with_snippet():
    msg = format_s3_upload_failure(
        {"status_code": 403, "body_snippet": "<Error>Access</Error>"}
    )
    assert "403" in msg
    assert "Access" in msg


@pytest.mark.unit
def test_format_s3_upload_failure_without_snippet():
    msg = format_s3_upload_failure({"status_code": 500})
    assert "500" in msg


@pytest.mark.unit
def test_format_s3_upload_failure_expired_token_hint():
    msg = format_s3_upload_failure(
        {
            "status_code": 403,
            "body_snippet": "<Code>AccessDenied</Code><Message>Request has expired</Message>",
        }
    )
    assert "403" in msg
    assert "expired" in msg.lower()


@pytest.mark.unit
def test_format_s3_upload_failure_signature_mismatch_hint():
    msg = format_s3_upload_failure(
        {"status_code": 403, "body_snippet": "<Code>SignatureDoesNotMatch</Code>"}
    )
    assert "403" in msg
    assert "signed" in msg.lower() or "SignatureDoesNotMatch" in msg


@pytest.mark.unit
def test_map_upload_error_validation_error():
    """Missing required file_path surfaces a per-field validation message."""
    with pytest.raises(ValidationError) as exc_info:
        UploadAttachmentToCardInput(
            organization_id="1",
            card_id=1,
            field_id="f",
            file_name="x",
        )
    text = map_upload_error_to_message(exc_info.value)
    assert "file_path" in text


@pytest.mark.unit
def test_map_upload_error_transport_query():
    exc = TransportQueryError("q", errors=[{"message": "not allowed"}])
    text = map_upload_error_to_message(exc)
    assert "not allowed" in text


@pytest.mark.unit
def test_map_upload_error_value_error():
    text = map_upload_error_to_message(ValueError("bad path"))
    assert text == "bad path"


@pytest.mark.unit
def test_map_upload_error_generic():
    text = map_upload_error_to_message(RuntimeError("boom"))
    assert "boom" in text
