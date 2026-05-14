"""Tests for v0.2/v0.3 CLI domains (tasks 8.1-8.4, 9.1-9.3)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from pipefy_cli.main import app


def test_attachment_upload_requires_card_xor_record(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env, tmp_path: Path
):
    oauth_env("att-xor")
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(
            app,
            [
                "attachment",
                "upload",
                "--file",
                str(f),
                "--organization",
                "1",
                "--field",
                "f",
            ],
        )
    assert r.exit_code == 2
    mock_client.create_presigned_url.assert_not_called()


def test_attachment_upload_card_happy_path_json(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env, tmp_path: Path
):
    oauth_env("att-up")
    p = tmp_path / "a.txt"
    p.write_text("hi", encoding="utf-8")
    mock_client = MagicMock()
    mock_client.create_presigned_url = AsyncMock(
        return_value={
            "url": "https://bucket.s3.amazonaws.com/x?y=1",
            "download_url": "https://dl",
        }
    )
    mock_client.upload_file_to_s3 = AsyncMock(return_value={"status_code": 200})
    mock_client.extract_storage_path = MagicMock(return_value="org/x/key")
    mock_client.update_card_field = AsyncMock(return_value={})

    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(
            app,
            [
                "attachment",
                "upload",
                "--card",
                "10",
                "--organization",
                "1",
                "--field",
                "doc",
                "--file",
                str(p),
                "--json",
            ],
        )
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["success"] is True
    mock_client.update_card_field.assert_awaited_once()


def test_field_condition_list_json(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("fc")
    mock_client = MagicMock()
    mock_client.get_field_conditions = AsyncMock(
        return_value={"phase": {"fieldConditions": [{"id": "1"}]}}
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(app, ["field-condition", "list", "--phase", "9", "--json"])
    assert r.exit_code == 0
    body = json.loads(r.stdout)
    assert body["success"] is True
    assert body["field_conditions"] == [{"id": "1"}]


def test_email_inbox_list_json(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("em")
    mock_client = MagicMock()
    mock_client.get_card_inbox_emails = AsyncMock(return_value={"emails": []})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(app, ["email", "inbox", "list", "--card", "1", "--json"])
    assert r.exit_code == 0


def test_audit_export_writes_file(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env, tmp_path: Path
):
    oauth_env("aud")
    out = tmp_path / "a.json"
    mock_client = MagicMock()
    mock_client.export_pipe_audit_logs = AsyncMock(
        return_value={"exportPipeAuditLogsReport": {"success": True}}
    )
    with patch(
        "pipefy_cli.commands.audit.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(
            app,
            ["audit", "export", "--pipe", "uuid-1", "--output", str(out)],
        )
    assert r.exit_code == 0
    assert (
        json.loads(out.read_text(encoding="utf-8"))["exportPipeAuditLogsReport"][
            "success"
        ]
        is True
    )


def test_automation_list_json(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("au")
    mock_client = MagicMock()
    mock_client.get_automations = AsyncMock(return_value=[{"id": "1", "name": "R"}])
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(app, ["automation", "list", "--pipe", "5", "--json"])
    assert r.exit_code == 0
    assert json.loads(r.stdout) == [{"id": "1", "name": "R"}]


def test_automation_logs_requires_automation_xor_repo(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("alog")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(app, ["automation", "logs", "--json"])
    assert r.exit_code == 2


def test_introspect_type_json_default(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("intro")
    mock_client = MagicMock()
    mock_client.introspect_type = AsyncMock(return_value={"name": "Card"})
    with patch(
        "pipefy_cli.commands.introspect.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(app, ["introspect", "type", "Card"])
    assert r.exit_code == 0
    assert json.loads(r.stdout) == {"name": "Card"}


def test_graphql_exec_query_json(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("gql")
    mock_client = MagicMock()
    mock_client.execute_graphql = AsyncMock(return_value={"pipe": {"id": "1"}})
    with patch(
        "pipefy_cli.commands.graphql.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(
            app,
            [
                "graphql",
                "exec",
                "--query",
                "query Q { __typename }",
                "--vars",
                "{}",
                "--json",
            ],
        )
    assert r.exit_code == 0
    mock_client.execute_graphql.assert_awaited_once()


def test_graphql_exec_mutation_without_yes_exit_2(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("gql2")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands.graphql.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(
            app,
            [
                "graphql",
                "exec",
                "--query",
                "mutation M { __typename }",
                "--json",
            ],
        )
    assert r.exit_code == 2
    mock_client.execute_graphql.assert_not_called()


def test_graphql_exec_mutation_with_yes_calls_sdk(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("gql3")
    mock_client = MagicMock()
    mock_client.execute_graphql = AsyncMock(return_value={"ok": True})
    with patch(
        "pipefy_cli.commands.graphql.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(
            app,
            [
                "graphql",
                "exec",
                "--query",
                "mutation M { __typename }",
                "--yes",
                "--json",
            ],
        )
    assert r.exit_code == 0
    mock_client.execute_graphql.assert_awaited_once()


def test_graphql_exec_invalid_vars_exit_2(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("gql4")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands.graphql.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(
            app,
            [
                "graphql",
                "exec",
                "--query",
                "query Q { __typename }",
                "--vars",
                "not-json",
                "--json",
            ],
        )
    assert r.exit_code == 2
    mock_client.execute_graphql.assert_not_called()
