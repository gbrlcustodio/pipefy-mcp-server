"""Tests for ``Settings`` / ``PipefySettings`` (env loading and coercion)."""

import pytest
from pipefy_sdk import PipefySettings
from pydantic import ValidationError

from pipefy_mcp.settings import McpSettings, Settings


@pytest.mark.unit
def test_internal_api_url_derived_from_base_url(monkeypatch):
    """``PIPEFY_BASE_URL`` flows into the computed ``internal_api_url``."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://custom.pipefy.com")
    settings = Settings()
    assert settings.pipefy.internal_api_url == "https://custom.pipefy.com/internal_api"


@pytest.mark.unit
def test_pipefy_settings_rejects_http_base_when_secure():
    with pytest.raises(ValueError, match="base_url.*HTTPS"):
        PipefySettings(base_url="http://app.pipefy.com")


@pytest.mark.unit
def test_pipefy_settings_rejects_loopback_base():
    with pytest.raises(ValueError, match="base_url.*localhost|127"):
        PipefySettings(base_url="https://127.0.0.1")


@pytest.mark.unit
def test_pipefy_settings_allow_insecure_urls_permits_http_localhost():
    s = PipefySettings(allow_insecure_urls=True, base_url="http://localhost")
    assert s.base_url == "http://localhost"
    assert s.graphql_url == "http://localhost/graphql"
    assert s.internal_api_url == "http://localhost/internal_api"


@pytest.mark.unit
def test_allow_insecure_urls_from_env(monkeypatch):
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "true")
    settings = Settings()
    assert settings.pipefy.allow_insecure_urls is True


@pytest.mark.unit
def test_permission_denied_enrichment_timeout_defaults_to_five():
    assert PipefySettings().permission_denied_enrichment_timeout_seconds == 5.0


@pytest.mark.unit
def test_permission_denied_enrichment_timeout_rejects_too_low():
    with pytest.raises(ValidationError):
        PipefySettings(permission_denied_enrichment_timeout_seconds=0.05)


@pytest.mark.unit
def test_permission_denied_enrichment_timeout_from_env(monkeypatch):
    monkeypatch.setenv("PIPEFY_PERMISSION_DENIED_ENRICHMENT_TIMEOUT_SECONDS", "8.5")
    settings = Settings()
    assert settings.pipefy.permission_denied_enrichment_timeout_seconds == 8.5


@pytest.mark.unit
def test_gql_reuse_fetched_graphql_schema_defaults_to_false():
    assert PipefySettings().gql_reuse_fetched_graphql_schema is False


@pytest.mark.unit
def test_gql_reuse_fetched_graphql_schema_from_env(monkeypatch):
    monkeypatch.setenv("PIPEFY_GQL_REUSE_FETCHED_GRAPHQL_SCHEMA", "true")
    settings = Settings()
    assert settings.pipefy.gql_reuse_fetched_graphql_schema is True


@pytest.mark.unit
def test_default_webhook_name_defaults():
    assert PipefySettings().default_webhook_name == "Pipefy Webhook"


@pytest.mark.unit
def test_default_webhook_name_from_env(monkeypatch):
    monkeypatch.setenv("PIPEFY_DEFAULT_WEBHOOK_NAME", "ACME Inbound")
    settings = Settings()
    assert settings.pipefy.default_webhook_name == "ACME Inbound"


@pytest.mark.unit
def test_default_webhook_name_rejects_empty_string():
    with pytest.raises(ValidationError):
        PipefySettings(default_webhook_name="")


@pytest.mark.unit
def test_settings_rejects_link_local_base_url(monkeypatch):
    """Settings load must SSRF-check ``base_url`` (which drives the OAuth token endpoint)."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://169.254.169.254")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "csecret")
    with pytest.raises(ValidationError, match="link-local|private|loopback"):
        Settings()


@pytest.mark.unit
def test_settings_picks_up_pipefy_token_from_env(monkeypatch):
    """``PIPEFY_TOKEN`` must populate ``auth.static_token`` so MCP boots from ``.env``-only setups."""
    monkeypatch.setenv("PIPEFY_TOKEN", "env-bearer")
    monkeypatch.delenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", raising=False)
    monkeypatch.delenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", raising=False)
    assert Settings().auth.static_token == "env-bearer"


@pytest.mark.unit
@pytest.mark.parametrize(
    "leak_env_var",
    [
        "AUTH_BASE_URL",
        "AUTH_STATIC_TOKEN",
        "AUTH_SERVICE_ACCOUNT_CLIENT_ID",
        "AUTH_SERVICE_ACCOUNT_CLIENT_SECRET",
        "AUTH_ISSUER_URL",
        "AUTH_CLIENT_ID",
        "AUTH_ALLOW_INSECURE_URLS",
    ],
)
def test_settings_does_not_route_unprefixed_env_into_auth(monkeypatch, leak_env_var):
    """``env_nested_delimiter`` must NOT be set on the parent, otherwise unprefixed
    env vars like ``AUTH_BASE_URL`` would split into ``auth.base_url`` and bypass
    :class:`AuthSettings`'s ``env_prefix="PIPEFY_AUTH_"`` gate, enabling a credential /
    auth-redirect leak. Locks in the security fix that closes the leak.
    """
    # Clear any host-side ``PIPEFY_*`` env to isolate the leak check.
    for var in (
        "PIPEFY_BASE_URL",
        "PIPEFY_TOKEN",
        "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID",
        "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET",
        "PIPEFY_AUTH_ISSUER_URL",
        "PIPEFY_AUTH_CLIENT_ID",
        "PIPEFY_ALLOW_INSECURE_URLS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(leak_env_var, "https://attacker.example.com")
    settings = Settings()
    assert settings.auth.base_url == "https://app.pipefy.com"
    assert settings.auth.service_account_url == "https://app.pipefy.com/oauth/token"
    assert settings.auth.static_token is None
    assert settings.auth.service_account_client_id is None
    assert settings.auth.service_account_client_secret is None


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
    """The ``PIPEFY_MCP_*`` env vars keep working after the move out of PipefySettings."""
    monkeypatch.setenv("PIPEFY_MCP_REMOTE_MODE", "true")
    monkeypatch.setenv("PIPEFY_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("PIPEFY_MCP_PORT", "9100")
    monkeypatch.setenv("PIPEFY_MCP_UNIFIED_ENVELOPE", "false")

    mcp = Settings().mcp
    assert mcp.remote_mode is True
    assert mcp.host == "0.0.0.0"
    assert mcp.port == 9100
    assert mcp.unified_envelope is False
