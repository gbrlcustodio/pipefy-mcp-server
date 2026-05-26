"""Unit tests for ``PipefySettings`` (defaults, env loading, SSRF validation)."""

from __future__ import annotations

import pytest
from _shared.live_settings import live_pipefy_settings

from pipefy_sdk.settings import DEFAULT_GRAPHQL_URL, PipefySettings

DEFAULT_INTERFACES_GRAPHQL_URL = "https://app.pipefy.com/graphql/interfaces"


@pytest.mark.unit
def test_pipefy_settings_interfaces_graphql_url_default():
    """``interfaces_graphql_url`` defaults to the Interfaces schema endpoint."""
    settings = PipefySettings()
    assert settings.interfaces_graphql_url == DEFAULT_INTERFACES_GRAPHQL_URL


@pytest.mark.unit
def test_pipefy_settings_interfaces_graphql_url_overridden_via_env(
    monkeypatch: pytest.MonkeyPatch,
):
    """``PIPEFY_INTERFACES_GRAPHQL_URL`` overrides ``interfaces_graphql_url``."""
    custom_url = "https://custom.pipefy.com/graphql/interfaces"
    monkeypatch.setenv("PIPEFY_INTERFACES_GRAPHQL_URL", custom_url)
    settings = live_pipefy_settings()
    assert settings.interfaces_graphql_url == custom_url


@pytest.mark.unit
def test_pipefy_settings_rejects_http_interfaces_graphql_url():
    """``interfaces_graphql_url`` must use HTTPS unless ``allow_insecure_urls``."""
    with pytest.raises(ValueError, match="interfaces_graphql_url.*HTTPS"):
        PipefySettings(
            interfaces_graphql_url="http://app.pipefy.com/graphql/interfaces",
            internal_api_url="https://app.pipefy.com/internal_api",
        )


@pytest.mark.unit
def test_pipefy_settings_graphql_url_defaults_to_pipefy_prod_endpoint(
    monkeypatch: pytest.MonkeyPatch,
):
    """``PipefySettings()`` with no ``PIPEFY_GRAPHQL_URL`` set defaults to the prod GraphQL endpoint."""
    monkeypatch.delenv("PIPEFY_GRAPHQL_URL", raising=False)
    settings = PipefySettings()
    assert settings.graphql_url == DEFAULT_GRAPHQL_URL
    assert DEFAULT_GRAPHQL_URL == "https://app.pipefy.com/graphql"


@pytest.mark.unit
def test_pipefy_settings_graphql_url_env_override_wins_over_default(
    monkeypatch: pytest.MonkeyPatch,
):
    """Setting ``PIPEFY_GRAPHQL_URL`` in env still overrides the default."""
    monkeypatch.setenv("PIPEFY_GRAPHQL_URL", "https://other.example.com/graphql")
    settings = live_pipefy_settings()
    assert settings.graphql_url == "https://other.example.com/graphql"


@pytest.mark.unit
def test_pipefy_settings_graphql_url_explicit_none_is_preserved():
    """Direct kwarg ``graphql_url=None`` opts out of the default (callers may use this for tests)."""
    settings = PipefySettings(graphql_url=None)
    assert settings.graphql_url is None
