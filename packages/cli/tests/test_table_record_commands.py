"""Tests for ``pipefy table`` and ``pipefy record`` subcommands."""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_cli.main import app

# Rich/Typer renders option names like ``--ids`` in bold by default, splitting
# the two dashes with ``\x1b[1m`` ANSI codes on Linux CI runners under
# ``FORCE_COLOR=1``. Strip those codes before the substring assert so the test
# passes on both macOS and Linux without depending on env vars.
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def test_table_list_search_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("tbl-list")
    payload = {"organizations": []}
    mock_client = MagicMock()
    mock_client.search_tables = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app, ["table", "list", "--name", "Assets", "--first", "20", "--json"]
        )
    assert result.exit_code == 0
    mock_client.search_tables.assert_awaited_once_with("Assets", first=20)


def test_table_list_with_ids_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("tbl-ids")
    payload = {"tables": []}
    mock_client = MagicMock()
    mock_client.get_tables = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["table", "list", "--ids", "10,20", "--json"])
    assert result.exit_code == 0
    mock_client.get_tables.assert_awaited_once_with(["10", "20"])


def test_table_list_ids_only_commas_bad_parameter(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("tbl-bad-ids")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["table", "list", "--ids", ",", "--json"])
    assert result.exit_code == 2
    assert "--ids must list" in _ANSI_ESCAPE_RE.sub("", result.stdout + result.stderr)
    mock_client.get_tables.assert_not_called()


def test_record_find_by_field_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("rec-find")
    payload = {"findRecords": {}}
    mock_client = MagicMock()
    mock_client.find_records = AsyncMock(return_value=payload)
    filt = json.dumps({"field_id": "f1", "field_value": "abc"})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["record", "find", "--table", "99", "--filter", filt, "--json"],
        )
    assert result.exit_code == 0
    mock_client.find_records.assert_awaited_once_with(
        "99", "f1", "abc", first=None, after=None
    )


def test_record_find_filter_field_mismatch_bad_parameter(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("rec-bad-filt")
    mock_client = MagicMock()
    filt = json.dumps({"field_id": "f1"})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["record", "find", "--table", "99", "--filter", filt, "--json"],
        )
    assert result.exit_code == 2
    mock_client.find_records.assert_not_called()


def test_record_find_list_page_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("rec-page")
    payload = {"table_records": {}}
    mock_client = MagicMock()
    mock_client.get_table_records = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["record", "find", "--table", "99", "--first", "10", "--json"],
        )
    assert result.exit_code == 0
    mock_client.get_table_records.assert_awaited_once_with("99", first=10, after=None)


def test_record_update_set_field_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("rec-set")
    mock_client = MagicMock()
    mock_client.set_table_record_field_value = AsyncMock(
        return_value={"setTableRecordFieldValue": {}}
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "record",
                "update",
                "501",
                "--field-id",
                "f2",
                "--value",
                '"hello"',
                "--json",
            ],
        )
    assert result.exit_code == 0
    mock_client.set_table_record_field_value.assert_awaited_once_with(
        "501", "f2", "hello"
    )


def test_table_delete_accepts_leading_dash_id(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    """Pipefy can encode table ids with a leading ``-`` (e.g. ``-ZocGcM0``).

    ``context_settings={"ignore_unknown_options": True}`` keeps Click from
    treating that token as a short option so the positional id parses cleanly.
    """
    oauth_env("tbl-dash-id")
    mock_client = MagicMock()
    mock_client.delete_table = AsyncMock(
        return_value={"deleteTable": {"success": True}}
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["table", "delete", "-ZocGcM0", "--yes", "--json"])
    assert result.exit_code == 0, result.stderr
    mock_client.delete_table.assert_awaited_once_with("-ZocGcM0")


def test_record_update_unknown_field_key_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("rec-upd-bad")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "record",
                "update",
                "501",
                "--fields",
                '{"unknown_key": 1}',
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.update_table_record.assert_not_called()
