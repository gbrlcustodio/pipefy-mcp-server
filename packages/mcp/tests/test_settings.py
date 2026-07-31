"""Tests for ``Settings`` / ``PipefySettings`` (env loading and coercion)."""

import pytest
from pipefy_sdk import PipefySettings
from pydantic import ValidationError

from pipefy_mcp.settings import (
    IpaasSettings,
    McpSettings,
    Settings,
    resolve_mcp_settings,
)


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
    monkeypatch.delenv("PIPEFY_OAUTH_CLIENT", raising=False)
    monkeypatch.delenv("PIPEFY_OAUTH_SECRET", raising=False)
    assert Settings().auth.static_token == "env-bearer"


@pytest.mark.unit
@pytest.mark.parametrize(
    "leak_env_var",
    [
        "AUTH_BASE_URL",
        "AUTH_STATIC_TOKEN",
        "AUTH_SERVICE_ACCOUNT_CLIENT_ID",
        "AUTH_SERVICE_ACCOUNT_CLIENT_SECRET",
        "AUTH_AUTH_URL",
        "AUTH_AUTH_CLIENT_ID",
        "AUTH_ALLOW_INSECURE_URLS",
        "PIPEFY_AUTH_BASE_URL",
        "PIPEFY_AUTH_STATIC_TOKEN",
    ],
)
def test_settings_does_not_route_unprefixed_env_into_auth(monkeypatch, leak_env_var):
    """``env_nested_delimiter`` must NOT be set on the parent — otherwise unprefixed
    env vars like ``AUTH_BASE_URL`` would split into ``auth.base_url`` and bypass
    :class:`AuthSettings`'s ``env_prefix="PIPEFY_"`` gate, enabling a credential /
    auth-redirect leak. Locks in the security fix that closes the leak.
    """
    # Clear any host-side ``PIPEFY_*`` env to isolate the leak check.
    for var in (
        "PIPEFY_BASE_URL",
        "PIPEFY_TOKEN",
        "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID",
        "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET",
        "PIPEFY_OAUTH_CLIENT",
        "PIPEFY_OAUTH_SECRET",
        "PIPEFY_AUTH_URL",
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
    assert mcp.profile == "local"
    assert mcp.transport == "stdio"
    assert mcp.host == "127.0.0.1"
    assert mcp.port == 8000
    assert mcp.log_level == "INFO"
    assert mcp.toolsets is None


@pytest.mark.unit
def test_mcp_settings_log_level_from_env_normalizes_case(monkeypatch):
    monkeypatch.setenv("PIPEFY_MCP_LOG_LEVEL", "warning")
    assert Settings().mcp.log_level == "WARNING"


@pytest.mark.unit
def test_mcp_settings_log_level_rejects_unknown_value():
    with pytest.raises(ValidationError):
        McpSettings(log_level="verbose")


@pytest.mark.unit
def test_mcp_settings_loads_from_pipefy_mcp_env(monkeypatch):
    """The ``PIPEFY_MCP_*`` env vars keep working after the move out of PipefySettings."""
    monkeypatch.setenv("PIPEFY_MCP_PROFILE", "remote")
    monkeypatch.setenv("PIPEFY_MCP_TRANSPORT", "http")
    monkeypatch.setenv("PIPEFY_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("PIPEFY_MCP_PORT", "9100")
    monkeypatch.setenv("PIPEFY_MCP_UNIFIED_ENVELOPE", "false")
    monkeypatch.setenv("PIPEFY_MCP_TOOLSETS", "workflow,database")

    mcp = Settings().mcp
    assert mcp.profile == "remote"
    assert mcp.transport == "http"
    assert mcp.host == "0.0.0.0"
    assert mcp.port == 9100
    assert mcp.unified_envelope is False
    assert mcp.toolsets == "workflow,database"


@pytest.mark.unit
def test_resolve_mcp_settings_folds_toolsets_flag_over_env(monkeypatch):
    """The ``--toolsets`` flag reaches ``mcp.toolsets`` and outranks the env var."""
    monkeypatch.setenv("PIPEFY_MCP_TOOLSETS", "governance")

    resolved = resolve_mcp_settings(
        profile=None, transport=None, host=None, port=None, toolsets="workflow"
    )
    assert resolved.mcp.toolsets == "workflow"


@pytest.mark.unit
def test_resolve_mcp_settings_toolsets_falls_back_to_env(monkeypatch):
    """With no flag, ``mcp.toolsets`` falls back to ``PIPEFY_MCP_TOOLSETS``."""
    monkeypatch.setenv("PIPEFY_MCP_TOOLSETS", "governance")

    resolved = resolve_mcp_settings(profile=None, transport=None, host=None, port=None)
    assert resolved.mcp.toolsets == "governance"


@pytest.mark.unit
def test_mcp_transport_defaults_from_profile(monkeypatch):
    """An unset transport follows the profile: local->stdio, remote->http."""
    monkeypatch.delenv("PIPEFY_MCP_TRANSPORT", raising=False)
    assert McpSettings(profile="local").transport == "stdio"
    assert McpSettings(profile="remote").transport == "http"


@pytest.mark.unit
def test_mcp_local_profile_may_run_over_http():
    """'local' is valid over either wire; an explicit http transport is honored."""
    assert McpSettings(profile="local", transport="http").transport == "http"


@pytest.mark.unit
def test_mcp_remote_over_stdio_is_rejected():
    """'remote' has no stdio equivalent (no per-request bearer), so it is refused."""
    with pytest.raises(ValidationError, match="requires the 'http' transport"):
        McpSettings(profile="remote", transport="stdio")


# --- bind-safety interlock (auth posture, not bind interface) ----------------


@pytest.mark.unit
@pytest.mark.parametrize("host", ["0.0.0.0", "203.0.113.5"])
def test_mcp_local_http_refuses_non_loopback_bind(host):
    """The unauthenticated 'local' profile refuses a non-loopback HTTP bind."""
    with pytest.raises(ValidationError, match="non-loopback HTTP bind"):
        McpSettings(profile="local", transport="http", host=host)


@pytest.mark.unit
def test_mcp_local_http_non_loopback_allowed_with_escape_hatch():
    """The escape hatch opts in to an unauthenticated non-loopback bind."""
    settings = McpSettings(
        profile="local",
        transport="http",
        host="0.0.0.0",
        allow_insecure_http_bind=True,
    )
    assert settings.host == "0.0.0.0"


@pytest.mark.unit
def test_mcp_local_http_escape_hatch_from_env(monkeypatch):
    """The escape hatch is settable via PIPEFY_MCP_ALLOW_INSECURE_HTTP_BIND."""
    monkeypatch.setenv("PIPEFY_MCP_ALLOW_INSECURE_HTTP_BIND", "true")
    settings = McpSettings(profile="local", transport="http", host="0.0.0.0")
    assert settings.allow_insecure_http_bind is True


@pytest.mark.unit
@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.2"])
def test_mcp_local_http_allows_loopback_bind(host):
    """Loopback covers all of 127.0.0.0/8 and ::1, not just literal 127.0.0.1."""
    assert McpSettings(profile="local", transport="http", host=host).host == host


@pytest.mark.unit
def test_mcp_local_stdio_ignores_a_non_loopback_host():
    """stdio never binds, so a non-loopback host is not checked."""
    settings = McpSettings(profile="local", transport="stdio", host="0.0.0.0")
    assert settings.host == "0.0.0.0"


@pytest.mark.unit
def test_mcp_remote_binds_any_host_without_the_escape_hatch():
    """The authenticated 'remote' profile binds a non-loopback host unrestricted.

    Its per-request bearer is the control, so bind interface is irrelevant. The
    resource-server requirement is a separate runtime check, not this validator.
    """
    settings = McpSettings(profile="remote", transport="http", host="0.0.0.0")
    assert settings.host == "0.0.0.0"
    assert settings.allow_insecure_http_bind is False


# --- transport allowlist fields (DNS-rebinding host/Origin allowlist) ---------


@pytest.mark.unit
def test_mcp_allowlists_default_to_none():
    """Unset allowlists stay None so the builder can preserve the SDK's default."""
    mcp = McpSettings()
    assert mcp.allowed_hosts is None
    assert mcp.allowed_origins is None


@pytest.mark.unit
def test_mcp_allowed_hosts_from_env_parses_json(monkeypatch):
    """PIPEFY_MCP_ALLOWED_HOSTS is a JSON array, like RS required_scopes."""
    monkeypatch.setenv("PIPEFY_MCP_ALLOWED_HOSTS", '["mcp.pipefy.com", "mcp:8000"]')
    assert Settings().mcp.allowed_hosts == ["mcp.pipefy.com", "mcp:8000"]


@pytest.mark.unit
def test_mcp_allowed_origins_from_env_parses_json(monkeypatch):
    monkeypatch.setenv("PIPEFY_MCP_ALLOWED_ORIGINS", '["https://mcp.pipefy.com"]')
    assert Settings().mcp.allowed_origins == ["https://mcp.pipefy.com"]


@pytest.mark.unit
def test_mcp_allowlist_trims_surrounding_whitespace():
    """Each entry is trimmed; localhost is kept (no SSRF gate on operator entries)."""
    mcp = McpSettings(
        allowed_hosts=[" mcp.pipefy.com ", "localhost"],
        allowed_origins=["  https://mcp.pipefy.com  "],
    )
    assert mcp.allowed_hosts == ["mcp.pipefy.com", "localhost"]
    assert mcp.allowed_origins == ["https://mcp.pipefy.com"]


@pytest.mark.unit
@pytest.mark.parametrize("field", ["allowed_hosts", "allowed_origins"])
def test_mcp_allowlist_rejects_a_blank_entry(field):
    """A blank/whitespace entry is a config error, not a silently-dropped value.

    Dropping it would hide the typo, and for allowed_origins could collapse the
    list to the strict reject-all-Origin posture, so the settings boundary refuses.
    """
    with pytest.raises(ValidationError, match="blank entry"):
        McpSettings(**{field: ["ok", "   "]})


@pytest.mark.unit
def test_mcp_explicit_empty_allowlist_is_preserved():
    """An explicit [] is a deliberate value (reject-all-Origin), not a blank entry."""
    mcp = McpSettings(allowed_hosts=[], allowed_origins=[])
    assert mcp.allowed_hosts == []
    assert mcp.allowed_origins == []


# --- iPaaS (Advanced Automations) settings ------------------------------------


@pytest.mark.unit
def test_ipaas_settings_work_out_of_the_box():
    """The default is Pipefy's canonical public PKCE client: no env, no secret."""
    settings = IpaasSettings()
    assert settings.configured is True
    assert settings.oauth_client_id
    assert settings.oauth_client_secret is None
    assert settings.url == "https://ipaas.pipefy.com"


@pytest.mark.unit
def test_ipaas_settings_blank_client_id_disables():
    assert IpaasSettings(oauth_client_id="").configured is False
    assert IpaasSettings(oauth_client_id="  ").configured is False


@pytest.mark.unit
def test_ipaas_settings_url_normalized_and_https_enforced():
    assert IpaasSettings(url="https://ipaas.test/ ").url == "https://ipaas.test"
    with pytest.raises(ValidationError):
        IpaasSettings(url="http://ipaas.test")


@pytest.mark.unit
def test_ipaas_settings_from_env(monkeypatch):
    monkeypatch.setenv("PIPEFY_IPAAS_OAUTH_CLIENT_ID", "custom-client")
    monkeypatch.setenv("PIPEFY_IPAAS_OAUTH_CLIENT_SECRET", "custom-secret")
    settings = IpaasSettings()
    assert settings.oauth_client_id == "custom-client"
    assert settings.oauth_client_secret == "custom-secret"
