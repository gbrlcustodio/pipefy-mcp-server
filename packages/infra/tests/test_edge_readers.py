"""Tests for the ``read_client_env`` / ``read_auth_env`` edge readers.

These return raw mappings for the application edge to feed into the pure domain
value objects. They own the ``PIPEFY_*`` env-name contract; they run no SSRF /
shape gate and import no domain type.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipefy_infra.config import read_auth_env, read_client_env

_PIPEFY_ENV_VARS = (
    "PIPEFY_BASE_URL",
    "PIPEFY_ALLOW_INSECURE_URLS",
    "PIPEFY_GQL_REUSE_FETCHED_GRAPHQL_SCHEMA",
    "PIPEFY_DEFAULT_WEBHOOK_NAME",
    "PIPEFY_AUTH_ISSUER_URL",
    "PIPEFY_AUTH_CLIENT_ID",
    "PIPEFY_AUTH_DISABLE_STORED_SESSION",
    "PIPEFY_AUTH_KEYCHAIN_BACKEND",
    "PIPEFY_TOKEN",
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID",
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET",
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Point TOML at a nonexistent file and clear the PIPEFY_* surface so each
    # test starts from a known-empty environment.
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "absent.toml"))
    for var in _PIPEFY_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_empty_env_yields_empty_mappings() -> None:
    # exclude_unset: with nothing set, the value objects supply every default.
    assert read_client_env() == {}
    assert read_auth_env() == {}


def test_client_env_reads_only_set_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://staging.example.com")
    monkeypatch.setenv("PIPEFY_DEFAULT_WEBHOOK_NAME", "hook")
    assert read_client_env() == {
        "base_url": "https://staging.example.com",
        "default_webhook_name": "hook",
    }


def test_client_env_flags_override_env_and_strip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://from-env.example.com")
    result = read_client_env(
        base_url="  https://from-flag.example.com  ", allow_insecure=True
    )
    assert result == {
        "base_url": "https://from-flag.example.com",
        "allow_insecure_urls": True,
    }


def test_auth_env_reads_credentials_under_canonical_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPEFY_TOKEN", "tok")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")
    monkeypatch.setenv("PIPEFY_AUTH_ISSUER_URL", "https://idp.example.com/realms/x")
    assert read_auth_env() == {
        "static_token": "tok",
        "service_account_client_id": "cid",
        "service_account_client_secret": "sec",
        "issuer_url": "https://idp.example.com/realms/x",
    }


def test_auth_env_omits_base_url_and_insecure_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # base_url / allow_insecure_urls are injected by the caller, never read here.
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://staging.example.com")
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "true")
    assert read_auth_env() == {}


def test_readers_pick_up_toml_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        'base_url = "https://toml.example.com"\nissuer_url = "https://toml-idp.example.com"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(config))
    assert read_client_env()["base_url"] == "https://toml.example.com"
    assert read_auth_env()["issuer_url"] == "https://toml-idp.example.com"
