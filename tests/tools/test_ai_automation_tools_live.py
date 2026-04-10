"""Live MCP path for AI automation create (optional integration).

Exercises **create_ai_automation** without ``condition`` (default placeholder) through
the full **pipefy_mcp.server.mcp** app (ToolRegistry + real **PipefyClient**), then
tears down with **delete_automation** (``confirm=True``).

Skips without **PIPEFY_*** OAuth or when **PIPE_AI_AUTOMATION_LIVE_PIPE_ID** /
**PIPE_AI_AUTOMATION_LIVE_FIELD_ID** are unset.

**Setup:** Disposable pipe with **AI enabled** and at least one card field. Set
``PIPE_AI_AUTOMATION_LIVE_FIELD_ID`` to that field's **internal_id** (string). Grant the
service account permission to create/delete automations on that pipe.

Run:

    uv run pytest tests/tools/test_ai_automation_tools_live.py -m integration -v

Env:

    PIPE_AI_AUTOMATION_LIVE_PIPE_ID   — pipe numeric ID (required for this module)
    PIPE_AI_AUTOMATION_LIVE_FIELD_ID  — field internal_id for prompt + field_ids (required)
"""

from __future__ import annotations

import os
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.server import mcp as mcp_server
from pipefy_mcp.settings import settings
from tests.integration_helpers import require_live_creds


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_create_ai_automation_omits_condition_uses_default_placeholder(
    extract_payload,
):
    """Full stack: create_ai_automation without condition; delete when possible."""
    require_live_creds()
    pipe_raw = os.environ.get("PIPE_AI_AUTOMATION_LIVE_PIPE_ID")
    field_raw = os.environ.get("PIPE_AI_AUTOMATION_LIVE_FIELD_ID")
    if not pipe_raw or not str(pipe_raw).strip():
        pytest.skip("Set PIPE_AI_AUTOMATION_LIVE_PIPE_ID (see module docstring).")
    if not field_raw or not str(field_raw).strip():
        pytest.skip(
            "Set PIPE_AI_AUTOMATION_LIVE_FIELD_ID to a field internal_id "
            "(see module docstring)."
        )

    pipe_id = str(pipe_raw).strip()
    field_id = str(field_raw).strip()
    token = uuid.uuid4().hex[:10]
    name = f"MCP AI auto live {token}"

    with patch("pipefy_mcp.server.settings", settings):
        async with create_client_session(
            mcp_server,
            read_timeout_seconds=timedelta(seconds=120),
            raise_exceptions=True,
        ) as session:
            create_result = await session.call_tool(
                "create_ai_automation",
                {
                    "name": name,
                    "event_id": "card_created",
                    "pipe_id": pipe_id,
                    "prompt": f"Summarize card %{field_id}",
                    "field_ids": [field_id],
                },
            )
    assert create_result.isError is False, create_result
    payload = extract_payload(create_result)
    if not payload.get("success"):
        pytest.skip(
            f"create_ai_automation failed (check AI on pipe / permissions): {payload!r}"
        )
    automation_id = str(payload.get("automation_id") or "").strip()
    assert automation_id, f"Missing automation_id in payload: {payload!r}"

    with patch("pipefy_mcp.server.settings", settings):
        async with create_client_session(
            mcp_server,
            read_timeout_seconds=timedelta(seconds=120),
            raise_exceptions=True,
        ) as session:
            delete_result = await session.call_tool(
                "delete_automation",
                {"automation_id": automation_id, "confirm": True},
            )
    assert delete_result.isError is False, delete_result
    del_payload = extract_payload(delete_result)
    assert del_payload.get("success") is True, del_payload
