"""Live attachment upload flows (real Pipefy + S3).

Skips when ``PIPEFY_*`` OAuth is missing or when optional org/card/record env
IDs are unset. Use a disposable sandbox card/record and attachment fields.

Run card + table end-to-end (requires all IDs for each test):
    uv run pytest tests/tools/test_attachment_tools_live.py -m integration -v
"""

from __future__ import annotations

import os
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from _shared.live_settings import live_resolved_auth, require_live_creds
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import PipefyClient

from pipefy_mcp.server import build_pipefy_mcp_server
from pipefy_mcp.settings import get_settings
from pipefy_mcp.tools.attachment_tools import AttachmentTools
from tools.conftest import build_tool_test_server

mcp_server = build_pipefy_mcp_server()


def _live_pipefy_client() -> PipefyClient:
    """PipefyClient wired with auth via the production precedence chain."""
    return PipefyClient(settings=get_settings().pipefy, auth=live_resolved_auth())


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
def live_pipefy_client():
    require_live_creds()
    return _live_pipefy_client()


@pytest.fixture
def live_attachment_mcp(live_pipefy_client):
    return build_tool_test_server(
        "Attachment tools live", AttachmentTools.register, live_pipefy_client
    )


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_upload_attachment_to_card_end_to_end(
    live_attachment_mcp,
    extract_payload,
    tmp_path: Path,
):
    """Full MCP flow: presigned URL, S3 PUT, updateCardField, read-back on card."""
    require_live_creds()
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
    file_path = tmp_path / file_name
    file_path.write_bytes(body)

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
                "file_path": str(file_path),
                "content_type": "text/plain",
            },
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload.get("success") is True
    assert payload.get("file_name") == file_name
    assert payload.get("field_id") == field_id
    assert payload.get("card_id") == card_id

    client = _live_pipefy_client()
    data = await client.get_card(card_id, include_fields=True)
    card = data.get("card") or {}
    value = _find_named_field_value(card.get("fields"), field_id)
    _assert_field_shows_upload(value, file_name)


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_upload_attachment_to_table_record_end_to_end(
    live_attachment_mcp,
    extract_payload,
    tmp_path: Path,
):
    """Full MCP path for table records: setTableRecordFieldValue + read-back."""
    require_live_creds()
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
    file_path = tmp_path / file_name
    file_path.write_bytes(body)

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
                "file_path": str(file_path),
                "content_type": "text/plain",
            },
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload.get("success") is True
    assert payload.get("table_record_id") == record_id

    client = _live_pipefy_client()
    data = await client.get_table_record(record_id)
    rec = data.get("table_record") or {}
    value = _find_named_field_value(rec.get("record_fields"), field_id)
    _assert_field_shows_upload(value, file_name)


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_pipeclaw_mcp_upload_attachment_to_card(
    extract_payload, tmp_path: Path
):
    """Registers AttachmentTools via the production app (ToolRegistry wiring)."""
    require_live_creds()
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
    file_path = tmp_path / file_name
    file_path.write_bytes(body)

    with patch("pipefy_mcp.settings.get_settings", get_settings):
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
                    "file_path": str(file_path),
                },
            )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload.get("success") is True
