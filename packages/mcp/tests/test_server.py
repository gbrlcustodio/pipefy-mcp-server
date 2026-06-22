import socket
import threading
import time
from contextlib import closing, contextmanager
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_auth import AuthSettings
from pipefy_sdk import PipefySettings

from pipefy_mcp.server import (
    _assert_http_surface_is_safe,
    _register_pipefy_tools,
    build_pipefy_mcp_server,
    lifespan,
    run_http_server,
    run_server,
)
from pipefy_mcp.settings import McpSettings, Settings
from pipefy_mcp.tools.registry import PIPEFY_TOOL_NAMES

_MINIMAL_PIPEFY_SETTINGS = Settings(
    pipefy=PipefySettings(base_url="https://api.pipefy.com"),
    auth=AuthSettings(),
)


@pytest.fixture
def mocked_container():
    """Patch ``ServicesContainer.get_instance`` with a no-network container."""
    container = MagicMock()
    container.initialize_services = AsyncMock()
    container.pipefy_client = MagicMock()
    with patch(
        "pipefy_mcp.server.ServicesContainer.get_instance",
        return_value=container,
    ):
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
def test_run_server_builds_the_server_and_runs_it_with_no_arguments():
    """run_server builds the server at startup and delegates to mcp.run() with no args."""
    with patch("pipefy_mcp.server.build_pipefy_mcp_server") as mock_build:
        run_server()
        mock_build.assert_called_once_with()
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
    """The lifespan initializes services and yields the container; it adds no tools."""
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
    """Re-entering the lifespan re-initializes services but never re-registers."""
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
    # Resources are re-initialized per visit; the tool table is never mutated.
    assert mocked_container.initialize_services.await_count == 2


@pytest.mark.unit
@pytest.mark.anyio
async def test_lifespan_logs_error_when_initialization_raises():
    """When service init raises, logger.exception runs and the error propagates."""
    app = FastMCP("lifespan-init-fail")
    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch("pipefy_mcp.server.ServicesContainer.get_instance") as mock_get_instance,
        patch("pipefy_mcp.server.logger") as mock_logger,
    ):
        mock_container = MagicMock()
        mock_container.initialize_services = AsyncMock(
            side_effect=ValueError("init failed")
        )
        mock_get_instance.return_value = mock_container

        with pytest.raises(ValueError, match="init failed"):
            async with lifespan(app):
                pass

        mock_logger.exception.assert_called_once()
        call_msg = mock_logger.exception.call_args[0][0]
        assert "Fatal error during server lifespan" in call_msg


# --- HTTP (Streamable) transport profile (#300) -----------------------------


def _build_http_app(remote_mode: bool) -> FastMCP:
    """Register tools on a fresh, lifespan-free app with a mocked client.

    Mirrors how ``run_http_server`` builds the HTTP app, minus the socket.
    """
    app = FastMCP("http-transport-test")
    mock_container = MagicMock()
    mock_container.initialize_services = AsyncMock()
    mock_container.pipefy_client = MagicMock()
    with patch(
        "pipefy_mcp.server.ServicesContainer.get_instance",
        return_value=mock_container,
    ):
        _register_pipefy_tools(app, remote_mode=remote_mode)
    return app


@pytest.mark.unit
@pytest.mark.parametrize(
    ("host", "remote_mode", "hatch"),
    [
        ("127.0.0.1", False, False),  # loopback, full surface
        ("localhost", False, False),  # loopback alias
        ("0.0.0.0", True, False),  # public but remote profile is the safe surface
        ("203.0.113.5", False, True),  # public, full surface, escape hatch set
    ],
)
def test_http_surface_interlock_allows(host, remote_mode, hatch):
    settings = Settings(
        pipefy=PipefySettings(base_url="https://api.pipefy.com"),
        auth=AuthSettings(),
        mcp=McpSettings(allow_full_surface_over_http=hatch),
    )
    with patch("pipefy_mcp.server.settings", settings):
        # Does not raise.
        _assert_http_surface_is_safe(host=host, remote_mode=remote_mode)


@pytest.mark.unit
def test_http_surface_interlock_refuses_public_full_surface_without_hatch():
    settings = Settings(
        pipefy=PipefySettings(base_url="https://api.pipefy.com"),
        auth=AuthSettings(),
        mcp=McpSettings(allow_full_surface_over_http=False),
    )
    with (
        patch("pipefy_mcp.server.settings", settings),
        pytest.raises(RuntimeError, match="Refusing to serve the full tool surface"),
    ):
        _assert_http_surface_is_safe(host="0.0.0.0", remote_mode=False)


@pytest.mark.unit
def test_run_http_server_registers_once_without_lifespan_and_serves():
    fake_app = MagicMock()
    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch("pipefy_mcp.server.anyio.run") as mock_anyio_run,
        patch("pipefy_mcp.server.FastMCP", return_value=fake_app) as mock_fastmcp,
        patch("pipefy_mcp.server._register_pipefy_tools") as mock_register,
        patch("pipefy_mcp.server.ServicesContainer.get_instance"),
    ):
        run_http_server(host="127.0.0.1", port=9123, remote_mode=True)

    mock_anyio_run.assert_called_once()
    _, fastmcp_kwargs = mock_fastmcp.call_args
    assert fastmcp_kwargs["host"] == "127.0.0.1"
    assert fastmcp_kwargs["port"] == 9123
    assert "lifespan" not in fastmcp_kwargs
    mock_register.assert_called_once_with(fake_app, remote_mode=True)
    fake_app.run.assert_called_once_with("streamable-http")


@pytest.mark.unit
def test_run_http_server_interlock_refuses_before_initializing_services():
    """The interlock fires before any service init or socket bind."""
    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch("pipefy_mcp.server.anyio.run") as mock_anyio_run,
        patch("pipefy_mcp.server.FastMCP") as mock_fastmcp,
    ):
        with pytest.raises(RuntimeError, match="Refusing to serve"):
            run_http_server(host="0.0.0.0", port=9123, remote_mode=False)

    mock_anyio_run.assert_not_called()
    mock_fastmcp.assert_not_called()


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def _served_http_app(app: FastMCP, host: str, port: int):
    """Serve ``app`` over real Streamable HTTP in a background thread."""
    config = uvicorn.Config(
        app.streamable_http_app(), host=host, port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        if not server.started:
            raise RuntimeError("HTTP server did not start in time")
        yield
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.anyio
async def test_http_client_completes_a_tool_call_over_streamable_http():
    """Acceptance: a client connects over HTTP, lists the remote surface, and calls a tool."""
    app = _build_http_app(remote_mode=True)

    @app.tool()
    async def ping() -> str:
        """Minimal tool to prove a tools/call round-trip over HTTP."""
        return "pong"

    host, port = "127.0.0.1", _free_port()
    with _served_http_app(app, host, port):
        url = f"http://{host}:{port}/mcp"
        async with streamable_http_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                listed = {tool.name for tool in (await session.list_tools()).tools}
                assert "get_organization" in listed
                assert "upload_attachment_to_card" not in listed

                result = await session.call_tool("ping", {})
                assert any(
                    getattr(block, "text", "") == "pong" for block in result.content
                )
