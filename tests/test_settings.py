"""Tests for ``Settings`` / ``PipefySettings`` (env loading and coercion)."""

import pytest

from pipefy_mcp.settings import PipefySettings, Settings


@pytest.mark.unit
def test_service_account_ids_defaults_to_empty_list():
    assert PipefySettings().service_account_ids == []


@pytest.mark.unit
def test_service_account_ids_accepts_list_and_strips_whitespace():
    settings = PipefySettings(service_account_ids=["  id1  ", "id2"])
    assert settings.service_account_ids == ["id1", "id2"]


@pytest.mark.unit
def test_service_account_ids_accepts_comma_separated_string():
    settings = PipefySettings(service_account_ids="alpha, beta ,gamma")
    assert settings.service_account_ids == ["alpha", "beta", "gamma"]


@pytest.mark.unit
def test_service_account_ids_from_env_comma_separated(monkeypatch):
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_IDS", "user-1,user-2, user-3 ")
    settings = Settings()
    assert settings.pipefy.service_account_ids == ["user-1", "user-2", "user-3"]


@pytest.mark.unit
def test_service_account_ids_empty_env_is_empty_list(monkeypatch):
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_IDS", "")
    settings = Settings()
    assert settings.pipefy.service_account_ids == []


@pytest.mark.unit
def test_pipefy_settings_rejects_http_graphql_when_secure():
    with pytest.raises(ValueError, match="graphql_url.*HTTPS"):
        PipefySettings(
            graphql_url="http://app.pipefy.com/graphql",
            oauth_url="https://auth.pipefy.com/oauth/token",
            internal_api_url="https://app.pipefy.com/internal_api",
        )


@pytest.mark.unit
def test_pipefy_settings_rejects_loopback_graphql():
    with pytest.raises(ValueError, match="graphql_url.*localhost|127"):
        PipefySettings(
            graphql_url="https://127.0.0.1/graphql",
            oauth_url="https://auth.pipefy.com/oauth/token",
            internal_api_url="https://app.pipefy.com/internal_api",
        )


@pytest.mark.unit
def test_pipefy_settings_allow_insecure_urls_permits_http_localhost():
    s = PipefySettings(
        allow_insecure_urls=True,
        graphql_url="http://localhost/graphql",
        oauth_url="http://localhost/oauth/token",
        internal_api_url="http://localhost/internal_api",
    )
    assert s.graphql_url == "http://localhost/graphql"


@pytest.mark.unit
def test_allow_insecure_urls_from_env(monkeypatch):
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "true")
    settings = Settings()
    assert settings.pipefy.allow_insecure_urls is True
