"""CLI tests for audit, automation, export, graphql, and introspect commands."""

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
    mock_client.upload_attachment.assert_not_called()


def test_attachment_upload_rejects_oversize_file(
    runner: CliRunner,
    clean_pipefy_env,
    saved_cwd,
    oauth_env,
    tmp_path: Path,
):
    """Files over the cap surface a BadParameter via step=file_read."""
    from pipefy_infra.filesystem import LocalFileError
    from pipefy_sdk import AttachmentUploadError

    oauth_env("att-size")
    f = tmp_path / "big.bin"
    f.write_bytes(b"more-than-ten-bytes")
    mock_client = MagicMock()
    cause = LocalFileError(f"File too large: {f} is 19 bytes, exceeding the 0 MiB cap.")
    exc = AttachmentUploadError(str(cause), step="file_read")
    exc.__cause__ = cause
    mock_client.upload_attachment = AsyncMock(side_effect=exc)

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
                "--card",
                "10",
                "--organization",
                "1",
                "--field",
                "f",
            ],
        )
    assert r.exit_code == 2
    assert "too large" in (r.stdout + (r.stderr or "")).lower()


def test_attachment_upload_card_file_path_passes_tilde_through(
    runner: CliRunner,
    clean_pipefy_env,
    saved_cwd,
    oauth_env,
    tmp_path: Path,
):
    """``--file ~/<name>`` is passed to the service unmodified; expansion is the service's job."""
    from pipefy_sdk import CardTarget

    oauth_env("att-tilde")

    mock_client = MagicMock()
    captured: dict = {}

    async def _capture(attachment, *, organization_id, target):
        captured["attachment"] = attachment
        captured["organization_id"] = organization_id
        captured["target"] = target
        return {
            "file_name": "tilde.bin",
            "content_type": "application/octet-stream",
            "file_size": 10,
            "field_id": target.field_id,
            "storage_path": "org/x/key",
            "download_url": "https://dl",
        }

    mock_client.upload_attachment = AsyncMock(side_effect=_capture)

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
                "~/tilde.bin",
                "--json",
            ],
        )
    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    out = json.loads(r.stdout)
    assert out["success"] is True
    assert str(captured["attachment"].path) == "~/tilde.bin"
    assert isinstance(captured["target"], CardTarget)


def test_attachment_upload_card_happy_path_json(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env, tmp_path: Path
):
    from pipefy_sdk import CardTarget

    oauth_env("att-up")
    p = tmp_path / "a.txt"
    p.write_text("hi", encoding="utf-8")
    mock_client = MagicMock()
    captured: dict = {}

    async def _capture(attachment, *, organization_id, target):
        captured["attachment"] = attachment
        captured["target"] = target
        return {
            "file_name": "a.txt",
            "content_type": "text/plain",
            "file_size": 2,
            "field_id": target.field_id,
            "storage_path": "org/x/key",
            "download_url": "https://dl",
        }

    mock_client.upload_attachment = AsyncMock(side_effect=_capture)

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
    assert captured["attachment"].path == p
    assert isinstance(captured["target"], CardTarget)
    assert captured["target"].card_id == "10"
    assert captured["target"].field_id == "doc"


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
        "pipefy_cli.commands._common.get_authenticated_client",
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
        "pipefy_cli.commands._common.get_authenticated_client",
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
        "pipefy_cli.commands._common.get_authenticated_client",
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
        "pipefy_cli.commands._common.get_authenticated_client",
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
        "pipefy_cli.commands._common.get_authenticated_client",
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
        "pipefy_cli.commands._common.get_authenticated_client",
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


def test_report_pipe_export_csv_streams_bytes_to_stdout(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    """``report-pipe export --format csv`` runs start → poll → stream end-to-end."""
    oauth_env("rpcsv-stream")
    mock_client = MagicMock()
    mock_client.export_pipe_report = AsyncMock(
        return_value={"exportPipeReport": {"pipeReportExport": {"id": "exp-77"}}}
    )
    mock_client.get_pipe_report_export = AsyncMock(
        return_value={
            "pipeReportExport": {"state": "done", "fileURL": "https://example/r.csv"}
        }
    )

    async def fake_stream(url, *, max_bytes):
        for chunk in (b"id,name\n", b"1,foo\n", b"2,bar\n"):
            yield chunk

    with (
        patch(
            "pipefy_cli.commands._common.get_authenticated_client",
            return_value=mock_client,
        ),
        patch("pipefy_cli.commands._common.stream_bytes", new=fake_stream),
    ):
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
                "--poll-timeout",
                "2.0",
            ],
        )

    assert r.exit_code == 0, r.stderr
    # stdout in Typer's CliRunner is captured as text; the CSV bytes are decodable as utf-8.
    assert r.stdout == "id,name\n1,foo\n2,bar\n"
    mock_client.export_pipe_report.assert_awaited_once()
    mock_client.get_pipe_report_export.assert_awaited_once_with("exp-77")


def test_report_pipe_export_csv_exits_1_when_export_id_missing(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    """When the start mutation returns no export id, the CLI exits with code 1."""
    oauth_env("rpcsv-noid")
    mock_client = MagicMock()
    mock_client.export_pipe_report = AsyncMock(
        return_value={"exportPipeReport": {"pipeReportExport": {}}}
    )

    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
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
            ],
        )

    assert r.exit_code == 1
    assert "export id" in r.stderr.lower()


def test_report_pipe_export_csv_exits_1_when_poll_reports_failed(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    """Failed export state surfaces as exit 1 with a stderr message (no traceback)."""
    oauth_env("rpcsv-fail")
    mock_client = MagicMock()
    mock_client.export_pipe_report = AsyncMock(
        return_value={"exportPipeReport": {"pipeReportExport": {"id": "exp-f"}}}
    )
    mock_client.get_pipe_report_export = AsyncMock(
        return_value={"pipeReportExport": {"state": "failed"}}
    )

    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
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
                "--poll-timeout",
                "2.0",
            ],
        )

    assert r.exit_code == 1
    assert "failed" in r.stderr.lower()
    mock_client.export_pipe_report.assert_awaited_once()


def test_report_org_export_csv_exits_1_when_poll_reports_failed(
    runner: CliRunner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("rocsv-fail")
    mock_client = MagicMock()
    mock_client.export_organization_report = AsyncMock(
        return_value={
            "exportOrganizationReport": {"organizationReportExport": {"id": "exp-o"}}
        }
    )
    mock_client.get_organization_report_export = AsyncMock(
        return_value={"organizationReportExport": {"state": "failed"}}
    )

    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        r = runner.invoke(
            app,
            [
                "report-org",
                "export",
                "--organization",
                "org1",
                "--organization-report-id",
                "rep1",
                "--format",
                "csv",
                "--poll-timeout",
                "2.0",
            ],
        )

    assert r.exit_code == 1
    assert "failed" in r.stderr.lower()
