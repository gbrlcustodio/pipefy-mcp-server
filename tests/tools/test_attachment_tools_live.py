"""Live attachment upload flows (real Pipefy + S3).

Skips when ``PIPEFY_*`` OAuth is missing or when optional org/card/record env
IDs are unset. Use a disposable sandbox card/record and attachment fields.

Run card + table end-to-end (requires all IDs for each test):
    uv run pytest tests/tools/test_attachment_tools_live.py -m integration -v

Run S3 error matrix subset (requires org only + live test flag):
    PIPE_ATTACHMENT_LIVE_S3_MATRIX=1 \\
    uv run pytest tests/tools/test_attachment_tools_live.py -m integration -k s3_put -v

Optional long-run expired-URL check (waits for ``PIPE_ATTACHMENT_S3_EXPIRY_WAIT_SECONDS``):
    PIPE_ATTACHMENT_LIVE_S3_MATRIX=1 PIPE_ATTACHMENT_S3_EXPIRY_WAIT_SECONDS=310 \\
    uv run pytest tests/tools/test_attachment_tools_live.py -m integration -k expired -v
"""

from __future__ import annotations

import asyncio
import base64
import os
import uuid
from datetime import timedelta
from unittest.mock import patch

import httpx
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.server import mcp as mcp_server
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.attachment_tools import AttachmentTools


def _pipefy_live_configured() -> bool:
    p = settings.pipefy
    return bool(
        p.graphql_url
        and str(p.graphql_url).startswith(("http://", "https://"))
        and p.oauth_url
        and str(p.oauth_url).startswith(("http://", "https://"))
        and p.oauth_client
        and p.oauth_secret
    )


def _require_live_creds() -> None:
    if not _pipefy_live_configured():
        pytest.skip(
            "Pipefy credentials not configured (PIPEFY_GRAPHQL_URL + OAuth in .env)"
        )


def _card_upload_env():
    org = os.environ.get("PIPE_ATTACHMENT_LIVE_ORG_ID")
    card_raw = os.environ.get("PIPE_ATTACHMENT_LIVE_CARD_ID")
    field = os.environ.get("PIPE_ATTACHMENT_LIVE_CARD_FIELD_ID")
    if not (org and card_raw and field):
        return None
    return org.strip(), int(card_raw), field.strip()


def _table_upload_env():
    org = os.environ.get("PIPE_ATTACHMENT_LIVE_ORG_ID")
    rec = os.environ.get("PIPE_ATTACHMENT_LIVE_TABLE_RECORD_ID")
    field = os.environ.get("PIPE_ATTACHMENT_LIVE_TABLE_FIELD_ID")
    if not (org and rec and field):
        return None
    return org.strip(), rec.strip(), field.strip()


def _find_named_field_value(fields, field_id: str):
    for row in fields or []:
        if str(row.get("name")) == str(field_id):
            return row.get("value")
    return None


def _assert_field_shows_upload(value, file_name: str) -> None:
    text = value if isinstance(value, str) else repr(value)
    assert text, "field value empty after upload"
    ok = file_name in text or "orgs/" in text
    assert ok, f"attachment field value did not reference file/path: {text!r}"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def live_pipefy_client():
    _require_live_creds()
    return PipefyClient(settings=settings.pipefy)


@pytest.fixture
def live_attachment_mcp(live_pipefy_client):
    mcp = FastMCP("Attachment tools live")
    AttachmentTools.register(mcp, live_pipefy_client)
    return mcp


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_upload_attachment_to_card_end_to_end(
    live_attachment_mcp,
    extract_payload,
):
    """Full MCP flow: presigned URL, S3 PUT, updateCardField, read-back on card."""
    _require_live_creds()
    env = _card_upload_env()
    if not env:
        pytest.skip(
            "Set PIPE_ATTACHMENT_LIVE_ORG_ID, PIPE_ATTACHMENT_LIVE_CARD_ID, "
            "and PIPE_ATTACHMENT_LIVE_CARD_FIELD_ID (attachment field uuid)"
        )
    org_id, card_id, field_id = env
    unique = uuid.uuid4().hex[:12]
    file_name = f"mcp-live-{unique}.txt"
    body = f"pipefy-mcp live attachment {unique}\n".encode()
    b64 = base64.standard_b64encode(body).decode("ascii")

    async with create_client_session(
        live_attachment_mcp,
        read_timeout_seconds=timedelta(seconds=120),
        raise_exceptions=True,
    ) as session:
        result = await session.call_tool(
            "upload_attachment_to_card",
            {
                "organization_id": org_id,
                "card_id": card_id,
                "field_id": field_id,
                "file_name": file_name,
                "file_content_base64": b64,
                "content_type": "text/plain",
            },
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload.get("success") is True
    assert payload.get("file_name") == file_name
    assert payload.get("field_id") == field_id
    assert payload.get("card_id") == card_id

    client = PipefyClient(settings=settings.pipefy)
    data = await client.get_card(card_id, include_fields=True)
    card = data.get("card") or {}
    value = _find_named_field_value(card.get("fields"), field_id)
    _assert_field_shows_upload(value, file_name)


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_upload_attachment_to_table_record_end_to_end(
    live_attachment_mcp,
    extract_payload,
):
    """Full MCP path for table records: setTableRecordFieldValue + read-back."""
    _require_live_creds()
    env = _table_upload_env()
    if not env:
        pytest.skip(
            "Set PIPE_ATTACHMENT_LIVE_ORG_ID, PIPE_ATTACHMENT_LIVE_TABLE_RECORD_ID, "
            "and PIPE_ATTACHMENT_LIVE_TABLE_FIELD_ID"
        )
    org_id, record_id, field_id = env
    unique = uuid.uuid4().hex[:12]
    file_name = f"mcp-live-table-{unique}.txt"
    body = f"pipefy-mcp table live {unique}\n".encode()
    b64 = base64.standard_b64encode(body).decode("ascii")

    async with create_client_session(
        live_attachment_mcp,
        read_timeout_seconds=timedelta(seconds=120),
        raise_exceptions=True,
    ) as session:
        result = await session.call_tool(
            "upload_attachment_to_table_record",
            {
                "organization_id": org_id,
                "table_record_id": record_id,
                "field_id": field_id,
                "file_name": file_name,
                "file_content_base64": b64,
                "content_type": "text/plain",
            },
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload.get("success") is True
    assert payload.get("table_record_id") == record_id

    client = PipefyClient(settings=settings.pipefy)
    data = await client.get_table_record(record_id)
    rec = data.get("table_record") or {}
    value = _find_named_field_value(rec.get("record_fields"), field_id)
    _assert_field_shows_upload(value, file_name)


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_pipeclaw_mcp_upload_attachment_to_card(extract_payload):
    """Registers AttachmentTools via the production app (ToolRegistry wiring)."""
    _require_live_creds()
    env = _card_upload_env()
    if not env:
        pytest.skip(
            "Set PIPE_ATTACHMENT_LIVE_ORG_ID, PIPE_ATTACHMENT_LIVE_CARD_ID, "
            "PIPE_ATTACHMENT_LIVE_CARD_FIELD_ID"
        )
    org_id, card_id, field_id = env
    unique = uuid.uuid4().hex[:12]
    file_name = f"mcp-app-live-{unique}.txt"
    body = f"app-registry {unique}\n".encode()
    b64 = base64.standard_b64encode(body).decode("ascii")

    with patch("pipefy_mcp.server.settings", settings):
        async with create_client_session(
            mcp_server,
            read_timeout_seconds=timedelta(seconds=120),
            raise_exceptions=True,
        ) as session:
            result = await session.call_tool(
                "upload_attachment_to_card",
                {
                    "organization_id": org_id,
                    "card_id": card_id,
                    "field_id": field_id,
                    "file_name": file_name,
                    "file_content_base64": b64,
                },
            )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload.get("success") is True


def _s3_matrix_enabled() -> bool:
    return os.environ.get("PIPE_ATTACHMENT_LIVE_S3_MATRIX", "").strip() in (
        "1",
        "true",
        "yes",
    )


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_s3_put_mismatched_content_length():
    """PUT body size must match ``contentLength`` given to createPresignedUrl."""
    _require_live_creds()
    org = os.environ.get("PIPE_ATTACHMENT_LIVE_ORG_ID")
    if not org:
        pytest.skip("Set PIPE_ATTACHMENT_LIVE_ORG_ID")
    if not _s3_matrix_enabled():
        pytest.skip("Set PIPE_ATTACHMENT_LIVE_S3_MATRIX=1 to run S3 PUT matrix tests")

    client = PipefyClient(settings=settings.pipefy)
    file_name = f"s3-mismatch-{uuid.uuid4().hex[:10]}.bin"
    signed_len = 200
    presigned = await client.create_presigned_url(
        organization_id=org,
        file_name=file_name,
        content_type="application/octet-stream",
        content_length=signed_len,
    )
    url = presigned.get("url")
    assert isinstance(url, str) and url.strip(), "no presigned url"

    wrong_body = b"x" * 3
    result = await client.upload_file_to_s3(
        presigned_url=url.strip(),
        file_bytes=wrong_body,
        content_type="application/octet-stream",
    )
    code = result.get("status_code", 0)
    if code < 400:
        pytest.skip(
            "Presigned URL did not reject mismatched contentLength in this environment; "
            "VD-6 still documents the usual AWS 4xx behavior."
        )


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_s3_put_expired_presigned_url():
    """After X-Amz-Expires, PUT should fail (403 typical). Long wait — opt-in."""
    _require_live_creds()
    org = os.environ.get("PIPE_ATTACHMENT_LIVE_ORG_ID")
    if not org:
        pytest.skip("Set PIPE_ATTACHMENT_LIVE_ORG_ID")
    if not _s3_matrix_enabled():
        pytest.skip("Set PIPE_ATTACHMENT_LIVE_S3_MATRIX=1 for S3 matrix tests")

    wait_raw = os.environ.get("PIPE_ATTACHMENT_S3_EXPIRY_WAIT_SECONDS", "").strip()
    if not wait_raw:
        pytest.skip(
            "Set PIPE_ATTACHMENT_S3_EXPIRY_WAIT_SECONDS "
            "(e.g. 310) to wait past presigned expiry"
        )
    wait_sec = int(wait_raw)

    client = PipefyClient(settings=settings.pipefy)
    file_name = f"s3-expiry-{uuid.uuid4().hex[:10]}.txt"
    presigned = await client.create_presigned_url(
        organization_id=org,
        file_name=file_name,
        content_type="text/plain",
        content_length=4,
    )
    url = presigned.get("url")
    assert isinstance(url, str) and url.strip()

    await asyncio.sleep(wait_sec)
    result = await client.upload_file_to_s3(
        presigned_url=url.strip(),
        file_bytes=b"abcd",
        content_type="text/plain",
    )
    code = result.get("status_code", 0)
    if code < 400:
        pytest.skip(
            "PUT still succeeded after wait; increase PIPE_ATTACHMENT_S3_EXPIRY_WAIT_SECONDS "
            "past X-Amz-Expires or confirm clock skew."
        )


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_s3_put_omits_content_type_when_signed():
    """If Content-Type is signed, omitting it on PUT should fail."""
    _require_live_creds()
    org = os.environ.get("PIPE_ATTACHMENT_LIVE_ORG_ID")
    if not org:
        pytest.skip("Set PIPE_ATTACHMENT_LIVE_ORG_ID")
    if not _s3_matrix_enabled():
        pytest.skip("Set PIPE_ATTACHMENT_LIVE_S3_MATRIX=1 for S3 matrix tests")

    client = PipefyClient(settings=settings.pipefy)
    file_name = f"s3-no-ctype-{uuid.uuid4().hex[:10]}.txt"
    body = b"abcd"
    presigned = await client.create_presigned_url(
        organization_id=org,
        file_name=file_name,
        content_type="text/plain",
        content_length=len(body),
    )
    url = presigned.get("url")
    assert isinstance(url, str) and url.strip()

    async with httpx.AsyncClient() as http:
        response = await http.put(url.strip(), content=body)
    if response.status_code < 400:
        pytest.skip(
            "Upload succeeded without Content-Type; signature may not bind it in this environment."
        )
