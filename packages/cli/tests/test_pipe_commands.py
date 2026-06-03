"""Tests for ``pipefy pipe`` subcommands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_cli.main import app


def test_pipe_get_rejects_option_like_positional_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("pipe-get-bad-opt")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["pipe", "get", "--bad", "--json"])
    assert result.exit_code == 2
    mock_client.get_pipe.assert_not_called()


def test_table_delete_accepts_leading_hyphen_table_id(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("table-del-hyphen")
    mock_client = MagicMock()
    mock_client.delete_table = AsyncMock(
        return_value={"deleteTable": {"success": True}}
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["table", "delete", "-ZocGcM0", "--yes", "--json"],
        )
    assert result.exit_code == 0, result.stderr
    mock_client.delete_table.assert_awaited_once_with("-ZocGcM0")


def test_pipe_get_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("pipe-get")
    payload = {"pipe": {"id": "10", "name": "P"}}
    mock_client = MagicMock()
    mock_client.get_pipe = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["pipe", "get", "10", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == payload
    mock_client.get_pipe.assert_awaited_once_with("10")


def test_pipe_get_json_includes_phase_inventory_fields(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("pipe-get-inventory")
    payload = {
        "pipe": {
            "id": "10",
            "name": "P",
            "startFormPhaseId": "100",
            "start_form_phase": {"id": "100", "name": "Start", "cards_count": 1},
            "phases": [{"id": "200", "name": "Done", "cards_count": 3}],
        }
    }
    mock_client = MagicMock()
    mock_client.get_pipe = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["pipe", "get", "10", "--json"])
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["pipe"]["start_form_phase"]["cards_count"] == 1
    assert body["pipe"]["phases"][0]["cards_count"] == 3


def test_pipe_list_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("pipe-list")
    payload = {"organizations": []}
    mock_client = MagicMock()
    mock_client.search_pipes = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["pipe", "list", "--name", "Invoices", "--max-per-org", "50", "--json"],
        )
    assert result.exit_code == 0
    mock_client.search_pipes.assert_awaited_once_with(
        "Invoices",
        max_pipes_per_org=50,
    )


def test_pipe_create_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("pipe-create")
    payload = {"createPipe": {"pipe": {"id": "99"}}}
    mock_client = MagicMock()
    mock_client.create_pipe = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["pipe", "create", "My Pipe", "--org", "555", "--json"],
        )
    assert result.exit_code == 0
    mock_client.create_pipe.assert_awaited_once_with("My Pipe", "555")


def test_pipe_create_whitespace_name_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("pipe-bad-name")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["pipe", "create", "   ", "--org", "1", "--json"])
    assert result.exit_code == 2
    mock_client.create_pipe.assert_not_called()


def test_pipe_update_preferences_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("pipe-upd")
    payload = {"updatePipe": {"pipe": {"id": "10"}}}
    mock_client = MagicMock()
    mock_client.update_pipe = AsyncMock(return_value=payload)
    prefs = {"foo": "bar"}
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "pipe",
                "update",
                "10",
                "--preferences",
                json.dumps(prefs),
                "--json",
            ],
        )
    assert result.exit_code == 0
    mock_client.update_pipe.assert_awaited_once_with(
        "10", name=None, icon=None, color=None, preferences=prefs
    )


def test_pipe_update_no_attributes_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("pipe-upd-none")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["pipe", "update", "10", "--json"])
    assert result.exit_code == 2
    mock_client.update_pipe.assert_not_called()


def test_pipe_delete_yes(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("pipe-del")
    payload = {"deletePipe": {"success": True}}
    mock_client = MagicMock()
    mock_client.delete_pipe = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["pipe", "delete", "10", "--yes", "--json"])
    assert result.exit_code == 0
    mock_client.delete_pipe.assert_awaited_once_with("10")


def test_pipe_clone_with_org(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("pipe-clone")
    payload = {"clonePipes": {}}
    mock_client = MagicMock()
    mock_client.clone_pipe = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["pipe", "clone", "301", "--org", "777", "--json"],
        )
    assert result.exit_code == 0
    mock_client.clone_pipe.assert_awaited_once_with(
        "301",
        organization_id="777",
    )


def test_pipe_clone_without_org_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("pipe-clone-no-org")
    payload = {"clonePipes": {}}
    mock_client = MagicMock()
    mock_client.clone_pipe = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["pipe", "clone", "301", "--json"])
    assert result.exit_code == 0
    mock_client.clone_pipe.assert_awaited_once_with(
        "301",
        organization_id=None,
    )


def test_pipe_update_preferences_empty_object_bad_parameter(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("pipe-upd-empty-pref")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["pipe", "update", "10", "--preferences", "{}", "--json"],
        )
    assert result.exit_code == 2
    mock_client.update_pipe.assert_not_called()


def test_phase_allowed_moves_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("ph-allowed-moves")
    payload = {
        "phase": {
            "id": "342182335",
            "name": "Doing",
            "cards_can_be_moved_to_phases": [{"id": "200", "name": "Done"}],
        }
    }
    mock_client = MagicMock()
    mock_client.get_phase_allowed_move_targets = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["phase", "allowed-moves", "342182335", "--json"],
        )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == payload
    mock_client.get_phase_allowed_move_targets.assert_awaited_once_with("342182335")


def test_phase_cards_count_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("ph-cards-count")
    payload = {
        "phase_id": "342182335",
        "phase_name": "Doing",
        "cards_count": 7,
    }
    mock_client = MagicMock()
    mock_client.get_phase_cards_count_payload = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["phase", "cards-count", "342182335", "--json"],
        )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == payload
    mock_client.get_phase_cards_count_payload.assert_awaited_once_with("342182335")


def test_phase_cards_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("ph-cards-list")
    payload = {
        "phase": {
            "id": "342182335",
            "cards": {
                "edges": [{"node": {"id": "1", "title": "A"}}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "totalCount": 1,
            },
        }
    }
    mock_client = MagicMock()
    mock_client.get_phase_cards = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["phase", "cards", "342182335", "--first", "50", "--after", "c1", "--json"],
        )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == payload
    mock_client.get_phase_cards.assert_awaited_once_with(
        "342182335",
        first=50,
        after="c1",
        include_fields=False,
    )
