"""Optional live CLI smoke tests (one read per domain when env IDs are present)."""

from __future__ import annotations

import os

import pytest
from _shared.live_settings import require_live_creds
from typer.testing import CliRunner

from pipefy_cli.main import app


def _pipe_id() -> str | None:
    return os.environ.get("PIPE_BUILDING_LIVE_PIPE_ID")


def _phase_id() -> str | None:
    return os.environ.get("PIPE_FIELD_CONDITION_LIVE_PHASE_ID")


# Tests do not chdir to ``tmp_path`` and do not override ``env=`` on
# ``runner.invoke`` so the CLI loads ``.env`` from the repo root via
# ``load_deployment`` (the same source ``require_live_creds`` reads).


@pytest.mark.integration
def test_cli_live_card_list_skips_without_pipe_id():
    require_live_creds()
    if not _pipe_id():
        pytest.skip("Set PIPE_BUILDING_LIVE_PIPE_ID for card list live smoke.")
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(
        app,
        ["card", "list", "--pipe", _pipe_id(), "--first", "1", "--json"],
    )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")


@pytest.mark.integration
def test_cli_live_pipe_get_skips_without_pipe_id():
    require_live_creds()
    if not _pipe_id():
        pytest.skip("Set PIPE_BUILDING_LIVE_PIPE_ID for pipe get live smoke.")
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(app, ["pipe", "get", _pipe_id(), "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")


@pytest.mark.integration
def test_cli_live_pipe_list_requires_only_oauth():
    require_live_creds()
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(app, ["pipe", "list", "--max-per-org", "1", "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")


@pytest.mark.integration
def test_cli_live_label_list_skips_without_pipe_id():
    require_live_creds()
    if not _pipe_id():
        pytest.skip("Set PIPE_BUILDING_LIVE_PIPE_ID for label list live smoke.")
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(app, ["label", "list", "--pipe", _pipe_id(), "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")


@pytest.mark.integration
def test_cli_live_webhook_list_skips_without_pipe_id():
    require_live_creds()
    if not _pipe_id():
        pytest.skip("Set PIPE_BUILDING_LIVE_PIPE_ID for webhook list live smoke.")
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(app, ["webhook", "list", "--pipe", _pipe_id(), "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")


@pytest.mark.integration
def test_cli_live_member_list_skips_without_pipe_id():
    require_live_creds()
    if not _pipe_id():
        pytest.skip("Set PIPE_BUILDING_LIVE_PIPE_ID for member list live smoke.")
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(app, ["member", "list", "--pipe", _pipe_id(), "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")


@pytest.mark.integration
def test_cli_live_relation_pipe_list_skips_without_pipe_id():
    require_live_creds()
    if not _pipe_id():
        pytest.skip("Set PIPE_BUILDING_LIVE_PIPE_ID for relation pipe list live smoke.")
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(app, ["relation", "pipe", "list", _pipe_id(), "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")


@pytest.mark.integration
def test_cli_live_table_list_requires_only_oauth():
    require_live_creds()
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(app, ["table", "list", "--first", "1", "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")


@pytest.mark.integration
def test_cli_live_phase_get_skips_without_phase_id():
    require_live_creds()
    if not _phase_id():
        pytest.skip("Set PIPE_FIELD_CONDITION_LIVE_PHASE_ID for phase get live smoke.")
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(app, ["phase", "get", _phase_id(), "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")


@pytest.mark.integration
def test_cli_live_field_list_skips_without_phase_id():
    require_live_creds()
    if not _phase_id():
        pytest.skip("Set PIPE_FIELD_CONDITION_LIVE_PHASE_ID for field list live smoke.")
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(app, ["field", "list", "--phase", _phase_id(), "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")


@pytest.mark.integration
def test_cli_live_record_find_skips_without_table_id():
    require_live_creds()
    table_id = os.environ.get("CLI_LIVE_TABLE_ID")
    if not table_id:
        pytest.skip("Set CLI_LIVE_TABLE_ID for record find live smoke.")
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(
        app,
        ["record", "find", "--table", table_id, "--first", "1", "--json"],
    )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
