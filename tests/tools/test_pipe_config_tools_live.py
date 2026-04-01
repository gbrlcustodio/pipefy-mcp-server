"""Live MCP calls for pipe-building tools using the production FastMCP app.

Uses ``pipefy_mcp.server.mcp`` (same entrypoint as ``uv run pipeclaw``): lifespan,
ToolRegistry, PipeConfigTools, and real PipefyClient. Skips when PIPEFY_* creds
are missing from the environment.

Run (read-only tests only need .env with Pipefy OAuth):
    uv run pytest tests/tools/test_pipe_config_tools_live.py -m integration -v

Optional env for extra coverage:
    PIPE_BUILDING_LIVE_PIPE_ID   — e.g. a test pipe ID for ``get_pipe``
    PIPE_BUILDING_LIVE_ORG_ID    — org ID for ``create_pipe`` (creates a new pipe each run)
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


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_pipeclaw_mcp_introspect_type_create_pipe_input(extract_payload):
    """Full stack: MCP tool -> introspection -> GraphQL (read-only)."""
    _require_live_creds()
    with patch("pipefy_mcp.server.settings", settings):
        async with create_client_session(
            mcp_server,
            read_timeout_seconds=timedelta(seconds=60),
            raise_exceptions=True,
        ) as session:
            result = await session.call_tool(
                "introspect_type",
                {"type_name": "CreatePipeInput"},
            )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "CreatePipeInput" in payload["result"]
    assert "organization_id" in payload["result"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_pipeclaw_mcp_get_pipe(extract_payload):
    """Full stack: MCP ``get_pipe`` (read-only)."""
    _require_live_creds()
    pipe_id_raw = os.environ.get("PIPE_BUILDING_LIVE_PIPE_ID")
    if not pipe_id_raw:
        pytest.skip(
            "Set PIPE_BUILDING_LIVE_PIPE_ID to a pipe you can read (optional live check)"
        )
    pipe_id = int(pipe_id_raw)
    with patch("pipefy_mcp.server.settings", settings):
        async with create_client_session(
            mcp_server,
            read_timeout_seconds=timedelta(seconds=60),
            raise_exceptions=True,
        ) as session:
            result = await session.call_tool("get_pipe", {"pipe_id": pipe_id})
    assert result.isError is False
    payload = extract_payload(result)
    assert payload.get("pipe") is not None
    assert str(payload["pipe"].get("id")) == str(pipe_id)


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_pipeclaw_mcp_create_pipe(extract_payload):
    """Full stack: MCP ``create_pipe`` — creates a real pipe (opt-in via env)."""
    _require_live_creds()
    org_raw = os.environ.get("PIPE_BUILDING_LIVE_ORG_ID")
    if not org_raw:
        pytest.skip(
            "Set PIPE_BUILDING_LIVE_ORG_ID to run a live create_pipe (writes to Pipefy)"
        )
    org_id = int(org_raw)
    with patch("pipefy_mcp.server.settings", settings):
        async with create_client_session(
            mcp_server,
            read_timeout_seconds=timedelta(seconds=90),
            raise_exceptions=True,
        ) as session:
            result = await session.call_tool(
                "create_pipe",
                {
                    "name": f"MCP integration {uuid.uuid4().hex[:8]} (delete me)",
                    "organization_id": org_id,
                },
            )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "createPipe" in payload["result"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_pipeclaw_mcp_create_label_hex_color(extract_payload):
    """Full stack: MCP ``create_label`` — requires pipe id (opt-in, writes)."""
    _require_live_creds()
    pipe_raw = os.environ.get("PIPE_BUILDING_LIVE_PIPE_ID")
    if not pipe_raw:
        pytest.skip("Set PIPE_BUILDING_LIVE_PIPE_ID for create_label live test")
    pipe_id = int(pipe_raw)
    with patch("pipefy_mcp.server.settings", settings):
        async with create_client_session(
            mcp_server,
            read_timeout_seconds=timedelta(seconds=90),
            raise_exceptions=True,
        ) as session:
            result = await session.call_tool(
                "create_label",
                {
                    "pipe_id": pipe_id,
                    "name": f"MCP live lbl {uuid.uuid4().hex[:8]}",
                    "color": "#00AA00",
                },
            )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "createLabel" in payload["result"]
