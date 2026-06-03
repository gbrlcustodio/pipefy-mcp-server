"""Tests for ``pipefy label`` and ``pipefy webhook`` subcommands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_cli.main import app


def test_label_list_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("lbl")
    mock_client = MagicMock()
    mock_client.get_pipe = AsyncMock(
        return_value={"pipe": {"labels": [{"id": "1", "name": "Bug"}]}}
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["label", "list", "--pipe", "8", "--json"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["success"] is True
    assert out["message"] == "Labels loaded."
    assert out["labels"] == [{"id": "1", "name": "Bug"}]


def test_label_create_rejects_color_name_before_api(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("lbl-create-hex")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "label",
                "create",
                "--pipe",
                "8",
                "--name",
                "Bug",
                "--color",
                "red",
            ],
        )
    assert result.exit_code == 2
    assert "expected #RRGGBB, received 'red'" in result.stderr
    mock_client.create_label.assert_not_called()


def test_label_create_passes_normalized_hex(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("lbl-create-ok")
    mock_client = MagicMock()
    mock_client.create_label = AsyncMock(return_value={"createLabel": {}})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "label",
                "create",
                "--pipe",
                "8",
                "--name",
                "Bug",
                "--color",
                "#ff0000",
                "--json",
            ],
        )
    assert result.exit_code == 0
    mock_client.create_label.assert_awaited_once_with("8", "Bug", "#FF0000")


def test_label_update_rejects_color_name_before_api(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("lbl-update-hex")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "label",
                "update",
                "3",
                "--name",
                "Story",
                "--color",
                "blue",
            ],
        )
    assert result.exit_code == 2
    assert "expected #RRGGBB, received 'blue'" in result.stderr
    mock_client.update_label.assert_not_called()


def test_label_list_pipe_denied_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("lbl-denied")
    mock_client = MagicMock()
    mock_client.get_pipe = AsyncMock(return_value={"pipe": None})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["label", "list", "--pipe", "8", "--json"])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["success"] is False
    assert "error" in out


def test_webhook_create_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("wh")
    mock_client = MagicMock()
    mock_client.create_webhook = AsyncMock(return_value={"createWebhook": {}})
    actions = json.dumps(["card.create"])
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "webhook",
                "create",
                "--pipe",
                "1",
                "--url",
                "https://example.com/hook",
                "--actions",
                actions,
                "--json",
            ],
        )
    assert result.exit_code == 0
    mock_client.create_webhook.assert_awaited_once_with(
        "1",
        "https://example.com/hook",
        ["card.create"],
    )


def test_webhook_create_actions_empty_array_bad_parameter(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("wh-bad-act")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "webhook",
                "create",
                "--pipe",
                "1",
                "--url",
                "https://example.com/hook",
                "--actions",
                "[]",
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.create_webhook.assert_not_called()


def test_webhook_update_name_whitespace_bad_parameter(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("wh-bad-name")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "webhook",
                "update",
                "w1",
                "--name",
                "   ",
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.update_webhook.assert_not_called()
