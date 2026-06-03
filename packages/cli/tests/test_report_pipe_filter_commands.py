"""CLI tests for report-pipe filter preflight."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_sdk.report_filter_preflight import EXAMPLE_PHASE_FILTER

from pipefy_cli.main import app


def test_report_pipe_create_rejects_naive_current_phase_filter(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("report-filter-bad")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "report-pipe",
                "create",
                "--pipe",
                "123",
                "--name",
                "R",
                "--filter",
                json.dumps({"current_phase": ["1"]}),
            ],
        )
    assert result.exit_code == 2
    mock_client.create_pipe_report.assert_not_called()
    assert "top-level" in result.stderr


def test_report_pipe_create_forwards_valid_filter(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("report-filter-ok")
    filt = {
        **EXAMPLE_PHASE_FILTER,
        "queries": [{**EXAMPLE_PHASE_FILTER["queries"][0], "value": "99"}],
    }
    mock_client = MagicMock()
    mock_client.create_pipe_report = AsyncMock(
        return_value={"createPipeReport": {"pipeReport": {"id": "r1"}}}
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "report-pipe",
                "create",
                "--pipe",
                "123",
                "--name",
                "R",
                "--filter",
                json.dumps(filt),
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stderr
    mock_client.create_pipe_report.assert_awaited_once_with(
        "123",
        "R",
        fields=None,
        filter=filt,
        formulas=None,
    )


def test_report_pipe_update_rejects_invalid_filter_operator(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("report-filter-update-bad")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "report-pipe",
                "update",
                "10",
                "--filter",
                json.dumps({"operator": "xor", "queries": []}),
            ],
        )
    assert result.exit_code == 2
    mock_client.update_pipe_report.assert_not_called()
