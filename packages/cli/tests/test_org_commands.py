"""Tests for ``pipefy org`` commands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from _shared.fixture_ids import EXAMPLE_NUMERIC_ORG_ID

from pipefy_cli.main import app


def test_org_get_uses_pipefy_org_id_when_argument_omitted(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")
    monkeypatch.setenv("PIPEFY_ORG_ID", EXAMPLE_NUMERIC_ORG_ID)

    payload = {"id": EXAMPLE_NUMERIC_ORG_ID, "name": "Test Org"}
    mock_client = MagicMock()
    mock_client.get_organization = AsyncMock(return_value=payload)

    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["org", "get", "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.get_organization.assert_awaited_once_with(EXAMPLE_NUMERIC_ORG_ID)


def test_org_get_positional_overrides_pipefy_org_id(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")
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
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")

    result = runner.invoke(app, ["org", "get", "--json"])
    assert result.exit_code == 2
    assert "PIPEFY_ORG_ID" in (result.stderr or "")
    assert "pipe list" in (result.stderr or "")


def test_org_list_returns_accessible_orgs(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")

    payload = [
        {"id": "111", "name": "Org One", "role": "admin"},
        {"id": "222", "name": "Org Two", "role": "member"},
    ]
    mock_client = MagicMock()
    mock_client.list_organizations = AsyncMock(return_value=payload)

    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["org", "list", "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.list_organizations.assert_awaited_once_with()
