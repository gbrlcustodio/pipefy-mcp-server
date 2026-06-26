from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_auth import AuthSettings, JwtValidationSettings
from pipefy_sdk import ClientSettings

from pipefy_mcp.auth import build_resource_server_auth
from pipefy_mcp.server import (
    _assert_safe_http_bind,
    _register_pipefy_tools,
    build_pipefy_mcp_server,
    lifespan,
    run_server,
)
from pipefy_mcp.settings import ResourceServerSettings, Settings
from pipefy_mcp.tools.registry import PIPEFY_TOOL_NAMES

_RS_ISSUER = "https://idp.example.com/realms/x"
_RS_RESOURCE = "https://mcp.example.com/mcp"


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
    sdk=ClientSettings(base_url="https://api.pipefy.com"),
    auth=AuthSettings(),
)


@pytest.fixture
def mocked_container():
    """Patch the ``ServicesContainer`` the lifespan builds with a no-network mock.

    The lifespan constructs ``ServicesContainer()`` per entry; this intercepts
    that construction so ``initialize_services`` is a no-op and ``pipefy_client``
    is a stand-in a tool can resolve.
    """
    container = MagicMock()
    container.initialize_services = AsyncMock()
    container.pipefy_client = MagicMock()
    with patch("pipefy_mcp.server.ServicesContainer", return_value=container):
        yield container


@pytest.mark.anyio
async def test_register_tools(mocked_container):
    """The full Pipefy tool surface is reachable through an MCP session.

    Builds its own app with an explicit ``remote_mode=False`` (so the ambient
    ``PIPEFY_MCP_REMOTE_MODE`` cannot change the surface) under ``mocked_container``
    (so entering the lifespan does not resolve real auth).
    """
    app = build_pipefy_mcp_server(remote_mode=False)
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
def test_run_server_builds_the_stdio_server_and_runs_it():
    """The default (stdio) profile builds at startup and delegates to mcp.run()."""
    with patch("pipefy_mcp.server.build_pipefy_mcp_server") as mock_build:
        run_server()
        mock_build.assert_called_once_with(remote_mode=None)
        mock_build.return_value.run.assert_called_once_with()


# --- Registration happens once, at construction (not in the lifespan) --------


@pytest.mark.unit
def test_build_server_registers_the_full_surface(mocked_container):
    """The default (local) profile registers every Pipefy tool up front."""
    app = build_pipefy_mcp_server(remote_mode=False)
    registered = {t.name for t in app._tool_manager.list_tools()}
    assert registered == set(PIPEFY_TOOL_NAMES)


@pytest.mark.unit
def test_build_server_remote_mode_exposes_only_the_remote_safe_seed(mocked_container):
    """The remote profile withholds every tool not marked remote-safe."""
    app = build_pipefy_mcp_server(remote_mode=True)
    exposed = {t.name for t in app._tool_manager.list_tools()} & PIPEFY_TOOL_NAMES
    assert 0 < len(exposed) < len(PIPEFY_TOOL_NAMES)
    assert "get_organization" in exposed
    assert "upload_attachment_to_card" not in exposed
    assert "execute_graphql" not in exposed


@pytest.mark.unit
def test_second_registration_pass_is_rejected_by_collision_preflight(mocked_container):
    """A second registration pass on the same app is rejected by the preflight.

    The guard is ``check_for_name_collisions()``: the first pass already
    registered the Pipefy names on this app, so the second pass's preflight sees
    them and raises. FastMCP's own ``add_tool`` would silently dedup duplicate
    names rather than raise, so the preflight is what makes re-registration safe
    to forbid. This is why registration runs once, at construction, and the
    lifespan (which Streamable HTTP re-enters per session) never re-registers.
    """
    app = build_pipefy_mcp_server(remote_mode=False)
    with pytest.raises(RuntimeError, match="already exist"):
        _register_pipefy_tools(app, remote_mode=False)


# --- The lifespan owns resources only ----------------------------------------


@pytest.mark.anyio
async def test_lifespan_initializes_services_and_yields_container_without_registering(
    mocked_container,
):
    """The lifespan builds a container, initializes it, and yields it; no tools added."""
    app = FastMCP("lifespan-resources-test")

    @app.tool()
    async def foreign_mcp_tool() -> str:
        """Pre-existing tool; the lifespan must not touch the tool table."""
        return "ok"

    with patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS):
        async with lifespan(app) as yielded:
            names = {t.name for t in app._tool_manager.list_tools()}

    assert yielded is mocked_container
    mocked_container.initialize_services.assert_awaited_once()
    # No Pipefy tools were registered by the lifespan; only the foreign tool.
    assert names == {"foreign_mcp_tool"}


@pytest.mark.anyio
async def test_repeat_lifespan_reinitializes_each_visit_and_leaves_tools_untouched(
    mocked_container,
):
    """Re-entering the lifespan builds and initializes a fresh container, never registers.

    Streamable HTTP re-enters the lifespan per session; each session gets its own
    initialized container, and the tool table is never mutated.
    """
    app = FastMCP("lifespan-repeat-test")

    @app.tool()
    async def foreign_mcp_tool() -> str:
        """Must survive both visits untouched."""
        return "ok"

    with patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS):
        async with lifespan(app):
            first = {t.name for t in app._tool_manager.list_tools()}
        async with lifespan(app):
            second = {t.name for t in app._tool_manager.list_tools()}

    assert first == second == {"foreign_mcp_tool"}
    # Resources are initialized per visit; the tool table is never mutated.
    assert mocked_container.initialize_services.await_count == 2


@pytest.mark.unit
@pytest.mark.anyio
async def test_lifespan_logs_error_when_initialization_raises():
    """When service init raises, logger.exception runs and the error propagates."""
    app = FastMCP("lifespan-init-fail")
    mock_container = MagicMock()
    mock_container.initialize_services = AsyncMock(
        side_effect=ValueError("init failed")
    )
    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch("pipefy_mcp.server.ServicesContainer", return_value=mock_container),
        patch("pipefy_mcp.server.logger") as mock_logger,
    ):
        with pytest.raises(ValueError, match="init failed"):
            async with lifespan(app):
                pass

        mock_logger.exception.assert_called_once()
        call_msg = mock_logger.exception.call_args[0][0]
        assert "Fatal error during server lifespan" in call_msg


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
def test_run_server_http_builds_the_app_and_serves_over_streamable_http():
    """The HTTP path builds through the shared builder and serves streamable-http."""
    fake_app = MagicMock()
    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch(
            "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
        ) as mock_build,
    ):
        run_server(http=True, host="127.0.0.1", port=9123, remote_mode=True)

    mock_build.assert_called_once_with(
        remote_mode=True, host="127.0.0.1", port=9123, resource_server=None
    )
    fake_app.run.assert_called_once_with("streamable-http")


@pytest.mark.unit
def test_run_server_http_fills_host_and_port_from_settings_when_unset():
    """Unset host/port resolve to the configured PIPEFY_MCP_HOST / PIPEFY_MCP_PORT."""
    fake_app = MagicMock()
    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch(
            "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
        ) as mock_build,
    ):
        run_server(http=True)

    _, kwargs = mock_build.call_args
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8000


@pytest.mark.unit
def test_run_server_http_respects_an_explicit_zero_port():
    """``port=0`` (let the OS pick) must not be swallowed as a falsy default."""
    fake_app = MagicMock()
    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch(
            "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
        ) as mock_build,
    ):
        run_server(http=True, host="127.0.0.1", port=0)

    _, kwargs = mock_build.call_args
    assert kwargs["port"] == 0


@pytest.mark.unit
def test_run_server_http_refuses_non_loopback_before_building():
    """The loopback guard fires before the app is built or served."""
    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch("pipefy_mcp.server.build_pipefy_mcp_server") as mock_build,
    ):
        with pytest.raises(RuntimeError, match="Refusing to serve"):
            run_server(http=True, host="0.0.0.0", port=9123, remote_mode=True)

    mock_build.assert_not_called()


# --- Resource-server role (OAuth 2.0 inbound bearer validation) --------------


@pytest.mark.unit
def test_stdio_build_has_no_inbound_auth(mocked_container):
    """The stdio profile builds with no inbound auth wired into FastMCP."""
    app = build_pipefy_mcp_server(remote_mode=False)
    assert app.settings.auth is None


@pytest.mark.unit
def test_build_with_resource_server_wires_inbound_auth(mocked_container):
    """An enabled resource-server pair wires FastMCP's auth + token verifier."""
    app = build_pipefy_mcp_server(
        remote_mode=True, resource_server=_resource_server_pair()
    )
    assert app.settings.auth is not None
    assert str(app.settings.auth.resource_server_url).rstrip("/") == _RS_RESOURCE


def _asgi_client(app):
    transport = httpx.ASGITransport(app=app.streamable_http_app())
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.unit
async def test_http_unauthenticated_request_gets_401_challenge(mocked_container):
    """A request with no bearer is rejected with a 401 + WWW-Authenticate challenge.

    The auth middleware runs before the MCP handler, so no session (and no
    network) is needed: the challenge points at the protected-resource metadata.
    """
    app = build_pipefy_mcp_server(
        remote_mode=True, resource_server=_resource_server_pair()
    )
    async with _asgi_client(app) as client:
        resp = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1}
        )
    assert resp.status_code == 401
    assert "resource_metadata=" in resp.headers["www-authenticate"]


@pytest.mark.unit
async def test_http_serves_protected_resource_metadata(mocked_container):
    """The RFC 9728 metadata route is served at the resource's well-known path."""
    app = build_pipefy_mcp_server(
        remote_mode=True, resource_server=_resource_server_pair()
    )
    async with _asgi_client(app) as client:
        resp = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resource"].rstrip("/") == _RS_RESOURCE
    advertised = [s.rstrip("/") for s in body["authorization_servers"]]
    assert _RS_ISSUER in advertised
