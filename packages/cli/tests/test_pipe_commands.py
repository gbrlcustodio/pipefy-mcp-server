"""Tests for ``pipefy pipe`` subcommands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_cli.main import app


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
