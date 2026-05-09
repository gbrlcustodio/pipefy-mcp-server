"""Tests for ``pipefy_cli.auth`` (OAuth / bearer factory and CLI exits)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_sdk import PipefySettings

from pipefy_cli.auth import get_authenticated_client
from pipefy_cli.main import app


def _minimal_oauth_settings() -> PipefySettings:
    return PipefySettings(
        graphql_url="https://unit.example.com/graphql",
        internal_api_url="https://unit.example.com/internal_api",
        oauth_url="https://unit.example.com/oauth/token",
        oauth_client="cid",
        oauth_secret="csecret",
    )


def test_get_authenticated_client_passes_bearer_to_pipefy_client(clean_pipefy_env):
    settings = _minimal_oauth_settings()
    with patch("pipefy_cli.auth.PipefyClient") as mock_pc:
        mock_pc.return_value = MagicMock()
        client = get_authenticated_client(settings, bearer_token="tok")
        mock_pc.assert_called_once_with(settings, bearer_token="tok")
        assert client is mock_pc.return_value


def test_get_authenticated_client_oauth_mode_no_bearer(clean_pipefy_env):
    settings = _minimal_oauth_settings()
    with patch("pipefy_cli.auth.PipefyClient") as mock_pc:
        mock_pc.return_value = MagicMock()
        get_authenticated_client(settings)
        mock_pc.assert_called_once_with(settings)


def test_cache_returns_same_instance_for_identical_oauth_settings(clean_pipefy_env):
    settings = _minimal_oauth_settings()
    with patch("pipefy_cli.auth.PipefyClient") as mock_pc:
        mock_pc.return_value = MagicMock()
        first = get_authenticated_client(settings)
        second = get_authenticated_client(settings)
        assert first is second
        assert mock_pc.call_count == 1


def test_missing_graphql_exits_2_cli(clean_pipefy_env, saved_cwd, runner):
    result = runner.invoke(app, ["card", "get", "123"])
    assert result.exit_code == 2
    combined = (result.stderr or "") + (result.stdout or "")
    assert "docs/setup.md" in combined


def test_missing_oauth_exits_2_cli(clean_pipefy_env, saved_cwd, monkeypatch, runner):
    monkeypatch.setenv(
        "PIPEFY_GRAPHQL_URL",
        "https://oauth-missing.example.com/graphql",
    )
    result = runner.invoke(app, ["card", "get", "123"])
    assert result.exit_code == 2
    combined = (result.stderr or "") + (result.stdout or "")
    assert "docs/setup.md" in combined


def test_cli_uses_pipefy_token_env_when_no_flag(
    clean_pipefy_env, saved_cwd, monkeypatch, runner
):
    monkeypatch.setenv(
        "PIPEFY_GRAPHQL_URL",
        "https://token-env.example.com/graphql",
    )
    monkeypatch.setenv("PIPEFY_TOKEN", "secret-from-env")
    mock_client = MagicMock()
    mock_client.get_card = AsyncMock(return_value={"id": "77"})
    with patch(
        "pipefy_cli.commands.card.get_authenticated_client",
        return_value=mock_client,
    ) as mock_gc:
        result = runner.invoke(app, ["card", "get", "77"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_gc.assert_called_once()
    assert mock_gc.call_args.kwargs.get("bearer_token") == "secret-from-env"
