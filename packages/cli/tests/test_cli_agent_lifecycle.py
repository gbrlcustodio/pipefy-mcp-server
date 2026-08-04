"""CLI lifecycle tests for AI agent active/disabled create and update."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from pipefy_cli.main import app

_AGENT_BEHAVIOR = {
    "name": "move on create",
    "event_id": "card_created",
    "actionParams": {
        "aiBehaviorParams": {
            "instruction": "Summarize the card.",
            "actionsAttributes": [
                {
                    "name": "Move",
                    "actionType": "move_card",
                    "metadata": {"destinationPhaseId": "2"},
                }
            ],
        }
    },
}

_PREFLIGHT_OK = {
    "success": True,
    "valid": True,
    "problems": [],
    "warnings": [],
    "message": "All behaviors passed validation.",
}


def test_agent_create_default_sets_preserve_disabled_at_false_on_update_chain(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    """Default ``agent create`` passes ``preserve_disabled_at=False`` on chained update."""
    oauth_env("ag-create-active")
    mock_client = MagicMock()
    mock_client.create_ai_agent = AsyncMock(
        return_value={
            "agent_uuid": "active-uuid",
            "disabled_at": "2026-08-04T12:00:00+00:00",
            "active": False,
        }
    )
    mock_client.update_ai_agent = AsyncMock(
        return_value={
            "agent_uuid": "active-uuid",
            "disabled_at": None,
            "active": True,
        }
    )

    with (
        patch(
            "pipefy_cli.commands._common.get_authenticated_client",
            return_value=mock_client,
        ),
        patch(
            "pipefy_cli.commands.agent.validate_ai_agent_behaviors_sdk",
            new=AsyncMock(return_value=_PREFLIGHT_OK),
        ),
        patch(
            "pipefy_sdk.client.resolve_and_populate_field_refs",
            new=AsyncMock(side_effect=lambda _c, behaviors: behaviors),
        ),
    ):
        r = runner.invoke(
            app,
            [
                "agent",
                "create",
                "--repo-uuid",
                "repo-uuid-1",
                "--pipe",
                "1",
                "--name",
                "Active Agent",
                "--instruction",
                "Be helpful.",
                "--behaviors",
                json.dumps([_AGENT_BEHAVIOR]),
                "--json",
            ],
        )

    assert r.exit_code == 0, r.stderr
    body = json.loads(r.stdout)
    assert body["agent_uuid"] == "active-uuid"
    assert body["disabled_at"] is None
    assert body["active"] is True

    create_arg = mock_client.create_ai_agent.call_args.args[0]
    assert create_arg.disabled_at is None
    update_arg = mock_client.update_ai_agent.call_args.args[0]
    assert update_arg.disabled_at is None
    assert update_arg.preserve_disabled_at is False


def test_agent_create_inactive_sets_disabled_at_on_create_and_update_chain(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    """``agent create --inactive`` sets the same ``disabled_at`` on create + chained update."""
    oauth_env("ag-create-inactive")
    stub_disabled_at = "2026-08-04T13:00:00+00:00"
    mock_client = MagicMock()
    mock_client.create_ai_agent = AsyncMock(
        return_value={
            "agent_uuid": "inactive-uuid",
            "disabled_at": stub_disabled_at,
            "active": False,
        }
    )
    mock_client.update_ai_agent = AsyncMock(
        return_value={
            "agent_uuid": "inactive-uuid",
            "disabled_at": stub_disabled_at,
            "active": False,
        }
    )

    with (
        patch(
            "pipefy_cli.commands._common.get_authenticated_client",
            return_value=mock_client,
        ),
        patch(
            "pipefy_cli.commands.agent.validate_ai_agent_behaviors_sdk",
            new=AsyncMock(return_value=_PREFLIGHT_OK),
        ),
        patch(
            "pipefy_sdk.client.resolve_and_populate_field_refs",
            new=AsyncMock(side_effect=lambda _c, behaviors: behaviors),
        ),
    ):
        r = runner.invoke(
            app,
            [
                "agent",
                "create",
                "--repo-uuid",
                "repo-uuid-1",
                "--pipe",
                "1",
                "--name",
                "Inactive Agent",
                "--instruction",
                "Be helpful.",
                "--behaviors",
                json.dumps([_AGENT_BEHAVIOR]),
                "--inactive",
                "--json",
            ],
        )

    assert r.exit_code == 0, r.stderr
    body = json.loads(r.stdout)
    assert body["agent_uuid"] == "inactive-uuid"
    assert body["disabled_at"] == stub_disabled_at
    assert body["active"] is False

    create_arg = mock_client.create_ai_agent.call_args.args[0]
    assert create_arg.disabled_at is not None
    datetime.fromisoformat(create_arg.disabled_at)
    update_arg = mock_client.update_ai_agent.call_args.args[0]
    assert update_arg.disabled_at == create_arg.disabled_at
    assert update_arg.preserve_disabled_at is True


def test_agent_update_json_exposes_active_when_disabled_at_null(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    """``agent update --json`` exposes ``disabled_at`` null and ``active`` true from SDK."""
    oauth_env("ag-update-active-json")
    mock_client = MagicMock()
    mock_client.update_ai_agent = AsyncMock(
        return_value={
            "agent_uuid": "active-uuid",
            "message": "AI Agent updated successfully. UUID: active-uuid",
            "disabled_at": None,
            "active": True,
        }
    )

    with (
        patch(
            "pipefy_cli.commands._common.get_authenticated_client",
            return_value=mock_client,
        ),
        patch(
            "pipefy_cli.commands.agent.validate_ai_agent_behaviors_sdk",
            new=AsyncMock(return_value=_PREFLIGHT_OK),
        ),
        patch(
            "pipefy_sdk.client.resolve_and_populate_field_refs",
            new=AsyncMock(side_effect=lambda _c, behaviors: behaviors),
        ),
    ):
        r = runner.invoke(
            app,
            [
                "agent",
                "update",
                "--uuid",
                "active-uuid",
                "--repo-uuid",
                "repo-uuid-1",
                "--pipe",
                "1",
                "--name",
                "Active Agent",
                "--instruction",
                "Be helpful.",
                "--behaviors",
                json.dumps([_AGENT_BEHAVIOR]),
                "--json",
            ],
        )

    assert r.exit_code == 0, r.stderr
    body = json.loads(r.stdout)
    assert body["disabled_at"] is None
    assert body["active"] is True


def test_agent_update_json_exposes_active_false_when_disabled(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    """``agent update --json`` exposes ``disabled_at`` and ``active`` false from SDK."""
    oauth_env("ag-update-inactive-json")
    stub_disabled_at = "2026-01-15T12:00:00+00:00"
    mock_client = MagicMock()
    mock_client.update_ai_agent = AsyncMock(
        return_value={
            "agent_uuid": "inactive-uuid",
            "message": "AI Agent updated successfully. UUID: inactive-uuid",
            "disabled_at": stub_disabled_at,
            "active": False,
        }
    )

    with (
        patch(
            "pipefy_cli.commands._common.get_authenticated_client",
            return_value=mock_client,
        ),
        patch(
            "pipefy_cli.commands.agent.validate_ai_agent_behaviors_sdk",
            new=AsyncMock(return_value=_PREFLIGHT_OK),
        ),
        patch(
            "pipefy_sdk.client.resolve_and_populate_field_refs",
            new=AsyncMock(side_effect=lambda _c, behaviors: behaviors),
        ),
    ):
        r = runner.invoke(
            app,
            [
                "agent",
                "update",
                "--uuid",
                "inactive-uuid",
                "--repo-uuid",
                "repo-uuid-1",
                "--pipe",
                "1",
                "--name",
                "Inactive Agent",
                "--instruction",
                "Be helpful.",
                "--behaviors",
                json.dumps([_AGENT_BEHAVIOR]),
                "--json",
            ],
        )

    assert r.exit_code == 0, r.stderr
    body = json.loads(r.stdout)
    assert body["disabled_at"] == stub_disabled_at
    assert body["active"] is False
