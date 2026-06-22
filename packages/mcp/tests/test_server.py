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
from pipefy_mcp.server import mcp as mcp_server
from pipefy_mcp.settings import Settings
from pipefy_mcp.tools.registry import PIPEFY_TOOL_NAMES


@pytest.fixture(scope="module")
def client_session():
    return create_client_session(
        mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )


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
async def test_register_tools(client_session):
    expected_tool_names = sorted(PIPEFY_TOOL_NAMES)

    with patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS):
        async with client_session as session:
            result = await session.list_tools()
            actual_tool_names = sorted(tool.name for tool in result.tools)

            assert actual_tool_names == expected_tool_names, (
                "Registered tool names must match PIPEFY_TOOL_NAMES"
            )


@pytest.mark.unit
def test_run_server_starts_mcp_with_no_arguments():
    """run_server delegates to mcp.run() without extra arguments."""
    with patch("pipefy_mcp.server.mcp") as mock_mcp:
        run_server()
        mock_mcp.run.assert_called_once_with()


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
def test_register_pipefy_tools_is_once_only_second_pass_collides(mocked_container):
    """A second registration on the same app collides.

    This is why registration lives at construction and the lifespan no longer
    registers: under Streamable HTTP the lifespan runs per session, and a
    second registration pass would raise (or race) on the tool table.
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
