"""Tests for ``pipefy_infra.deployment.DeploymentConfig`` (pure value object)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipefy_infra.deployment import DEFAULT_BASE_URL, DeploymentConfig


def test_defaults_to_production_host() -> None:
    config = DeploymentConfig()
    assert config.base_url == DEFAULT_BASE_URL
    assert config.allow_insecure_urls is False


def test_derived_endpoints_are_base_url_suffixes() -> None:
    config = DeploymentConfig(base_url="https://example.test")
    assert config.graphql_url == "https://example.test/graphql"
    assert config.internal_api_url == "https://example.test/internal_api"
    assert config.interfaces_graphql_url == "https://example.test/graphql/interfaces"
    assert config.oauth_token_url == "https://example.test/oauth/token"


def test_trailing_slash_does_not_double_up_in_derived_urls() -> None:
    config = DeploymentConfig(base_url="https://example.test/")
    assert config.graphql_url == "https://example.test/graphql"
    assert config.oauth_token_url == "https://example.test/oauth/token"


def test_surrounding_whitespace_is_stripped() -> None:
    config = DeploymentConfig(base_url="  https://example.test  ")
    assert config.base_url == "https://example.test"


def test_non_root_path_is_rejected() -> None:
    with pytest.raises(ValidationError, match="host root"):
        DeploymentConfig(base_url="https://example.test/api")


def test_query_or_fragment_is_rejected() -> None:
    with pytest.raises(ValidationError, match="host root"):
        DeploymentConfig(base_url="https://example.test/?a=1")


def test_http_rejected_by_default() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        DeploymentConfig(base_url="http://example.test")


def test_internal_host_rejected_by_default() -> None:
    with pytest.raises(ValidationError, match="blocked range"):
        DeploymentConfig(base_url="https://127.0.0.1")


def test_allow_insecure_permits_http_and_loopback() -> None:
    config = DeploymentConfig(base_url="http://127.0.0.1", allow_insecure_urls=True)
    assert config.base_url == "http://127.0.0.1"
    assert config.graphql_url == "http://127.0.0.1/graphql"
