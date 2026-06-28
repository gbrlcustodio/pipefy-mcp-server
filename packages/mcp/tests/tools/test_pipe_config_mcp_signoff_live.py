"""Live MCP smoke tests for pipe config and field-condition tooling (opt-in integration).

Exercises ``call_tool`` against ``pipefy_mcp.server.mcp`` with real credentials. Full release
checklists may still require manual validation in an MCP client (e.g. destructive-hint UX).

Run (``.env`` with ``PIPEFY_*`` and a disposable test pipe):

    export PIPE_CONFIG_SIGNOFF_PIPE_ID=123456789
    export PIPE_FIELD_CONDITION_LIVE_PHASE_ID=987654321
    uv run pytest packages/mcp/tests/tools/test_pipe_config_mcp_signoff_live.py -m integration -v

``PIPE_CONFIG_SIGNOFF_PIPE_ID`` falls back to ``PIPE_BUILDING_LIVE_PIPE_ID`` if unset.
``PIPE_FIELD_CONDITION_LIVE_PHASE_ID`` falls back to ``PIPE_CONFIG_SIGNOFF_PHASE_ID``.

Also run field-condition create/delete coverage:
``packages/mcp/tests/tools/test_field_conditions_tools_live.py``.
See ``docs/mcp/tools/cross-cutting.md`` and field-condition tool docs under ``docs/mcp/tools/``
for expected MCP behavior.
"""

from __future__ import annotations

import os
from datetime import timedelta
from unittest.mock import patch

import pytest
from _shared.live_settings import require_live_creds
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.server import build_pipefy_mcp_server
from pipefy_mcp.settings import get_settings

mcp_server = build_pipefy_mcp_server()

_LEGACY_TASK6_PIPE_ID = "TASK6_SIGNOFF_PIPE_ID"
_LEGACY_TASK6_PHASE_ID = "TASK6_SIGNOFF_PHASE_ID"
_LEGACY_TASK6_AGENT_UUID = "TASK6_SIGNOFF_AGENT_UUID"


def _env_first_int(*keys: str) -> int | None:
    for key in keys:
        raw = os.environ.get(key)
        if raw:
            return int(raw)
    return None


def _signoff_pipe_id() -> int | None:
    return _env_first_int(
        "PIPE_CONFIG_SIGNOFF_PIPE_ID",
        "PIPE_BUILDING_LIVE_PIPE_ID",
        _LEGACY_TASK6_PIPE_ID,
    )


def _signoff_phase_id() -> int | None:
    return _env_first_int(
        "PIPE_FIELD_CONDITION_LIVE_PHASE_ID",
        "PIPE_CONFIG_SIGNOFF_PHASE_ID",
        _LEGACY_TASK6_PHASE_ID,
    )


def _signoff_agent_uuid() -> str | None:
    for key in ("PIPE_CONFIG_SIGNOFF_AGENT_UUID", _LEGACY_TASK6_AGENT_UUID):
        raw = os.environ.get(key)
        if raw:
            return raw.strip()
    return None


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_get_pipe_then_get_ai_agents(extract_payload):
    """get_pipe exposes uuid/phases; get_ai_agents(repo_uuid) succeeds on the same pipe."""
    require_live_creds()
    pipe_id = _signoff_pipe_id()
    if pipe_id is None:
        pytest.skip(
            "Set PIPE_CONFIG_SIGNOFF_PIPE_ID or PIPE_BUILDING_LIVE_PIPE_ID to a test pipe "
            "(see module docstring)"
        )

    with patch("pipefy_mcp.settings.get_settings", get_settings):
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

    with patch("pipefy_mcp.settings.get_settings", get_settings):
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
async def test_live_get_ai_agent_when_env_set(extract_payload):
    """Optional: load one agent by UUID (compare with Pipefy UI)."""
    require_live_creds()
    agent_uuid = _signoff_agent_uuid()
    if not agent_uuid:
        pytest.skip(
            "Set PIPE_CONFIG_SIGNOFF_AGENT_UUID to run get_ai_agent live check (optional)"
        )

    with patch("pipefy_mcp.settings.get_settings", get_settings):
        async with create_client_session(
            mcp_server,
            read_timeout_seconds=timedelta(seconds=60),
            raise_exceptions=True,
        ) as session:
            r = await session.call_tool("get_ai_agent", {"uuid": agent_uuid})

    assert r.isError is False, r
    body = extract_payload(r)
    assert body.get("success") is True, body
    assert body.get("agent"), body


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_get_phase_fields_includes_internal_id_and_uuid(
    extract_payload,
):
    """get_phase_fields returns internal_id and uuid per field."""
    require_live_creds()
    phase_id = _signoff_phase_id()
    if phase_id is None:
        pytest.skip(
            "Set PIPE_FIELD_CONDITION_LIVE_PHASE_ID or PIPE_CONFIG_SIGNOFF_PHASE_ID "
            "(phase with fields — see test_field_conditions_tools_live.py)"
        )

    with patch("pipefy_mcp.settings.get_settings", get_settings):
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
            f"fields[{idx}] missing internal_id (get_phase_fields / GET_PHASE_FIELDS_QUERY)"
        )
        assert field.get("uuid") is not None, (
            f"fields[{idx}] missing uuid (get_phase_fields / GET_PHASE_FIELDS_QUERY)"
        )
