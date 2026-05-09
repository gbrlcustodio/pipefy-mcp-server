"""Pytest fixtures for ``pipefy-cli``."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

_PIPEFY_ENV_KEYS = (
    "PIPEFY_GRAPHQL_URL",
    "PIPEFY_INTERNAL_API_URL",
    "PIPEFY_OAUTH_URL",
    "PIPEFY_OAUTH_CLIENT",
    "PIPEFY_OAUTH_SECRET",
    "PIPEFY_ALLOW_INSECURE_URLS",
    "PIPEFY_TOKEN",
    "PIPEFY_SERVICE_ACCOUNT_IDS",
    "PIPEFY_PERMISSION_DENIED_ENRICHMENT_TIMEOUT_SECONDS",
    "PIPEFY_GQL_REUSE_FETCHED_GRAPHQL_SCHEMA",
    "PIPEFY_DEFAULT_WEBHOOK_NAME",
    "PIPEFY_MCP_UNIFIED_ENVELOPE",
)


@pytest.fixture
def clean_pipefy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove canonical ``PIPEFY_*`` keys so each test controls env explicitly."""

    for key in _PIPEFY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def saved_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Run with cwd under ``tmp_path`` (no repo ``.env`` leakage)."""

    monkeypatch.chdir(tmp_path)
    yield tmp_path


@pytest.fixture
def runner() -> CliRunner:
    """Typer CLI runner with stderr separated from stdout."""

    return CliRunner(mix_stderr=False)


@pytest.fixture(autouse=True)
def _reset_cli_auth_cache() -> None:
    """Avoid leaking :func:`get_authenticated_client` memoization across tests."""

    from pipefy_cli.auth import clear_authenticated_client_cache

    clear_authenticated_client_cache()
    yield
    clear_authenticated_client_cache()
