"""Unit tests for ``PipefySettings`` (defaults, env loading, SSRF validation)."""

from __future__ import annotations

import pytest
from _shared.live_settings import live_pipefy_settings

from pipefy_sdk.settings import PipefySettings

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
