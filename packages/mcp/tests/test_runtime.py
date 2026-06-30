"""Tests for the MCP composition root (resolve_mcp_runtime) and edge models."""

import pytest
from pipefy_infra.deployment import DeploymentConfig
from pydantic import ValidationError

from pipefy_mcp.runtime import (
    McpSettings,
    get_runtime,
    reset_runtime,
    resolve_mcp_runtime,
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
    runtime = resolve_mcp_runtime()
    assert (
        runtime.endpoints.internal_api_url == "https://custom.pipefy.com/internal_api"
    )


@pytest.mark.unit
def test_endpoints_and_token_url_share_one_host(monkeypatch):
    """The SDK endpoints and the service-account token URL derive from one host.

    Structurally guaranteed: resolve_mcp_runtime builds ONE DeploymentConfig and
    feeds it to both loaders, so the endpoints and the OAuth token URL cannot
    drift onto different hosts.
    """
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://custom.pipefy.com")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "csecret")
    runtime = resolve_mcp_runtime()
    assert runtime.endpoints.graphql_url == "https://custom.pipefy.com/graphql"
    sa = runtime.credentials.service_account
    assert sa is not None
    assert sa.token_url == "https://custom.pipefy.com/oauth/token"


@pytest.mark.unit
def test_allow_insecure_urls_from_env(monkeypatch):
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "true")
    assert resolve_mcp_runtime().allow_insecure_urls is True


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
    assert resolve_mcp_runtime().mcp.permission_denied_enrichment_timeout_seconds == 8.5


@pytest.mark.unit
def test_gql_reuse_fetched_graphql_schema_from_env(monkeypatch):
    monkeypatch.setenv("PIPEFY_GQL_REUSE_FETCHED_GRAPHQL_SCHEMA", "true")
    assert resolve_mcp_runtime().reuse_schema is True


@pytest.mark.unit
def test_default_webhook_name_from_env(monkeypatch):
    monkeypatch.setenv("PIPEFY_DEFAULT_WEBHOOK_NAME", "ACME Inbound")
    assert resolve_mcp_runtime().default_webhook_name == "ACME Inbound"


@pytest.mark.unit
def test_runtime_rejects_link_local_base_url(monkeypatch):
    """Resolution must SSRF-check ``base_url`` (which drives the OAuth token endpoint)."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://169.254.169.254")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "csecret")
    with pytest.raises(ValueError, match="link-local|private|loopback"):
        resolve_mcp_runtime()


@pytest.mark.unit
def test_runtime_picks_up_pipefy_token_from_env(monkeypatch):
    """``PIPEFY_TOKEN`` must populate ``credentials.static_token`` so MCP boots from ``.env``-only setups."""
    monkeypatch.setenv("PIPEFY_TOKEN", "env-bearer")
    assert resolve_mcp_runtime().credentials.static_token == "env-bearer"


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
        # base_url is not an auth reader field (it lives on the deployment edge),
        # so even the correct PIPEFY_AUTH_ prefix routes nowhere.
        "PIPEFY_AUTH_BASE_URL",
    ],
)
def test_runtime_does_not_route_unprefixed_env_into_auth(monkeypatch, leak_env_var):
    """Unprefixed / mis-prefixed env vars must not bleed into auth fields.

    Each reader binds only its own ``env_prefix``; nothing splits a stray
    ``AUTH_BASE_URL`` into a nested path. Locks in the leak guard.
    """
    monkeypatch.setenv(leak_env_var, "https://attacker.example.com")
    runtime = resolve_mcp_runtime()
    assert runtime.endpoints.graphql_url == "https://app.pipefy.com/graphql"
    assert runtime.credentials.static_token is None
    assert runtime.credentials.service_account is None


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

    mcp = resolve_mcp_runtime().mcp
    assert mcp.remote_mode is True
    assert mcp.host == "0.0.0.0"
    assert mcp.port == 9100
    assert mcp.unified_envelope is False


@pytest.mark.unit
def test_deployment_config_rejects_http_base_when_secure():
    with pytest.raises(ValueError, match="base_url.*HTTPS"):
        DeploymentConfig(base_url="http://app.pipefy.com")


@pytest.mark.unit
def test_get_runtime_caches_and_reset_re_resolves(monkeypatch):
    """get_runtime caches; reset_runtime forces the next call to re-read env."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://first.example.com")
    first = get_runtime()
    assert first.endpoints.graphql_url == "https://first.example.com/graphql"
    # A second call without reset returns the SAME cached instance.
    assert get_runtime() is first
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://second.example.com")
    reset_runtime()
    second = get_runtime()
    assert second is not first
    assert second.endpoints.graphql_url == "https://second.example.com/graphql"
