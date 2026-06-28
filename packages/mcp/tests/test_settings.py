"""Tests for the MCP composition root (resolve_mcp_settings) and edge models."""

import pytest
from pipefy_infra.deployment import DeploymentConfig
from pydantic import ValidationError

from pipefy_mcp.settings import (
    McpSettings,
    get_settings,
    reset_settings,
    resolve_mcp_settings,
)


@pytest.fixture(autouse=True)
def _clear_pipefy_env(monkeypatch):
    """Strip ambient PIPEFY_* so resolution exercises defaults unless a test sets them."""
    import os

    for key in list(os.environ):
        if key.startswith("PIPEFY_") or key in {"XDG_CONFIG_HOME", "APPDATA"}:
            monkeypatch.delenv(key, raising=False)


@pytest.mark.unit
def test_internal_api_url_derived_from_base_url(monkeypatch):
    """``PIPEFY_BASE_URL`` flows into the computed ``internal_api_url``."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://custom.pipefy.com")
    settings = resolve_mcp_settings()
    assert settings.pipefy.internal_api_url == "https://custom.pipefy.com/internal_api"


@pytest.mark.unit
def test_sub_models_share_one_deployment(monkeypatch):
    """pipefy / auth / jwt / rs are all injected the SAME DeploymentConfig instance."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://custom.pipefy.com")
    s = resolve_mcp_settings()
    assert s.pipefy.deployment is s.auth.deployment
    assert s.auth.deployment is s.jwt.deployment
    assert s.jwt.deployment is s.rs.deployment


@pytest.mark.unit
def test_allow_insecure_urls_from_env(monkeypatch):
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "true")
    settings = resolve_mcp_settings()
    assert settings.pipefy.allow_insecure_urls is True
    assert settings.auth.allow_insecure_urls is True


@pytest.mark.unit
def test_permission_denied_enrichment_timeout_defaults_to_five():
    assert McpSettings().permission_denied_enrichment_timeout_seconds == 5.0


@pytest.mark.unit
def test_permission_denied_enrichment_timeout_rejects_too_low():
    with pytest.raises(ValidationError):
        McpSettings(permission_denied_enrichment_timeout_seconds=0.05)


@pytest.mark.unit
def test_permission_denied_enrichment_timeout_from_env(monkeypatch):
    monkeypatch.setenv("PIPEFY_PERMISSION_DENIED_ENRICHMENT_TIMEOUT_SECONDS", "8.5")
    assert (
        resolve_mcp_settings().mcp.permission_denied_enrichment_timeout_seconds == 8.5
    )


@pytest.mark.unit
def test_gql_reuse_fetched_graphql_schema_from_env(monkeypatch):
    monkeypatch.setenv("PIPEFY_GQL_REUSE_FETCHED_GRAPHQL_SCHEMA", "true")
    assert resolve_mcp_settings().pipefy.gql_reuse_fetched_graphql_schema is True


@pytest.mark.unit
def test_default_webhook_name_from_env(monkeypatch):
    monkeypatch.setenv("PIPEFY_DEFAULT_WEBHOOK_NAME", "ACME Inbound")
    assert resolve_mcp_settings().pipefy.default_webhook_name == "ACME Inbound"


@pytest.mark.unit
def test_settings_rejects_link_local_base_url(monkeypatch):
    """Resolution must SSRF-check ``base_url`` (which drives the OAuth token endpoint)."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://169.254.169.254")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "csecret")
    with pytest.raises(ValueError, match="link-local|private|loopback"):
        resolve_mcp_settings()


@pytest.mark.unit
def test_settings_picks_up_pipefy_token_from_env(monkeypatch):
    """``PIPEFY_TOKEN`` must populate ``auth.static_token`` so MCP boots from ``.env``-only setups."""
    monkeypatch.setenv("PIPEFY_TOKEN", "env-bearer")
    assert resolve_mcp_settings().auth.static_token == "env-bearer"


@pytest.mark.unit
@pytest.mark.parametrize(
    "leak_env_var",
    [
        "AUTH_BASE_URL",
        "AUTH_STATIC_TOKEN",
        "AUTH_SERVICE_ACCOUNT_CLIENT_ID",
        "AUTH_SERVICE_ACCOUNT_CLIENT_SECRET",
        "AUTH_AUTH_ISSUER_URL",
        "AUTH_AUTH_PUBLIC_CLIENT_ID",
        "AUTH_ALLOW_INSECURE_URLS",
        # base_url is not an AuthEnvSettings field (it lives on the injected
        # deployment), so even the correct PIPEFY_AUTH_ prefix routes nowhere.
        "PIPEFY_AUTH_BASE_URL",
    ],
)
def test_settings_does_not_route_unprefixed_env_into_auth(monkeypatch, leak_env_var):
    """Unprefixed / mis-prefixed env vars must not bleed into auth fields.

    Each reader binds only its own ``env_prefix``; nothing splits a stray
    ``AUTH_BASE_URL`` into a nested path. Locks in the leak guard.
    """
    monkeypatch.setenv(leak_env_var, "https://attacker.example.com")
    settings = resolve_mcp_settings()
    assert settings.auth.deployment.base_url == "https://app.pipefy.com"
    assert (
        settings.auth.deployment.oauth_token_url == "https://app.pipefy.com/oauth/token"
    )
    assert settings.auth.static_token is None
    assert settings.auth.service_account is None


@pytest.mark.unit
def test_mcp_settings_defaults():
    """MCP knobs default to the local stdio profile."""
    mcp = McpSettings()
    assert mcp.unified_envelope is True
    assert mcp.remote_mode is False
    assert mcp.host == "127.0.0.1"
    assert mcp.port == 8000


@pytest.mark.unit
def test_mcp_settings_loads_from_pipefy_mcp_env(monkeypatch):
    """The ``PIPEFY_MCP_*`` env vars drive the MCP knobs."""
    monkeypatch.setenv("PIPEFY_MCP_REMOTE_MODE", "true")
    monkeypatch.setenv("PIPEFY_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("PIPEFY_MCP_PORT", "9100")
    monkeypatch.setenv("PIPEFY_MCP_UNIFIED_ENVELOPE", "false")

    mcp = resolve_mcp_settings().mcp
    assert mcp.remote_mode is True
    assert mcp.host == "0.0.0.0"
    assert mcp.port == 9100
    assert mcp.unified_envelope is False


@pytest.mark.unit
def test_deployment_config_rejects_http_base_when_secure():
    with pytest.raises(ValueError, match="base_url.*HTTPS"):
        DeploymentConfig(base_url="http://app.pipefy.com")


@pytest.mark.unit
def test_get_settings_caches_and_reset_re_resolves(monkeypatch):
    """get_settings caches; reset_settings forces the next call to re-read env."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://first.example.com")
    first = get_settings()
    assert first.pipefy.deployment.base_url == "https://first.example.com"
    # A second call without reset returns the SAME cached instance.
    assert get_settings() is first
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://second.example.com")
    reset_settings()
    second = get_settings()
    assert second is not first
    assert second.pipefy.deployment.base_url == "https://second.example.com"
