"""Tests for ``pipefy table field`` subcommands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_cli.main import app


def test_table_field_create_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("tbl-field-create")
    payload = {"table_field": {"id": "f1"}}
    mock_client = MagicMock()
    mock_client.create_table_field = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "table",
                "field",
                "create",
                "42",
                "--label",
                "Phone",
                "--type",
                "phone",
                "--json",
            ],
        )
    assert result.exit_code == 0
    mock_client.create_table_field.assert_awaited_once_with("42", "Phone", "phone")


def test_table_field_update_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("tbl-field-update")
    payload = {"table_field": {"id": "f1", "label": "Phone 2"}}
    mock_client = MagicMock()
    mock_client.update_table_field = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "table",
                "field",
                "update",
                "f1",
                "--table",
                "42",
                "--label",
                "Phone 2",
                "--json",
            ],
        )
    assert result.exit_code == 0
    mock_client.update_table_field.assert_awaited_once_with(
        "f1", table_id="42", label="Phone 2"
    )


def test_table_field_delete_yes(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("tbl-field-delete")
    payload = {"deleteTableField": {"success": True}}
    mock_client = MagicMock()
    mock_client.delete_table_field = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "table",
                "field",
                "delete",
                "f1",
                "--table",
                "42",
                "--yes",
                "--json",
            ],
        )
    assert result.exit_code == 0
    mock_client.delete_table_field.assert_awaited_once_with("f1", "42")


def test_table_field_delete_aborts_when_user_denies_confirm(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("tbl-field-delete-deny")
    mock_client = MagicMock()
    mock_client.delete_table_field = AsyncMock(return_value={"deleteTableField": {}})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "table",
                "field",
                "delete",
                "f1",
                "--table",
                "42",
                "--json",
            ],
            input="n\n",
        )
    assert result.exit_code != 0
    mock_client.delete_table_field.assert_not_called()
