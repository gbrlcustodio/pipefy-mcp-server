"""Unit tests for ``SdkConfig`` (forwarding off injected DeploymentConfig, env reading).

Pure ``DeploymentConfig`` validation (defaults, derived URLs, SSRF) lives in the
infra package's ``test_deployment.py``; here we cover the SDK-specific surface:
the injected ``deployment`` is required, the URL / posture forwards resolve off
it, and the SDK's own knobs load from the environment via the reader.
"""

from __future__ import annotations

import pytest
from _shared.live_settings import live_pipefy_config
from pipefy_infra.deployment import DEFAULT_BASE_URL, DeploymentConfig
from pydantic import ValidationError

from pipefy_sdk.config import SdkConfig

PROD_GRAPHQL_URL = "https://app.pipefy.com/graphql"
PROD_INTERNAL_API_URL = "https://app.pipefy.com/internal_api"
PROD_INTERFACES_GRAPHQL_URL = "https://app.pipefy.com/graphql/interfaces"


@pytest.mark.unit
def test_sdk_config_requires_injected_deployment():
    """``deployment`` has no default: the application edge must inject it."""
    with pytest.raises(ValidationError, match="deployment"):
        SdkConfig()


@pytest.mark.unit
def test_sdk_config_forwards_urls_and_posture_off_deployment():
    """The URL / insecure-posture forwards resolve off the injected deployment."""
    settings = SdkConfig(deployment=DeploymentConfig(base_url=DEFAULT_BASE_URL))
    assert settings.graphql_url == PROD_GRAPHQL_URL
    assert settings.internal_api_url == PROD_INTERNAL_API_URL
    assert settings.interfaces_graphql_url == PROD_INTERFACES_GRAPHQL_URL
    assert settings.allow_insecure_urls is False


@pytest.mark.unit
def test_sdk_config_forwards_a_custom_host():
    """A non-prod deployment host flows through every forwarded URL."""
    settings = SdkConfig(
        deployment=DeploymentConfig(base_url="https://staging.example.com")
    )
    assert settings.graphql_url == "https://staging.example.com/graphql"
    assert settings.internal_api_url == "https://staging.example.com/internal_api"
    assert (
        settings.interfaces_graphql_url
        == "https://staging.example.com/graphql/interfaces"
    )


@pytest.mark.unit
def test_sdk_config_knob_defaults():
    """The SDK's own knobs carry their documented defaults."""
    settings = SdkConfig(deployment=DeploymentConfig())
    assert settings.gql_reuse_fetched_graphql_schema is False
    assert settings.default_webhook_name == "Pipefy Webhook"


@pytest.mark.unit
def test_reader_base_url_env_drives_forwarded_urls(monkeypatch: pytest.MonkeyPatch):
    """``PIPEFY_BASE_URL`` flows through the reader into all forwarded URLs."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://staging.example.com")
    settings = live_pipefy_config()
    assert settings.graphql_url == "https://staging.example.com/graphql"
    assert settings.internal_api_url == "https://staging.example.com/internal_api"
    assert (
        settings.interfaces_graphql_url
        == "https://staging.example.com/graphql/interfaces"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "legacy_env_var",
    [
        "PIPEFY_GRAPHQL_URL",
        "PIPEFY_INTERNAL_API_URL",
        "PIPEFY_INTERFACES_GRAPHQL_URL",
        "PIPEFY_SERVICE_ACCOUNT_URL",
        "PIPEFY_OAUTH_URL",
    ],
)
def test_reader_ignores_removed_per_url_env_vars(
    monkeypatch: pytest.MonkeyPatch, legacy_env_var: str
):
    """Per-URL env vars from earlier betas are silently ignored (``extra="ignore"``).

    Locks the hard break: setting any of them must not steer the derived URLs
    off the prod default. Operators have to migrate to ``PIPEFY_BASE_URL``.
    """
    monkeypatch.setenv(legacy_env_var, "https://stale.example.com/whatever")
    settings = live_pipefy_config()
    assert settings.graphql_url == PROD_GRAPHQL_URL
    assert settings.internal_api_url == PROD_INTERNAL_API_URL
    assert settings.interfaces_graphql_url == PROD_INTERFACES_GRAPHQL_URL


@pytest.mark.unit
def test_reader_empty_base_url_raises(monkeypatch: pytest.MonkeyPatch):
    """Empty PIPEFY_BASE_URL is rejected at construction (no opt-out overload)."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "")
    with pytest.raises(ValidationError, match="should match pattern"):
        live_pipefy_config()


@pytest.mark.unit
def test_reader_base_url_strips_surrounding_whitespace(
    monkeypatch: pytest.MonkeyPatch,
):
    """Operator copy-paste sometimes carries surrounding whitespace - strip before pattern."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "  https://app.pipefy.com\t")
    settings = live_pipefy_config()
    assert settings.graphql_url == PROD_GRAPHQL_URL


@pytest.mark.unit
def test_reader_gql_reuse_schema_env(monkeypatch: pytest.MonkeyPatch):
    """The SDK knob loads from its ``PIPEFY_`` env var through the reader."""
    monkeypatch.setenv("PIPEFY_GQL_REUSE_FETCHED_GRAPHQL_SCHEMA", "true")
    assert live_pipefy_config().gql_reuse_fetched_graphql_schema is True
