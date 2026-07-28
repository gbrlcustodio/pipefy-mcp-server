"""Tests for ``pipefy attachment`` commands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_cli.main import app

_AUTH = "pipefy_cli.commands._common.get_authenticated_client"


def _creds(monkeypatch) -> None:
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")


def test_attachment_presign_returns_target(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _creds(monkeypatch)
    target = {
        "upload_url": "https://pipefy-uploads.s3.amazonaws.com/orgs/o/uploads/u/r.pdf?X-Amz-Expires=300",
        "storage_path": "orgs/o/uploads/u/r.pdf",
        "expires_in_seconds": 300,
    }
    mock_client = MagicMock()
    mock_client.create_attachment_presigned_url = AsyncMock(return_value=target)

    with patch(_AUTH, return_value=mock_client):
        result = runner.invoke(
            app,
            ["attachment", "presign", "--org", "42", "--file-name", "r.pdf", "--json"],
        )

    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    out = json.loads(result.stdout)
    assert out["success"] is True
    assert out["storage_path"] == "orgs/o/uploads/u/r.pdf"
    assert out["upload_url"].startswith("https://pipefy-uploads.s3.amazonaws.com/")
    assert out["expires_in_seconds"] == 300
    assert "download_url" not in out
    mock_client.create_attachment_presigned_url.assert_awaited_once_with(
        organization_id="42",
        file_name="r.pdf",
        content_type=None,
        content_length=None,
    )


def test_attachment_presign_missing_file_name_exits_2(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _creds(monkeypatch)
    result = runner.invoke(app, ["attachment", "presign", "--org", "42"])
    assert result.exit_code == 2


def test_attachment_presign_blank_org_rejected(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _creds(monkeypatch)
    result = runner.invoke(
        app, ["attachment", "presign", "--org", "   ", "--file-name", "r.pdf"]
    )
    assert result.exit_code == 2
