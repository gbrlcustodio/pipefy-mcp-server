import time
from datetime import timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_auth import (
    AuthSettings,
    JwtValidationSettings,
    RefreshableBearerAuth,
    StaticBearerAuth,
    TokenResponse,
)
from pipefy_auth.storage import StoredSession
from pipefy_sdk import PipefySettings

from pipefy_mcp._docs import DOCS_SETUP_REF
from pipefy_mcp.auth import RequestContextBearerAuth, build_resource_server_auth
from pipefy_mcp.core.runtime import RequestScopedIdentity, StartupIdentity
from pipefy_mcp.server import (
    _assert_safe_http_bind,
    _make_lifespan,
    _register_pipefy_tools,
    _select_auth_source,
    build_pipefy_mcp_server,
    run_server,
)
from pipefy_mcp.settings import McpSettings, ResourceServerSettings, Settings
from pipefy_mcp.tools.registry import PIPEFY_TOOL_NAMES

_RS_ISSUER = "https://idp.example.com/realms/x"
_RS_RESOURCE = "https://mcp.example.com/mcp"


def _fresh_stored_session() -> StoredSession:
    return StoredSession(
        issuer="https://signin.pipefy.com/realms/pipefy",
        client_id="pipefy-cli",
        obtained_at=int(time.time()),
        token=TokenResponse(
            access_token="ACCESS",
            refresh_token="REFRESH",
            expires_in=3600,
        ),
    )


def _resource_server_pair():
    """A configured resource-server (verifier, auth) pair with no network at build.

    The explicit ``jwks_uri`` skips OIDC discovery; the unauthenticated-request
    and metadata tests never decode a token, so the JWKS is never fetched. The
    inbound issuer comes from ``default_issuer_url`` (the login issuer) to exercise
    the same-realm default rather than an explicit override.
    """
    return build_resource_server_auth(
        ResourceServerSettings(resource_server_url=_RS_RESOURCE),
        JwtValidationSettings(jwks_uri="https://idp.example.com/jwks"),
        default_issuer_url=_RS_ISSUER,
    )


_MINIMAL_PIPEFY_SETTINGS = Settings(
    pipefy=PipefySettings(base_url="https://api.pipefy.com"),
    auth=AuthSettings(),
)

# The same minimal settings under the remote profile, for builder tests that need
# the default-deny remote-safe surface without going through run_server.
_REMOTE_PROFILE_SETTINGS = _MINIMAL_PIPEFY_SETTINGS.model_copy(
    update={"mcp": McpSettings(profile="remote")}
)


@pytest.fixture
def remote_rs_env(monkeypatch):
    """Configure the resource-server env so the remote profile resolves an RS.

    ``resolve_mcp_settings`` builds the rs/jwt models from the environment, so the
    remote profile's mandatory resource server comes from these vars (the same
    values as a configured deployment). The explicit ``JWKS_URI`` skips OIDC
    discovery, so building the resource server does no network I/O.
    """
    monkeypatch.setenv("PIPEFY_MCP_RS_RESOURCE_SERVER_URL", _RS_RESOURCE)
    monkeypatch.setenv("PIPEFY_JWT_ISSUER_URL", _RS_ISSUER)
    monkeypatch.setenv("PIPEFY_JWT_JWKS_URI", "https://idp.example.com/jwks")


@pytest.fixture
def mocked_runtime():
    """Patch the builder's identity selection and runtime with no-network stand-ins.

    ``build_pipefy_mcp_server`` first selects an identity source (which, on the
    stdio profile, resolves a credential and fails fast) and then constructs
    ``McpRuntime`` once (which wires its client). This intercepts both so building
    resolves no real credential and ``pipefy_client`` is a stand-in a tool can
    resolve.
    """
    runtime = MagicMock()
    runtime.pipefy_client = MagicMock()
    with (
        patch(
            "pipefy_mcp.server._select_auth_source",
            return_value=RequestScopedIdentity(RequestContextBearerAuth()),
        ),
        patch("pipefy_mcp.server.McpRuntime", return_value=runtime),
    ):
        yield runtime


class TestSelectAuthSource:
    """The composition root parses the transport profile into an identity source.

    The stdio profile resolves one credential from settings and fails fast when
    none is configured; the hosted profile needs none.
    """

    @pytest.fixture(autouse=True)
    def _hermetic_auth_env(self, clear_auth_env):
        """Apply the shared auth-env scrub to every test in this class."""

    @pytest.mark.unit
    def test_hosted_profile_needs_no_credential(self):
        """With a resource server, identity is per request; no startup credential."""

        def _poison(**_kwargs):
            raise AssertionError("hosted profile must not resolve a startup credential")

        with patch("pipefy_mcp.core.runtime.resolve_pipefy_auth", _poison):
            source = _select_auth_source(
                _MINIMAL_PIPEFY_SETTINGS, _resource_server_pair()
            )
        assert isinstance(source, RequestScopedIdentity)
        assert isinstance(source.auth, RequestContextBearerAuth)

    @pytest.mark.unit
    def test_static_token_becomes_a_startup_identity(self):
        """``PIPEFY_TOKEN`` resolves to a static-bearer startup identity."""
        settings = Settings(
            pipefy=PipefySettings(base_url="https://api.pipefy.com"),
            auth=AuthSettings(static_token="env-bearer"),
        )
        source = _select_auth_source(settings, None)
        assert isinstance(source, StartupIdentity)
        assert isinstance(source.auth, StaticBearerAuth)

    # Patch ``load_session``: ``auth_url``'s prod default makes the stored-session
    # tier reachable, so a host with a real keychain entry would otherwise satisfy
    # resolution and break the assertion.
    @pytest.mark.unit
    @patch("pipefy_auth.resolver.load_session", lambda **_: None)
    def test_stdio_profile_without_credential_fails_fast(self):
        """No PIPEFY_TOKEN and no service-account triple → raises at selection."""
        settings = Settings(
            pipefy=PipefySettings(base_url="https://api.pipefy.com"),
            auth=AuthSettings(),
        )
        with pytest.raises(
            RuntimeError, match="Missing Pipefy authentication"
        ) as exc_info:
            _select_auth_source(settings, None)
        assert DOCS_SETUP_REF in str(exc_info.value)

    @pytest.mark.unit
    def test_stored_session_builds_a_refreshable_startup_identity(self):
        """The stored-session arm wires a lazily-refreshing auth; no eager network I/O."""
        settings = Settings(
            pipefy=PipefySettings(base_url="https://api.pipefy.com"),
            auth=AuthSettings(auth_url="https://signin.pipefy.com/realms/pipefy"),
        )
        with patch(
            "pipefy_auth.resolver.load_session",
            return_value=_fresh_stored_session(),
        ):
            source = _select_auth_source(settings, None)
        assert isinstance(source, StartupIdentity)
        assert isinstance(source.auth, RefreshableBearerAuth)


@pytest.mark.anyio
async def test_register_tools(mocked_runtime):
    """The full Pipefy tool surface is reachable through an MCP session.

    Builds its own app from local-profile settings (so the ambient environment
    cannot change the surface) under ``mocked_runtime`` (so entering the lifespan
    does not resolve real auth).
    """
    app = build_pipefy_mcp_server(_MINIMAL_PIPEFY_SETTINGS)
    session = create_client_session(
        app,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )
    async with session as s:
        result = await s.list_tools()
        actual_tool_names = sorted(tool.name for tool in result.tools)

    assert actual_tool_names == sorted(PIPEFY_TOOL_NAMES), (
        "Registered tool names must match PIPEFY_TOOL_NAMES"
    )


@pytest.mark.unit
def test_run_server_builds_the_stdio_server_and_runs_it(monkeypatch):
    """The default (local/stdio) profile builds at startup and delegates to mcp.run()."""
    monkeypatch.delenv("PIPEFY_MCP_PROFILE", raising=False)
    monkeypatch.delenv("PIPEFY_MCP_TRANSPORT", raising=False)
    with patch("pipefy_mcp.server.build_pipefy_mcp_server") as mock_build:
        run_server()
        mock_build.assert_called_once()
        (built_settings,), _ = mock_build.call_args
        assert built_settings.mcp.profile == "local"
        assert built_settings.mcp.transport == "stdio"
        mock_build.return_value.run.assert_called_once_with()


# --- Registration happens once, at construction (not in the lifespan) --------


@pytest.mark.unit
def test_build_server_registers_the_full_surface(mocked_runtime):
    """The default (local) profile registers every Pipefy tool up front."""
    app = build_pipefy_mcp_server(_MINIMAL_PIPEFY_SETTINGS)
    registered = {t.name for t in app._tool_manager.list_tools()}
    assert registered == set(PIPEFY_TOOL_NAMES)


@pytest.mark.unit
def test_build_server_remote_mode_exposes_only_the_remote_safe_seed(mocked_runtime):
    """The remote profile withholds every tool not marked remote-safe."""
    app = build_pipefy_mcp_server(_REMOTE_PROFILE_SETTINGS)
    exposed = {t.name for t in app._tool_manager.list_tools()} & PIPEFY_TOOL_NAMES
    assert 0 < len(exposed) < len(PIPEFY_TOOL_NAMES)
    assert "get_organization" in exposed
    assert "upload_attachment_to_card" not in exposed
    assert "execute_graphql" not in exposed


@pytest.mark.unit
def test_second_registration_pass_is_rejected_by_collision_preflight(mocked_runtime):
    """A second registration pass on the same app is rejected by the preflight.

    The guard is ``check_for_name_collisions()``: the first pass already
    registered the Pipefy names on this app, so the second pass's preflight sees
    them and raises. FastMCP's own ``add_tool`` would silently dedup duplicate
    names rather than raise, so the preflight is what makes re-registration safe
    to forbid. This is why registration runs once, at construction, and the
    lifespan (which Streamable HTTP re-enters per session) never re-registers.
    """
    app = build_pipefy_mcp_server(_MINIMAL_PIPEFY_SETTINGS)
    with pytest.raises(RuntimeError, match="already exist"):
        _register_pipefy_tools(app, remote_mode=False)


# --- The lifespan owns resources only ----------------------------------------


@pytest.mark.anyio
async def test_lifespan_yields_the_runtime_without_registering(
    mocked_runtime,
):
    """The lifespan yields the app-scoped runtime and adds no tools."""
    app = FastMCP("lifespan-resources-test")

    @app.tool()
    async def foreign_mcp_tool() -> str:
        """Pre-existing tool; the lifespan must not touch the tool table."""
        return "ok"

    lifespan = _make_lifespan(mocked_runtime)
    async with lifespan(app) as yielded:
        names = {t.name for t in app._tool_manager.list_tools()}

    assert yielded is mocked_runtime
    # No Pipefy tools were registered by the lifespan; only the foreign tool.
    assert names == {"foreign_mcp_tool"}


@pytest.mark.anyio
async def test_repeat_lifespan_yields_the_same_runtime_and_leaves_tools_untouched(
    mocked_runtime,
):
    """Re-entering the lifespan yields the one app-scoped runtime, never registers.

    Streamable HTTP re-enters the lifespan per session; the runtime (with its
    client wired at construction) is shared across entries, and the tool table is
    never mutated.
    """
    app = FastMCP("lifespan-repeat-test")

    @app.tool()
    async def foreign_mcp_tool() -> str:
        """Must survive both visits untouched."""
        return "ok"

    lifespan = _make_lifespan(mocked_runtime)
    async with lifespan(app) as first_runtime:
        first = {t.name for t in app._tool_manager.list_tools()}
    async with lifespan(app) as second_runtime:
        second = {t.name for t in app._tool_manager.list_tools()}

    assert first == second == {"foreign_mcp_tool"}
    assert first_runtime is second_runtime is mocked_runtime


# --- HTTP (Streamable) transport profile ------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_http_bind_allows_loopback_hosts(host):
    _assert_safe_http_bind(host=host)


@pytest.mark.unit
@pytest.mark.parametrize("host", ["0.0.0.0", "203.0.113.5"])
def test_loopback_http_bind_refuses_non_loopback_hosts(host):
    """A non-loopback bind is refused until the hosted on-behalf-of profile lands."""
    with pytest.raises(RuntimeError, match="non-loopback host"):
        _assert_safe_http_bind(host=host)


@pytest.mark.unit
def test_run_server_stdio_logs_the_argv_resolved_profile(monkeypatch):
    """The startup log reflects the argv-resolved profile, not the ambient env.

    Regression guard: launching ``--profile local`` while ``PIPEFY_MCP_PROFILE``
    says ``remote`` in the environment must log ``local`` (argv wins), so the one
    operator-facing signal of the active profile is accurate.
    """
    monkeypatch.setenv("PIPEFY_MCP_PROFILE", "remote")
    monkeypatch.delenv("PIPEFY_MCP_TRANSPORT", raising=False)
    with (
        patch("pipefy_mcp.server.build_pipefy_mcp_server"),
        patch("pipefy_mcp.server.logger") as mock_logger,
    ):
        run_server(profile="local")

    logged = " ".join(str(call.args) for call in mock_logger.info.call_args_list)
    assert "local" in logged
    assert "remote" not in logged


@pytest.mark.unit
def test_run_server_local_profile_over_http_serves_without_inbound_auth():
    """``--profile local --transport http`` serves HTTP with the full surface, no bearer.

    The local profile over loopback HTTP trusts its peer, so no resource-server
    (inbound bearer validation) is built even when serving over HTTP.
    """
    fake_app = MagicMock()
    with patch(
        "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
    ) as mock_build:
        run_server(profile="local", transport="http", host="127.0.0.1", port=9200)

    mock_build.assert_called_once()
    (built_settings,), kwargs = mock_build.call_args
    assert built_settings.mcp.profile == "local"
    assert built_settings.mcp.host == "127.0.0.1"
    assert built_settings.mcp.port == 9200
    assert kwargs["resource_server"] is None
    fake_app.run.assert_called_once_with("streamable-http")


@pytest.mark.unit
def test_run_server_remote_profile_defaults_to_http_transport(
    monkeypatch, remote_rs_env
):
    """``--profile remote`` with no ``--transport`` serves HTTP (profile-derived default)."""
    monkeypatch.delenv("PIPEFY_MCP_TRANSPORT", raising=False)
    fake_app = MagicMock()
    with patch(
        "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
    ) as mock_build:
        run_server(profile="remote", host="127.0.0.1", port=9300)

    fake_app.run.assert_called_once_with("streamable-http")
    (built_settings,), _ = mock_build.call_args
    assert built_settings.mcp.profile == "remote"


@pytest.mark.unit
def test_run_server_http_builds_the_app_and_serves_over_streamable_http(remote_rs_env):
    """The remote HTTP path builds through the shared builder with a resource server."""
    fake_app = MagicMock()
    with patch(
        "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
    ) as mock_build:
        run_server(profile="remote", transport="http", host="127.0.0.1", port=9123)

    (built_settings,), kwargs = mock_build.call_args
    assert built_settings.mcp.profile == "remote"
    assert built_settings.mcp.host == "127.0.0.1"
    assert built_settings.mcp.port == 9123
    assert kwargs["resource_server"] is not None
    fake_app.run.assert_called_once_with("streamable-http")


@pytest.mark.unit
def test_run_server_remote_without_resource_server_fails_fast(monkeypatch):
    """``--profile remote`` with no RESOURCE_SERVER_URL fails fast, never builds the app.

    The remote profile acts on behalf of the caller, so it needs a per-request
    bearer to validate. Without a configured resource server there is no
    per-request identity, and silently falling back to the single startup
    credential would defeat the profile, so startup is refused.
    """
    monkeypatch.delenv("PIPEFY_MCP_RS_RESOURCE_SERVER_URL", raising=False)
    with patch("pipefy_mcp.server.build_pipefy_mcp_server") as mock_build:
        with pytest.raises(RuntimeError, match="requires a resource server"):
            run_server(profile="remote", transport="http", host="127.0.0.1", port=9123)

    mock_build.assert_not_called()


@pytest.mark.unit
def test_run_server_http_fills_host_and_port_from_settings_when_unset(
    monkeypatch, remote_rs_env
):
    """Unset host/port resolve to the configured PIPEFY_MCP_HOST / PIPEFY_MCP_PORT."""
    monkeypatch.delenv("PIPEFY_MCP_HOST", raising=False)
    monkeypatch.delenv("PIPEFY_MCP_PORT", raising=False)
    fake_app = MagicMock()
    with patch(
        "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
    ) as mock_build:
        run_server(profile="remote", transport="http")

    (built_settings,), _ = mock_build.call_args
    assert built_settings.mcp.host == "127.0.0.1"
    assert built_settings.mcp.port == 8000


@pytest.mark.unit
def test_run_server_http_respects_an_explicit_zero_port(remote_rs_env):
    """``port=0`` (let the OS pick) must not be swallowed as a falsy default."""
    fake_app = MagicMock()
    with patch(
        "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
    ) as mock_build:
        run_server(profile="remote", transport="http", host="127.0.0.1", port=0)

    (built_settings,), _ = mock_build.call_args
    assert built_settings.mcp.port == 0


@pytest.mark.unit
def test_run_server_http_refuses_non_loopback_before_building(remote_rs_env):
    """The loopback guard fires before the app is built or served."""
    with patch("pipefy_mcp.server.build_pipefy_mcp_server") as mock_build:
        with pytest.raises(RuntimeError, match="Refusing to serve"):
            run_server(profile="remote", transport="http", host="0.0.0.0", port=9123)

    mock_build.assert_not_called()


# --- Resource-server role (OAuth 2.0 inbound bearer validation) --------------


@pytest.mark.unit
def test_stdio_build_has_no_inbound_auth(mocked_runtime):
    """The stdio profile builds with no inbound auth wired into FastMCP."""
    app = build_pipefy_mcp_server(_MINIMAL_PIPEFY_SETTINGS)
    assert app.settings.auth is None


@pytest.mark.unit
def test_build_with_resource_server_wires_inbound_auth(mocked_runtime):
    """An enabled resource-server pair wires FastMCP's auth + token verifier."""
    app = build_pipefy_mcp_server(
        _REMOTE_PROFILE_SETTINGS, resource_server=_resource_server_pair()
    )
    assert app.settings.auth is not None
    assert str(app.settings.auth.resource_server_url).rstrip("/") == _RS_RESOURCE


def _asgi_client(app):
    transport = httpx.ASGITransport(app=app.streamable_http_app())
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.unit
async def test_http_unauthenticated_request_gets_401_challenge(mocked_runtime):
    """A request with no bearer is rejected with a 401 + WWW-Authenticate challenge.

    The auth middleware runs before the MCP handler, so no session (and no
    network) is needed: the challenge points at the protected-resource metadata.
    """
    app = build_pipefy_mcp_server(
        _REMOTE_PROFILE_SETTINGS, resource_server=_resource_server_pair()
    )
    async with _asgi_client(app) as client:
        resp = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1}
        )
    assert resp.status_code == 401
    assert "resource_metadata=" in resp.headers["www-authenticate"]


@pytest.mark.unit
async def test_http_serves_protected_resource_metadata(mocked_runtime):
    """The RFC 9728 metadata route is served at the resource's well-known path."""
    app = build_pipefy_mcp_server(
        _REMOTE_PROFILE_SETTINGS, resource_server=_resource_server_pair()
    )
    async with _asgi_client(app) as client:
        resp = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resource"].rstrip("/") == _RS_RESOURCE
    advertised = [s.rstrip("/") for s in body["authorization_servers"]]
    assert _RS_ISSUER in advertised
