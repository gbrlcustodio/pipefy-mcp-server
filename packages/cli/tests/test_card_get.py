"""Tests for ``pipefy card get`` (config, auth, SDK, renderers)."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from _shared.live_settings import live_pipefy_settings, require_live_creds
from pipefy_sdk import PipefyGraphQLError, PipefySettings
from pipefy_sdk.exceptions import PipefyAPIError

from pipefy_cli.main import app


def _patch_get_client(card_payload: dict):
    mock_client = MagicMock()
    mock_client.get_card = AsyncMock(return_value=card_payload)
    return (
        patch(
            "pipefy_cli.commands._common.get_authenticated_client",
            return_value=mock_client,
        ),
        mock_client,
    )


def test_card_get_json_stdout(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")

    payload = {"id": "501", "title": "Unit card"}
    patcher, mock_client = _patch_get_client(payload)
    with patcher:
        result = runner.invoke(
            app,
            ["card", "get", "501", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    out = json.loads(result.stdout)
    assert out == payload
    mock_client.get_card.assert_awaited_once_with("501", include_fields=False)


def test_card_get_rich_stdout(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")

    payload = {"id": "502", "title": "Rich card"}
    patcher, _mock_client = _patch_get_client(payload)
    with patcher:
        result = runner.invoke(app, ["card", "get", "502"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert "502" in result.stdout
    assert "Rich card" in result.stdout


def test_card_get_sdk_error_stderr_exit_1(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")

    mock_client = MagicMock()
    mock_client.get_card = AsyncMock(side_effect=PipefyAPIError("GraphQL failure"))
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["card", "get", "999", "--json"])
    assert result.exit_code == 1
    assert "GraphQL failure" in (result.stderr or "")


def test_card_get_permission_denied_hint_on_stderr(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")

    exc = PipefyGraphQLError(
        [{"message": "Forbidden", "extensions": {"code": "PERMISSION_DENIED"}}]
    )
    mock_client = MagicMock()
    mock_client.get_card = AsyncMock(side_effect=exc)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["card", "get", "501", "--json"])
    assert result.exit_code == 1
    err = result.stderr or ""
    assert "PERMISSION_DENIED" in err
    assert "deleted or is not visible" in err


def _apply_settings_to_env(monkeypatch: pytest.MonkeyPatch, s: PipefySettings) -> None:
    # Service-account credentials live on AuthSettings; the live test inherits
    # them from the operator's existing shell env. Only the API host needs to
    # flow into the subprocess CLI invocation.
    monkeypatch.setenv("PIPEFY_BASE_URL", str(s.base_url))
    if s.allow_insecure_urls:
        monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "true")


@pytest.mark.integration
def test_card_get_live_json(runner, monkeypatch, tmp_path):
    """Live ``get_card`` via CLI (OAuth); requires ``PIPEFY_CLI_LIVE_CARD_ID``."""

    require_live_creds()
    card_id = os.environ.get("PIPEFY_CLI_LIVE_CARD_ID")
    if not card_id:
        pytest.skip(
            "Set PIPEFY_CLI_LIVE_CARD_ID to a card id your service account can read"
        )
    settings = live_pipefy_settings()
    monkeypatch.chdir(tmp_path)
    _apply_settings_to_env(monkeypatch, settings)

    result = runner.invoke(
        app,
        ["card", "get", card_id.strip(), "--json"],
    )
    assert result.exit_code == 0, (result.stdout, result.stderr)
    data = json.loads(result.stdout)
    # SDK returns the raw GraphQL payload shape: {"card": {"id": "...", ...}}.
    card = data.get("card") if isinstance(data.get("card"), dict) else data
    assert card.get("id") is not None
    assert str(card["id"]) == str(card_id).strip()
