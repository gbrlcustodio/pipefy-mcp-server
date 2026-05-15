"""Tests for ``pipefy phase`` and ``pipefy field`` subcommands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_cli.main import app


def test_phase_get_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("ph-get")
    payload = {"phase_id": "1", "phase_name": "Backlog", "fields": []}
    mock_client = MagicMock()
    mock_client.get_phase_fields = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["phase", "get", "1", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == payload
    mock_client.get_phase_fields.assert_awaited_once_with("1", required_only=False)


def test_phase_create_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("ph-cr")
    payload = {"createPhase": {}}
    mock_client = MagicMock()
    mock_client.create_phase = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["phase", "create", "--pipe", "9", "--name", "Review", "--json"],
        )
    assert result.exit_code == 0
    mock_client.create_phase.assert_awaited_once_with(
        "9", "Review", done=False, index=None, description=None
    )


def test_phase_update_resolves_name_json(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("ph-upd")
    mock_client = MagicMock()
    mock_client.get_phase_fields = AsyncMock(
        return_value={"phase_name": "Todo", "fields": []}
    )
    mock_client.update_phase = AsyncMock(return_value={"updatePhase": {}})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["phase", "update", "3", "--description", "x", "--json"],
        )
    assert result.exit_code == 0
    mock_client.update_phase.assert_awaited_once_with("3", description="x", name="Todo")


def test_phase_delete_yes(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("ph-del")
    mock_client = MagicMock()
    mock_client.delete_phase = AsyncMock(return_value={"deletePhase": {}})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["phase", "delete", "3", "--yes", "--json"])
    assert result.exit_code == 0
    mock_client.delete_phase.assert_awaited_once_with("3")


def test_field_list_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("fld-list")
    payload = {"phase_id": "1", "fields": []}
    mock_client = MagicMock()
    mock_client.get_phase_fields = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["field", "list", "--phase", "1", "--json"])
    assert result.exit_code == 0
    mock_client.get_phase_fields.assert_awaited_once_with("1", required_only=False)


def test_field_create_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("fld-cr")
    mock_client = MagicMock()
    mock_client.create_phase_field = AsyncMock(return_value={"createPhaseField": {}})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "field",
                "create",
                "--phase",
                "2",
                "--label",
                "Owner",
                "--type",
                "assignee_select",
                "--json",
            ],
        )
    assert result.exit_code == 0
    mock_client.create_phase_field.assert_awaited_once_with(
        "2", "Owner", "assignee_select"
    )


def test_field_update_forwards_extra_phase_id_for_slug_resolution(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    """``--extra '{"phase_id": ...}'`` reaches ``client.update_phase_field`` verbatim.

    Locks the CLI side of the smoke-2026-05-15 slug-resolution fix: the SDK can only
    map ``"priority"`` to its ``internal_id`` if the CLI forwards ``phase_id`` as a
    keyword argument.
    """
    oauth_env("fld-upd")
    mock_client = MagicMock()
    mock_client.update_phase_field = AsyncMock(
        return_value={"updatePhaseField": {"phase_field": {"id": "429358624"}}}
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "field",
                "update",
                "priority",
                "--extra",
                '{"label": "Priority", "phase_id": "343162749"}',
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout
    mock_client.update_phase_field.assert_awaited_once_with(
        "priority", label="Priority", phase_id="343162749"
    )


def test_field_delete_yes(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("fld-del")
    mock_client = MagicMock()
    mock_client.delete_phase_field = AsyncMock(return_value={"deletePhaseField": {}})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["field", "delete", "fid-1", "--yes", "--json"],
        )
    assert result.exit_code == 0
    mock_client.delete_phase_field.assert_awaited_once_with("fid-1", pipe_uuid=None)
