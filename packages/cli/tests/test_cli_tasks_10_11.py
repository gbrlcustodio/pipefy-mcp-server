"""Smoke tests for CLI tasks 10.0 / 11.0 domains."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from pipefy_cli.main import app


def test_agent_validate_behaviors_json(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("ag-val")
    mock_client = MagicMock()
    mock_client.get_pipe = AsyncMock(
        return_value={"pipe": {"phases": [], "start_form_fields": []}}
    )
    mock_client.get_pipe_relations = AsyncMock(
        return_value={"children": [], "parents": []}
    )
    mock_client.get_phase_allowed_move_targets = AsyncMock(
        return_value={"phase": {"cards_can_be_moved_to_phases": []}}
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(
            app,
            [
                "agent",
                "validate-behaviors",
                "--pipe",
                "1",
                "--behaviors",
                json.dumps(
                    [
                        {
                            "name": "x",
                            "event_id": "card_created",
                            "actionParams": {
                                "aiBehaviorParams": {
                                    "instruction": "hi",
                                    "actionsAttributes": [
                                        {
                                            "name": "m",
                                            "actionType": "move_card",
                                            "metadata": {"destinationPhaseId": "2"},
                                        }
                                    ],
                                }
                            },
                        }
                    ]
                ),
                "--json",
            ],
        )
    assert r.exit_code == 0
    body = json.loads(r.stdout)
    assert body.get("success") is True


def test_ai_automation_validate_prompt_json(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("ai-val")
    mock_client = MagicMock()
    mock_client.get_pipe_with_preferences = AsyncMock(
        return_value={
            "pipe": {
                "phases": [{"fields": [{"internal_id": "9", "id": "f", "label": "L"}]}],
                "start_form_fields": [],
                "preferences": {"aiAgentsEnabled": True},
                "organizationId": "300",
            }
        }
    )
    mock_client.get_automation_events = AsyncMock(return_value=[{"id": "card_created"}])
    mock_client.get_ai_credit_usage = AsyncMock(
        return_value={"aiCreditUsageStats": {"active": True, "usage": 0, "limit": 0}}
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(
            app,
            [
                "ai-automation",
                "validate-prompt",
                "--pipe",
                "1",
                "--prompt",
                "Hello %{9}",
                "--field-ids",
                '["9"]',
                "--event-id",
                "card_created",
                "--json",
            ],
        )
    assert r.exit_code == 0
    body = json.loads(r.stdout)
    assert body.get("valid") is True


def test_usage_credits_invokes_client(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("usage-c")
    mock_client = MagicMock()
    mock_client.get_ai_credit_usage = AsyncMock(return_value={"aiCreditUsageStats": {}})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(
            app,
            [
                "usage",
                "credits",
                "--organization",
                "1",
                "--period",
                "current_month",
                "--json",
            ],
        )
    assert r.exit_code == 0
    mock_client.get_ai_credit_usage.assert_awaited_once()


def test_org_get_json(runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("org-g")
    mock_client = MagicMock()
    mock_client.get_organization = AsyncMock(return_value={"organization": {"id": "1"}})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(app, ["org", "get", "1", "--json"])
    assert r.exit_code == 0


def test_export_automation_jobs_json(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("ex-j")
    mock_client = MagicMock()
    mock_client.export_automation_jobs = AsyncMock(return_value={"ok": True})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(
            app,
            [
                "export",
                "automation-jobs",
                "--organization",
                "1",
                "--period",
                "current_month",
                "--json",
            ],
        )
    assert r.exit_code == 0


def test_report_pipe_export_rejects_json_with_csv(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("rpcsv")
    r = runner.invoke(
        app,
        [
            "report-pipe",
            "export",
            "--pipe",
            "p1",
            "--report-id",
            "r1",
            "--format",
            "csv",
            "--json",
        ],
    )
    assert r.exit_code != 0
    assert "mutually" in r.stderr.lower() or "cannot" in r.stderr.lower()


def test_report_org_export_rejects_json_with_csv(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("rocsv")
    r = runner.invoke(
        app,
        [
            "report-org",
            "export",
            "--organization",
            "o1",
            "--format",
            "csv",
            "--json",
        ],
    )
    assert r.exit_code != 0
    assert "mutually" in r.stderr.lower() or "cannot" in r.stderr.lower()


def test_export_poll_max_rounds_maps_timeout():
    from pipefy_cli.commands._common import export_poll_max_rounds

    assert export_poll_max_rounds(90.0) == 45
    assert export_poll_max_rounds(2.0) == 1
    with pytest.raises(ValueError):
        export_poll_max_rounds(0.0)


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


def test_agent_create_happy_path_chains_create_then_update(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    """``agent create`` runs preflight, then ``create_ai_agent`` + ``update_ai_agent``."""
    oauth_env("ag-create-ok")
    mock_client = MagicMock()
    mock_client.create_ai_agent = AsyncMock(return_value={"agent_uuid": "uuid-1"})
    mock_client.update_ai_agent = AsyncMock(return_value={})

    preflight_ok = {
        "success": True,
        "valid": True,
        "problems": [],
        "warnings": [],
        "message": "All behaviors passed validation.",
    }

    with (
        patch(
            "pipefy_cli.commands._common.get_authenticated_client",
            return_value=mock_client,
        ),
        patch(
            "pipefy_cli.commands.agent.validate_ai_agent_behaviors_sdk",
            new=AsyncMock(return_value=preflight_ok),
        ),
        patch(
            "pipefy_cli.commands.agent.resolve_and_populate_field_refs",
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
                "Acme",
                "--instruction",
                "Be helpful.",
                "--behaviors",
                json.dumps([_AGENT_BEHAVIOR]),
                "--json",
            ],
        )

    assert r.exit_code == 0, r.stderr
    body = json.loads(r.stdout)
    assert body == {
        "success": True,
        "agent_uuid": "uuid-1",
        "message": "Created agent uuid-1",
    }
    mock_client.create_ai_agent.assert_awaited_once()
    mock_client.update_ai_agent.assert_awaited_once()


def test_agent_create_blocks_when_preflight_invalid(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    """``agent create`` exits with a usage error (code 2) when the preflight reports problems."""
    oauth_env("ag-create-blocked")
    mock_client = MagicMock()
    mock_client.create_ai_agent = AsyncMock()
    mock_client.update_ai_agent = AsyncMock()

    preflight_block = {
        "success": True,
        "valid": False,
        "problems": ["destinationPhaseId 999 not found in pipe phases."],
        "warnings": [],
        "message": "Found 1 problem(s) in behaviors.",
    }

    with (
        patch(
            "pipefy_cli.commands._common.get_authenticated_client",
            return_value=mock_client,
        ),
        patch(
            "pipefy_cli.commands.agent.validate_ai_agent_behaviors_sdk",
            new=AsyncMock(return_value=preflight_block),
        ),
    ):
        r = runner.invoke(
            app,
            [
                "agent",
                "create",
                "--repo-uuid",
                "repo-uuid-2",
                "--pipe",
                "1",
                "--name",
                "Acme",
                "--instruction",
                "Be helpful.",
                "--behaviors",
                json.dumps([_AGENT_BEHAVIOR]),
                "--json",
            ],
        )

    assert r.exit_code == 2
    assert "validate-behaviors failed" in r.stderr
    assert "destinationPhaseId 999" in r.stderr
    mock_client.create_ai_agent.assert_not_called()
    mock_client.update_ai_agent.assert_not_called()


def test_ai_automation_create_requires_oauth(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    """``ai-automation create`` exits 2 with a clear message when OAuth is not configured."""
    oauth_env("ai-no-oauth")
    mock_client = MagicMock()
    mock_client.ai_automation_available = False

    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(
            app,
            [
                "ai-automation",
                "create",
                "--pipe",
                "1",
                "--name",
                "Email summary",
                "--event-id",
                "card_created",
                "--prompt",
                "Summarize: %{9}",
                "--field-ids",
                '["9"]',
                "--json",
            ],
        )

    assert r.exit_code == 2
    assert "OAuth" in r.stderr
    mock_client.create_ai_automation.assert_not_called()
