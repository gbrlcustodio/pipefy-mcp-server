import json
from contextlib import asynccontextmanager
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from _rs_fixtures import RS_ISSUER, RS_JWKS_URI, RS_RESOURCE, remote_rs_settings
from mcp.server.mcpserver import MCPServer
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_auth import AuthSettings
from pipefy_sdk import PipefySettings

from pipefy_mcp.core.tool_middleware import ToolCallContext, short_circuit_error
from pipefy_mcp.core.transport_security import build_transport_security
from pipefy_mcp.observability.tool_log_middleware import tool_log_middleware
from pipefy_mcp.server import (
    _make_lifespan,
    _register_pipefy_tools,
    _serve_streamable_http,
    build_pipefy_mcp_server,
    default_tool_middlewares,
    run_server,
)
from pipefy_mcp.settings import McpSettings, Settings, resolve_mcp_settings
from pipefy_mcp.tools.registry import PIPEFY_TOOL_NAMES
from pipefy_mcp.tools.toolsets import DOMAINS, POWER_GRAPHQL_TOOLS

_MINIMAL_PIPEFY_SETTINGS = Settings(
    pipefy=PipefySettings(base_url="https://api.pipefy.com"),
    auth=AuthSettings(),
)

# The same minimal settings under the remote profile, for builder tests that need
# the default-deny remote-safe surface without going through run_server.
_REMOTE_PROFILE_SETTINGS = _MINIMAL_PIPEFY_SETTINGS.model_copy(
    update={"mcp": McpSettings(profile="remote")}
)

# A fully-configured remote deployment: the remote profile plus the resource-server
# identity and JWT validation config. The runtime's ``for_profile`` builds the
# inbound ``(verifier, auth)`` pair from these with no network at build, so builder
# tests can exercise inbound auth without creds or a mocked runtime.
_REMOTE_RS_SETTINGS = remote_rs_settings()


@pytest.fixture
def remote_rs_env(monkeypatch):
    """Configure the resource-server env so the remote profile resolves an RS.

    ``resolve_mcp_settings`` builds the rs/jwt models from the environment, so the
    remote profile's mandatory resource server comes from these vars (the same
    values as a configured deployment). The explicit ``JWKS_URI`` skips OIDC
    discovery, so building the resource server does no network I/O.
    """
    monkeypatch.setenv("PIPEFY_MCP_RS_RESOURCE_SERVER_URL", RS_RESOURCE)
    monkeypatch.setenv("PIPEFY_JWT_ISSUER_URL", RS_ISSUER)
    monkeypatch.setenv("PIPEFY_JWT_JWKS_URI", RS_JWKS_URI)


@pytest.fixture
def mocked_runtime():
    """Patch the runtime factory with a no-network stand-in.

    ``build_pipefy_mcp_server`` builds the app-scoped runtime via
    :meth:`McpRuntime.for_profile`, which on the local profile resolves a credential
    and fails fast. This intercepts the factory so building resolves no real
    credential, ``session_for_request`` yields a stand-in a tool can resolve, and
    ``inbound_auth`` is ``None`` (no resource server, matching the local profile).
    """
    runtime = MagicMock()
    runtime.session_for_request.return_value = MagicMock()
    runtime.inbound_auth = None
    runtime.transport_security = None
    with patch("pipefy_mcp.server.McpRuntime.for_profile", return_value=runtime):
        yield runtime


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
def test_build_pipefy_mcp_server_passes_log_level_to_fastmcp(mocked_runtime):
    settings = _MINIMAL_PIPEFY_SETTINGS.model_copy(
        update={"mcp": McpSettings(log_level="WARNING")}
    )
    with patch("pipefy_mcp.server.FastMCP") as mock_fastmcp:
        build_pipefy_mcp_server(settings)
    assert mock_fastmcp.call_args.kwargs["log_level"] == "WARNING"


@pytest.mark.unit
def test_run_server_stdio_does_not_configure_structured_logging(monkeypatch):
    """Stdio must not install the structured emitter (HTTP-only configuration)."""
    monkeypatch.delenv("PIPEFY_MCP_PROFILE", raising=False)
    monkeypatch.delenv("PIPEFY_MCP_TRANSPORT", raising=False)
    with (
        patch("pipefy_mcp.server.configure_observability_logging") as mock_configure,
        patch("pipefy_mcp.server.build_pipefy_mcp_server"),
    ):
        run_server(
            resolve_mcp_settings(profile=None, transport=None, host=None, port=None)
        )
    mock_configure.assert_not_called()


@pytest.mark.unit
def test_run_server_builds_the_stdio_server_and_runs_it(monkeypatch):
    """The default (local/stdio) profile builds at startup and delegates to mcp.run()."""
    monkeypatch.delenv("PIPEFY_MCP_PROFILE", raising=False)
    monkeypatch.delenv("PIPEFY_MCP_TRANSPORT", raising=False)
    with patch("pipefy_mcp.server.build_pipefy_mcp_server") as mock_build:
        run_server(
            resolve_mcp_settings(profile=None, transport=None, host=None, port=None)
        )
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
    # The attachment tools are remote-safe via file_url (file_path rejected per call).
    assert "upload_attachment_to_card" in exposed
    # raw-GraphQL escape hatch is remote-safe (#308)
    assert "execute_graphql" in exposed
    # A secret-handling write stays withheld, so default-deny still holds.
    assert "create_llm_provider" not in exposed


@pytest.mark.unit
def test_build_server_applies_toolset_selection(mocked_runtime):
    """A ``toolsets`` selection narrows the registered surface to the named domains."""
    settings = _MINIMAL_PIPEFY_SETTINGS.model_copy(
        update={"mcp": McpSettings(toolsets="database")}
    )
    app = build_pipefy_mcp_server(settings)
    exposed = {t.name for t in app._tool_manager.list_tools()} & PIPEFY_TOOL_NAMES
    assert exposed == set(DOMAINS["database"])


@pytest.mark.unit
def test_build_server_power_profile_hides_curated_tools_behind_meta_tools(
    mocked_runtime,
):
    """The power profile exposes the meta-tools + raw GraphQL and hides the rest."""
    settings = _MINIMAL_PIPEFY_SETTINGS.model_copy(
        update={"mcp": McpSettings(toolsets="power")}
    )
    app = build_pipefy_mcp_server(settings)
    names = {t.name for t in app._tool_manager.list_tools()}
    assert {
        "search_tools",
        "describe_tool",
        "execute_tool",
        "get_tool_categories",
    } <= names
    # Of the curated surface, only the raw-GraphQL tools remain visible by name.
    assert names & PIPEFY_TOOL_NAMES == set(POWER_GRAPHQL_TOOLS)
    assert "get_pipe" not in names


@pytest.mark.unit
def test_build_server_power_with_unknown_token_fails_closed(mocked_runtime):
    """An unknown token alongside `power` fails at build, matching the domain path.

    ``wants_power`` short-circuits to ``apply_power_profile``, which does not call
    ``resolve_selection``; without the explicit validation a value like
    ``power,typo`` (e.g. via ``PIPEFY_MCP_TOOLSETS``) would silently start the server.
    """
    settings = _MINIMAL_PIPEFY_SETTINGS.model_copy(
        update={"mcp": McpSettings(toolsets="power,typo")}
    )
    with pytest.raises(ValueError, match="unknown toolset"):
        build_pipefy_mcp_server(settings)


@pytest.mark.unit
def test_default_tool_middlewares_seeds_the_logger_under_remote():
    """The composition root seeds structured tool-call logging for the hosted profile."""
    assert default_tool_middlewares(_REMOTE_PROFILE_SETTINGS) == [tool_log_middleware]


@pytest.mark.unit
def test_default_tool_middlewares_seeds_nothing_under_local():
    """The local profile gets no default middleware; the chain stays empty."""
    assert default_tool_middlewares(_MINIMAL_PIPEFY_SETTINGS) == []


@pytest.mark.anyio
async def test_extra_tool_middlewares_register_through_the_public_builder(
    mocked_runtime,
):
    """A consumer's middleware installs via ``extra_tool_middlewares``, no private reach.

    Drives a real MCP session against an app built through the public builder: a
    short-circuiting middleware passed as ``extra_tool_middlewares`` returns its
    envelope, so the consumer's middleware demonstrably runs in the installed chain
    (the tool never executes, so no live client is needed). The short-circuit
    envelope's shape is pinned elsewhere; this asserts only that the seam wires it in.
    """

    async def deny(ctx: ToolCallContext, call_next):
        return short_circuit_error("blocked by consumer", code="DENIED")

    app = build_pipefy_mcp_server(
        _MINIMAL_PIPEFY_SETTINGS, extra_tool_middlewares=[deny]
    )
    session = create_client_session(
        app,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )
    async with session as s:
        result = await s.call_tool("get_organization", {})

    assert result.isError is True
    assert json.loads(result.content[0].text)["error"]["code"] == "DENIED"


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
        _register_pipefy_tools(app, remote_mode=False, toolsets=None)


# --- The lifespan owns resources only ----------------------------------------


@pytest.mark.anyio
async def test_lifespan_yields_the_runtime_without_registering(
    mocked_runtime,
):
    """The lifespan yields the app-scoped runtime and adds no tools."""
    app = MCPServer("lifespan-resources-test")

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
    app = MCPServer("lifespan-repeat-test")

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
        run_server(
            resolve_mcp_settings(profile="local", transport=None, host=None, port=None)
        )

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
    with (
        patch(
            "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
        ) as mock_build,
        patch("pipefy_mcp.server.anyio.run") as mock_anyio_run,
    ):
        settings = resolve_mcp_settings(
            profile="local", transport="http", host="127.0.0.1", port=9200
        )
        run_server(settings)

    mock_build.assert_called_once()
    (built_settings,), _ = mock_build.call_args
    assert built_settings.mcp.profile == "local"
    assert built_settings.mcp.host == "127.0.0.1"
    assert built_settings.mcp.port == 9200
    mock_anyio_run.assert_called_once_with(_serve_streamable_http, fake_app, settings)


@pytest.mark.unit
def test_run_server_remote_profile_defaults_to_http_transport(
    monkeypatch, remote_rs_env
):
    """``--profile remote`` with no ``--transport`` serves HTTP (profile-derived default)."""
    monkeypatch.delenv("PIPEFY_MCP_TRANSPORT", raising=False)
    fake_app = MagicMock()
    with (
        patch(
            "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
        ) as mock_build,
        patch("pipefy_mcp.server.anyio.run") as mock_anyio_run,
    ):
        settings = resolve_mcp_settings(
            profile="remote", transport=None, host="127.0.0.1", port=9300
        )
        run_server(settings)

    mock_anyio_run.assert_called_once_with(_serve_streamable_http, fake_app, settings)
    (built_settings,), _ = mock_build.call_args
    assert built_settings.mcp.profile == "remote"


@pytest.mark.unit
def test_run_server_http_builds_the_app_and_serves_over_streamable_http(remote_rs_env):
    """The remote HTTP path builds through the shared builder and serves streamable-http."""
    fake_app = MagicMock()
    with (
        patch(
            "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
        ) as mock_build,
        patch("pipefy_mcp.server.anyio.run") as mock_anyio_run,
    ):
        settings = resolve_mcp_settings(
            profile="remote", transport="http", host="127.0.0.1", port=9123
        )
        run_server(settings)

    (built_settings,), _ = mock_build.call_args
    assert built_settings.mcp.profile == "remote"
    assert built_settings.mcp.host == "127.0.0.1"
    assert built_settings.mcp.port == 9123
    mock_anyio_run.assert_called_once_with(_serve_streamable_http, fake_app, settings)


@pytest.mark.anyio
async def test_serve_streamable_http_disables_uvicorn_access_log(remote_rs_env):
    """Structured request lines replace uvicorn access logs on the HTTP transport."""
    fake_app = MagicMock()
    mock_http_app = MagicMock()
    settings = resolve_mcp_settings(
        profile="remote", transport="http", host="127.0.0.1", port=9123
    )
    with (
        patch("pipefy_mcp.server.configure_observability_logging") as mock_configure,
        patch(
            "pipefy_mcp.server.wire_hosted_observability",
            return_value=mock_http_app,
        ) as mock_wire,
        patch("uvicorn.Config") as mock_config_cls,
        patch("uvicorn.Server") as mock_server_cls,
    ):
        mock_server_cls.return_value.serve = AsyncMock()
        await _serve_streamable_http(fake_app, settings)

    mock_configure.assert_called_once_with()
    mock_wire.assert_called_once_with(fake_app)
    mock_config_cls.assert_called_once_with(
        mock_http_app,
        host="127.0.0.1",
        port=9123,
        log_level="info",
        access_log=False,
    )
    mock_server_cls.return_value.serve.assert_awaited_once()


@pytest.mark.unit
def test_run_server_remote_without_resource_server_fails_fast(monkeypatch):
    """``--profile remote`` with no RESOURCE_SERVER_URL fails fast building the runtime.

    The remote profile acts on behalf of the caller, so it needs a per-request
    bearer to validate. Without a configured resource server there is no
    per-request identity, and silently falling back to the single startup
    credential would defeat the profile, so the runtime refuses to build.
    """
    monkeypatch.delenv("PIPEFY_MCP_RS_RESOURCE_SERVER_URL", raising=False)
    with pytest.raises(RuntimeError, match="requires a resource server"):
        run_server(
            resolve_mcp_settings(
                profile="remote", transport="http", host="127.0.0.1", port=9123
            )
        )


@pytest.mark.unit
def test_run_server_http_fills_host_and_port_from_settings_when_unset(
    monkeypatch, remote_rs_env
):
    """Unset host/port resolve to the configured PIPEFY_MCP_HOST / PIPEFY_MCP_PORT."""
    monkeypatch.delenv("PIPEFY_MCP_HOST", raising=False)
    monkeypatch.delenv("PIPEFY_MCP_PORT", raising=False)
    fake_app = MagicMock()
    with (
        patch(
            "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
        ) as mock_build,
        patch("pipefy_mcp.server.anyio.run"),
    ):
        run_server(
            resolve_mcp_settings(
                profile="remote", transport="http", host=None, port=None
            )
        )

    (built_settings,), _ = mock_build.call_args
    assert built_settings.mcp.host == "127.0.0.1"
    assert built_settings.mcp.port == 8000


@pytest.mark.unit
def test_run_server_http_respects_an_explicit_zero_port(remote_rs_env):
    """``port=0`` (let the OS pick) must not be swallowed as a falsy default."""
    fake_app = MagicMock()
    with (
        patch(
            "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
        ) as mock_build,
        patch("pipefy_mcp.server.anyio.run"),
    ):
        run_server(
            resolve_mcp_settings(
                profile="remote", transport="http", host="127.0.0.1", port=0
            )
        )

    (built_settings,), _ = mock_build.call_args
    assert built_settings.mcp.port == 0


@pytest.mark.unit
def test_run_server_remote_serves_off_loopback_without_a_bind_guard(remote_rs_env):
    """The resource-server profile binds a non-loopback host with no guard or bypass.

    Auth posture, not bind interface, is the axis: ``remote`` validates a
    per-request bearer, so ``0.0.0.0`` is a legitimate hosted bind and nothing
    refuses it (a container binds ``0.0.0.0`` and is still private).
    """
    fake_app = MagicMock()
    with (
        patch(
            "pipefy_mcp.server.build_pipefy_mcp_server", return_value=fake_app
        ) as mock_build,
        patch("pipefy_mcp.server.anyio.run") as mock_anyio_run,
    ):
        settings = resolve_mcp_settings(
            profile="remote", transport="http", host="0.0.0.0", port=9123
        )
        run_server(settings)

    (built_settings,), _ = mock_build.call_args
    assert built_settings.mcp.host == "0.0.0.0"
    mock_anyio_run.assert_called_once_with(_serve_streamable_http, fake_app, settings)


# --- Resource-server role (OAuth 2.0 inbound bearer validation) --------------


@pytest.mark.unit
def test_stdio_build_has_no_inbound_auth(mocked_runtime):
    """The stdio profile builds with no inbound auth wired into FastMCP."""
    app = build_pipefy_mcp_server(_MINIMAL_PIPEFY_SETTINGS)
    assert app.settings.auth is None


@pytest.mark.unit
def test_build_with_resource_server_wires_inbound_auth():
    """The remote profile with a configured RS wires FastMCP's auth + token verifier."""
    app = build_pipefy_mcp_server(_REMOTE_RS_SETTINGS)
    assert app.settings.auth is not None
    assert str(app.settings.auth.resource_server_url).rstrip("/") == RS_RESOURCE


def _asgi_client(app):
    transport = httpx.ASGITransport(app=app.streamable_http_app())
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@asynccontextmanager
async def _serving_asgi_client(app):
    """An ASGI client with the app's lifespan running.

    The transport's DNS-rebinding Host check sits behind the streamable-HTTP
    session manager, whose task group is started by the ASGI lifespan. httpx's
    ASGITransport does not run lifespan events, so drive Starlette's lifespan
    context explicitly (the 401/metadata tests do not need this because they
    short-circuit before the session manager).
    """
    asgi = app.streamable_http_app()
    async with asgi.router.lifespan_context(asgi):
        transport = httpx.ASGITransport(app=asgi)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


@pytest.mark.unit
async def test_http_unauthenticated_request_gets_401_challenge():
    """A request with no bearer is rejected with a 401 + WWW-Authenticate challenge.

    The auth middleware runs before the MCP handler, so no session (and no
    network) is needed: the challenge points at the protected-resource metadata.
    """
    app = build_pipefy_mcp_server(_REMOTE_RS_SETTINGS)
    async with _asgi_client(app) as client:
        resp = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1}
        )
    assert resp.status_code == 401
    assert "resource_metadata=" in resp.headers["www-authenticate"]


@pytest.mark.unit
async def test_http_serves_protected_resource_metadata():
    """The RFC 9728 metadata route is served at the resource's well-known path."""
    app = build_pipefy_mcp_server(_REMOTE_RS_SETTINGS)
    async with _asgi_client(app) as client:
        resp = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resource"].rstrip("/") == RS_RESOURCE
    advertised = [s.rstrip("/") for s in body["authorization_servers"]]
    assert RS_ISSUER in advertised


# --- transport allowlist (DNS-rebinding) reaches FastMCP and the transport ----

_PUBLIC_HOST_PING = {
    "json": {"jsonrpc": "2.0", "method": "ping", "id": 1},
    "headers": {"host": "mcp.pipefy.com"},
}


@pytest.mark.unit
def test_build_passes_the_runtimes_none_transport_security_to_fastmcp(mocked_runtime):
    """When the runtime built no allowlist, FastMCP keeps its own loopback default."""
    with patch("pipefy_mcp.server.FastMCP") as mock_fastmcp:
        build_pipefy_mcp_server(_MINIMAL_PIPEFY_SETTINGS)
    assert mock_fastmcp.call_args.kwargs["transport_security"] is None


@pytest.mark.unit
def test_build_passes_the_runtimes_allowlist_to_fastmcp(mocked_runtime):
    """The allowlist the runtime built reaches the FastMCP constructor verbatim."""
    mocked_runtime.transport_security = build_transport_security(
        McpSettings(allowed_hosts=["mcp.pipefy.com"]), None
    )
    with patch("pipefy_mcp.server.FastMCP") as mock_fastmcp:
        build_pipefy_mcp_server(_MINIMAL_PIPEFY_SETTINGS)
    assert (
        mock_fastmcp.call_args.kwargs["transport_security"]
        is mocked_runtime.transport_security
    )


@pytest.mark.unit
async def test_http_loopback_default_rejects_a_public_host(mocked_runtime):
    """The default (loopback-only) allowlist answers 421 to a public Host header.

    This is the behavior a fronted deployment hits before the allowlist is
    configured: MCPServer auto-enables the loopback allowlist on the 127.0.0.1
    construction host, so a proxied public Host is a DNS-rebinding rejection.
    """
    app = build_pipefy_mcp_server(_MINIMAL_PIPEFY_SETTINGS)
    async with _serving_asgi_client(app) as client:
        resp = await client.post("/mcp", **_PUBLIC_HOST_PING)
    assert resp.status_code == 421


@pytest.mark.unit
async def test_http_configured_allowlist_accepts_a_public_host(mocked_runtime):
    """With the public host allowlisted, the same request clears the Host gate.

    It no longer 421s; it reaches the transport handler (which then fails on the
    missing session, not on DNS-rebinding), proving the allowlist widened the gate.
    """
    mocked_runtime.transport_security = build_transport_security(
        McpSettings(allowed_hosts=["mcp.pipefy.com"]), None
    )
    app = build_pipefy_mcp_server(_MINIMAL_PIPEFY_SETTINGS)
    async with _serving_asgi_client(app) as client:
        resp = await client.post("/mcp", **_PUBLIC_HOST_PING)
    assert resp.status_code != 421
