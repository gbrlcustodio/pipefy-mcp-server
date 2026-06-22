from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_auth import AuthSettings
from pipefy_sdk import PipefySettings

from pipefy_mcp.server import (
    _register_pipefy_tools,
    build_pipefy_mcp_server,
    lifespan,
    run_server,
)
from pipefy_mcp.settings import Settings
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
