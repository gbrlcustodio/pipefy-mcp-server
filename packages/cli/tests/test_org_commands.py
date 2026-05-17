"""Tests for ``pipefy org`` commands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_cli.main import app


def test_org_get_uses_pipefy_org_id_when_argument_omitted(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    monkeypatch.setenv(
        "PIPEFY_GRAPHQL_URL",
        "https://cli-org-env.example.com/graphql",
    )
    monkeypatch.setenv(
        "PIPEFY_INTERNAL_API_URL",
        "https://cli-org-env.example.com/internal_api",
    )
    monkeypatch.setenv(
        "PIPEFY_OAUTH_URL",
        "https://cli-org-env.example.com/oauth/token",
    )
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "cid")
    monkeypatch.setenv("PIPEFY_OAUTH_SECRET", "sec")
    monkeypatch.setenv("PIPEFY_ORG_ID", "302398434")

    payload = {"id": "302398434", "name": "Test Org"}
    mock_client = MagicMock()
    mock_client.get_organization = AsyncMock(return_value=payload)

    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["org", "get", "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.get_organization.assert_awaited_once_with("302398434")


def test_org_get_positional_overrides_pipefy_org_id(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    monkeypatch.setenv(
        "PIPEFY_GRAPHQL_URL",
        "https://cli-org-pos.example.com/graphql",
    )
    monkeypatch.setenv(
        "PIPEFY_INTERNAL_API_URL",
        "https://cli-org-pos.example.com/internal_api",
    )
    monkeypatch.setenv(
        "PIPEFY_OAUTH_URL",
        "https://cli-org-pos.example.com/oauth/token",
    )
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "cid")
    monkeypatch.setenv("PIPEFY_OAUTH_SECRET", "sec")
    monkeypatch.setenv("PIPEFY_ORG_ID", "111")

    payload = {"id": "222", "name": "Other Org"}
    mock_client = MagicMock()
    mock_client.get_organization = AsyncMock(return_value=payload)

    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["org", "get", "222", "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.get_organization.assert_awaited_once_with("222")


def test_org_get_missing_id_and_env_exits_2(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    monkeypatch.setenv(
        "PIPEFY_GRAPHQL_URL",
        "https://cli-org-miss.example.com/graphql",
    )
    monkeypatch.setenv(
        "PIPEFY_INTERNAL_API_URL",
        "https://cli-org-miss.example.com/internal_api",
    )
    monkeypatch.setenv(
        "PIPEFY_OAUTH_URL",
        "https://cli-org-miss.example.com/oauth/token",
    )
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "cid")
    monkeypatch.setenv("PIPEFY_OAUTH_SECRET", "sec")

    result = runner.invoke(app, ["org", "get", "--json"])
    assert result.exit_code == 2
    assert "PIPEFY_ORG_ID" in (result.stderr or "")
    assert "pipe list" in (result.stderr or "")
