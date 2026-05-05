"""Live MCP path for field conditions (no execute_graphql).

Exercises **get_phase_fields** → **create_field_condition** → **delete_field_condition**
through **pipefy_mcp.server.mcp** (full ToolRegistry + PipefyClient). Skips without
**PIPEFY_*** OAuth or when **PIPE_FIELD_CONDITION_LIVE_PHASE_ID** is unset.

**Setup:** Use a disposable pipe/phase with **at least two phase fields** (any types).
The test uses one field as the condition trigger (**field_address** = its **internal_id**)
and the other as **phaseFieldId** in **actions**. Grant the service account **create /
delete field conditions** on that phase.

Run:
    uv run pytest tests/tools/test_field_conditions_tools_live.py -m integration -v

Env:
    PIPE_FIELD_CONDITION_LIVE_PHASE_ID  — numeric phase ID (required for this module)
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
async def test_live_field_condition_tools_only_happy_path(extract_payload):
    """Full stack: get_phase_fields → create_field_condition → delete_field_condition."""
    require_live_creds()
    phase_raw = os.environ.get("PIPE_FIELD_CONDITION_LIVE_PHASE_ID")
    if not phase_raw:
        pytest.skip(
            "Set PIPE_FIELD_CONDITION_LIVE_PHASE_ID to a phase with 2+ fields "
            "(see tests/tools/test_field_conditions_tools_live.py docstring)"
        )
    phase_id = int(phase_raw)

    with patch("pipefy_mcp.server.settings", settings):
        async with create_client_session(
            mcp_server,
            read_timeout_seconds=timedelta(seconds=120),
            raise_exceptions=True,
        ) as session:
            r_fields = await session.call_tool(
                "get_phase_fields",
                {"phase_id": phase_id, "required_only": False},
            )
    assert r_fields.isError is False, r_fields
    pf_payload = extract_payload(r_fields)
    fields = pf_payload.get("fields") or []
    if len(fields) < 2:
        pytest.skip(
            f"Phase {phase_id} has fewer than 2 fields ({len(fields)}); "
            "add fields or pick another phase."
        )

    trigger = fields[0]
    target = fields[1]
    for label, f in ("trigger", trigger), ("target", target):
        iid = f.get("internal_id")
        if iid is None or str(iid).strip() == "":
            pytest.skip(
                f"Phase field ({label}) missing internal_id — cannot build field condition "
                "payload (ensure get_phase_fields returns internal_id from the API)."
            )

    trigger_id = str(trigger["internal_id"]).strip()
    target_id = str(target["internal_id"]).strip()

    expr_token = uuid.uuid4().hex[:10]
    condition = {
        "expressions": [
            {
                "field_address": trigger_id,
                "operation": "equals",
                "value": f"mcp_fc_sentinel_{expr_token}",
                "structure_id": 1,
            }
        ],
        "expressions_structure": [[1]],
    }
    actions = [{"phaseFieldId": target_id, "whenEvaluator": True, "actionId": "hide"}]
    rule_name = f"MCP field cond {expr_token}"

    condition_id_created: str | None = None
    deleted_successfully = False
    try:
        with patch("pipefy_mcp.server.settings", settings):
            async with create_client_session(
                mcp_server,
                read_timeout_seconds=timedelta(seconds=120),
                raise_exceptions=True,
            ) as session:
                r_create = await session.call_tool(
                    "create_field_condition",
                    {
                        "phase_id": phase_id,
                        "condition": condition,
                        "actions": actions,
                        "extra_input": {"name": rule_name},
                        "debug": True,
                    },
                )
        assert r_create.isError is False, r_create
        created = extract_payload(r_create)
        assert created.get("success") is True, created
        condition_id_created = created.get("condition_id")
        assert condition_id_created, created

        with patch("pipefy_mcp.server.settings", settings):
            async with create_client_session(
                mcp_server,
                read_timeout_seconds=timedelta(seconds=120),
                raise_exceptions=True,
            ) as session:
                r_delete = await session.call_tool(
                    "delete_field_condition",
                    {"condition_id": condition_id_created, "debug": True},
                )
        assert r_delete.isError is False, r_delete
        deleted = extract_payload(r_delete)
        assert deleted.get("success") is True, deleted
        deleted_successfully = True
    finally:
        if condition_id_created and not deleted_successfully:
            with patch("pipefy_mcp.server.settings", settings):
                async with create_client_session(
                    mcp_server,
                    read_timeout_seconds=timedelta(seconds=120),
                    raise_exceptions=True,
                ) as session:
                    await session.call_tool(
                        "delete_field_condition",
                        {"condition_id": condition_id_created, "debug": True},
                    )
