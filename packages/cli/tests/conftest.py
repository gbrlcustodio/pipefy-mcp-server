"""Pytest fixtures for ``pipefy-cli``."""

from __future__ import annotations

import keyring
import keyring.backend
import pytest
from typer.testing import CliRunner

_PIPEFY_ENV_KEYS = (
    "PIPEFY_BASE_URL",
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID",
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET",
    # Legacy aliases — kept so tests that opt into back-compat coverage start
    # from a clean slate even when the dropped names linger in the developer
    # shell.
    "PIPEFY_OAUTH_CLIENT",
    "PIPEFY_OAUTH_SECRET",
    "PIPEFY_ALLOW_INSECURE_URLS",
    "PIPEFY_TOKEN",
    "PIPEFY_PERMISSION_DENIED_ENRICHMENT_TIMEOUT_SECONDS",
    "PIPEFY_GQL_REUSE_FETCHED_GRAPHQL_SCHEMA",
    "PIPEFY_DEFAULT_WEBHOOK_NAME",
    "PIPEFY_MCP_UNIFIED_ENVELOPE",
    "PIPEFY_ORG_ID",
    "PIPEFY_AUTH_URL",
    "PIPEFY_AUTH_CLIENT_ID",
    "PIPEFY_DISABLE_STORED_SESSION",
    "PIPEFY_KEYCHAIN_BACKEND",
)


@pytest.fixture
def oauth_env(monkeypatch: pytest.MonkeyPatch):
    """Set minimal service-account + GraphQL URLs for CLI commands that require client-credentials mode."""

    def _set(host: str) -> None:
        monkeypatch.setenv("PIPEFY_BASE_URL", f"https://{host}.example.com")
        monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
        monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")

    return _set


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


class InMemoryKeyring(keyring.backend.KeyringBackend):
    """In-memory keyring backend that mirrors the real-world ``delete_password``
    contract (raises ``PasswordDeleteError`` when the entry is missing)."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        from keyring.errors import PasswordDeleteError

        if (service, username) not in self._store:
            raise PasswordDeleteError(f"no entry for {service}/{username}")
        del self._store[(service, username)]


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> InMemoryKeyring:
    """Patch the ``keyring`` module surface our storage code uses."""

    fake = InMemoryKeyring()
    monkeypatch.setattr(keyring, "_keyring_backend", fake, raising=False)
    monkeypatch.setattr(keyring, "get_keyring", lambda: fake)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)
    return fake
