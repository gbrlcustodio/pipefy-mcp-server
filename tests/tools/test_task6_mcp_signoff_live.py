"""Task 6 sign-off — automated slice of MCP stack smoke (opt-in integration).

Task 6 in ``tasks-ai-agents-field-conditions.md`` also requires **manual** steps in **Cursor MCP**
(operator + LLM UX, ``destructiveHint`` gating, recording outcome). This module covers the
pieces that can run in CI/agent sandboxes via ``call_tool`` on ``pipefy_mcp.server.mcp``.

**Run (after ``.env`` with ``PIPEFY_*`` + a disposable test pipe):**

    export TASK6_SIGNOFF_PIPE_ID=123456789
    export PIPE_FIELD_CONDITION_LIVE_PHASE_ID=987654321
    uv run pytest tests/tools/test_task6_mcp_signoff_live.py -m integration -v

``TASK6_SIGNOFF_PIPE_ID`` falls back to ``PIPE_BUILDING_LIVE_PIPE_ID`` if unset.
``PIPE_FIELD_CONDITION_LIVE_PHASE_ID`` falls back to ``TASK6_SIGNOFF_PHASE_ID``.

**Also run** (field condition create/delete cycle): ``tests/tools/test_field_conditions_tools_live.py``.

**Manual only (Cursor):** Task 6.4–6.5 — UI parity, destructive confirmation UX, PR/ticket note.
"""

from __future__ import annotations

import os
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
    return bool(p.graphql_url and p.oauth_url and p.oauth_client and p.oauth_secret)


def _require_live_creds() -> None:
    if not _pipefy_live_configured():
        pytest.skip(
            "Pipefy credentials not configured (PIPEFY_GRAPHQL_URL + OAuth in .env)"
        )


def _task6_pipe_id() -> int | None:
    for key in ("TASK6_SIGNOFF_PIPE_ID", "PIPE_BUILDING_LIVE_PIPE_ID"):
        raw = os.environ.get(key)
        if raw:
            return int(raw)
    return None


def _task6_phase_id() -> int | None:
    raw = os.environ.get("PIPE_FIELD_CONDITION_LIVE_PHASE_ID") or os.environ.get(
        "TASK6_SIGNOFF_PHASE_ID"
    )
    return int(raw) if raw else None


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.integration
@pytest.mark.anyio
async def test_task6_6_1_and_6_2_get_pipe_then_get_ai_agents(extract_payload):
    """6.1 + 6.2: get_pipe exposes uuid/phases; get_ai_agents(repo_uuid) succeeds."""
    _require_live_creds()
    pipe_id = _task6_pipe_id()
    if pipe_id is None:
        pytest.skip(
            "Set TASK6_SIGNOFF_PIPE_ID or PIPE_BUILDING_LIVE_PIPE_ID to a test pipe "
            "(see module docstring)"
        )

    with patch("pipefy_mcp.server.settings", settings):
        async with create_client_session(
            mcp_server,
            read_timeout_seconds=timedelta(seconds=90),
            raise_exceptions=True,
        ) as session:
            r_pipe = await session.call_tool("get_pipe", {"pipe_id": pipe_id})

    assert r_pipe.isError is False, r_pipe
    payload = extract_payload(r_pipe)
    pipe = payload.get("pipe")
    assert pipe is not None, payload
    assert str(pipe.get("id")) == str(pipe_id)
    repo_uuid = pipe.get("uuid")
    assert repo_uuid, "pipe.uuid required for get_ai_agents"
    phases = pipe.get("phases")
    assert isinstance(phases, list), "pipe.phases should be a list"

    with patch("pipefy_mcp.server.settings", settings):
        async with create_client_session(
            mcp_server,
            read_timeout_seconds=timedelta(seconds=90),
            raise_exceptions=True,
        ) as session:
            r_agents = await session.call_tool(
                "get_ai_agents",
                {"repo_uuid": str(repo_uuid)},
            )

    assert r_agents.isError is False, r_agents
    agents_payload = extract_payload(r_agents)
    assert agents_payload.get("success") is True, agents_payload
    assert "agents" in agents_payload


@pytest.mark.integration
@pytest.mark.anyio
async def test_task6_6_2_get_ai_agent_when_env_set(extract_payload):
    """Optional: load one agent by UUID (compare with Pipefy UI)."""
    _require_live_creds()
    agent_uuid = os.environ.get("TASK6_SIGNOFF_AGENT_UUID")
    if not agent_uuid:
        pytest.skip(
            "Set TASK6_SIGNOFF_AGENT_UUID to run get_ai_agent live check (optional)"
        )

    with patch("pipefy_mcp.server.settings", settings):
        async with create_client_session(
            mcp_server,
            read_timeout_seconds=timedelta(seconds=60),
            raise_exceptions=True,
        ) as session:
            r = await session.call_tool("get_ai_agent", {"uuid": agent_uuid.strip()})

    assert r.isError is False, r
    body = extract_payload(r)
    assert body.get("success") is True, body
    assert body.get("agent"), body


@pytest.mark.integration
@pytest.mark.anyio
async def test_task6_6_3_get_phase_fields_includes_internal_id_and_uuid(
    extract_payload,
):
    """6.3 (read slice): get_phase_fields returns internal_id and uuid per field."""
    _require_live_creds()
    phase_id = _task6_phase_id()
    if phase_id is None:
        pytest.skip(
            "Set PIPE_FIELD_CONDITION_LIVE_PHASE_ID or TASK6_SIGNOFF_PHASE_ID "
            "(phase with fields — see test_field_conditions_tools_live.py)"
        )

    with patch("pipefy_mcp.server.settings", settings):
        async with create_client_session(
            mcp_server,
            read_timeout_seconds=timedelta(seconds=90),
            raise_exceptions=True,
        ) as session:
            r = await session.call_tool(
                "get_phase_fields",
                {"phase_id": phase_id, "required_only": False},
            )

    assert r.isError is False, r
    payload = extract_payload(r)
    fields = payload.get("fields") or []
    if not fields:
        pytest.skip(f"Phase {phase_id} has no fields; cannot assert internal_id shape")

    for idx, field in enumerate(fields[:5]):
        assert field.get("internal_id") is not None, (
            f"fields[{idx}] missing internal_id (Task 5.3 / GET_PHASE_FIELDS_QUERY)"
        )
        assert field.get("uuid") is not None, (
            f"fields[{idx}] missing uuid (Task 5.3 / GET_PHASE_FIELDS_QUERY)"
        )
