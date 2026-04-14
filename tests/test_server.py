from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.server import mcp as mcp_server
from pipefy_mcp.server import run_server
from pipefy_mcp.settings import PipefySettings, Settings
from pipefy_mcp.tools.registry import PIPEFY_TOOL_NAMES


@pytest.fixture(scope="module")
def client_session():
    return create_client_session(
        mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )


_MINIMAL_PIPEFY_SETTINGS = Settings(
    pipefy=PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://api.pipefy.com/oauth/token",
        oauth_client="test-client",
        oauth_secret="test-secret",
    )
)


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


@pytest.mark.anyio
async def test_repeat_lifespan_preserves_foreign_tools_and_stable_pipefy_names():
    """Second lifespan visit removes only Pipefy-owned tools, then re-registers; foreign tools stay."""
    from pipefy_mcp.server import lifespan

    app = FastMCP("repeat-lifespan-test")

    @app.tool()
    async def foreign_mcp_tool() -> str:
        """Registered outside ToolRegistry; must survive a second lifespan run."""
        return "ok"

    mock_container = MagicMock()
    mock_container.pipefy_client = MagicMock()

    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch(
            "pipefy_mcp.server.ServicesContainer.get_instance",
            return_value=mock_container,
        ),
    ):
        async with lifespan(app):
            first_names = {t.name for t in app._tool_manager.list_tools()}
        async with lifespan(app):
            second_names = {t.name for t in app._tool_manager.list_tools()}

    assert first_names == second_names
    assert "foreign_mcp_tool" in second_names
    assert "create_card" in second_names


@pytest.mark.unit
@pytest.mark.anyio
async def test_lifespan_logs_error_when_initialization_raises():
    """When lifespan initialization raises, logger.exception runs and the error propagates."""
    from pipefy_mcp.server import lifespan

    app = FastMCP("test")
    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch("pipefy_mcp.server.ServicesContainer.get_instance") as mock_get_instance,
        patch("pipefy_mcp.server.logger") as mock_logger,
    ):
        mock_container = MagicMock()
        mock_container.initialize_services.side_effect = ValueError("init failed")
        mock_get_instance.return_value = mock_container

        with pytest.raises(ValueError, match="init failed"):
            async with lifespan(app):
                pass

        mock_logger.exception.assert_called_once()
        call_msg = mock_logger.exception.call_args[0][0]
        assert "Fatal error during server lifespan" in call_msg


@pytest.mark.unit
@pytest.mark.anyio
async def test_lifespan_failed_register_tools_does_not_mark_repeat_visit_state():
    """``register_tools`` failure must not set repeat-visit flag or owned tool names."""
    import pipefy_mcp.core.pipefy_tool_lifecycle as ptl
    from pipefy_mcp.server import lifespan

    app = FastMCP("fail-register-tools")
    mock_container = MagicMock()
    mock_container.pipefy_client = MagicMock()

    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch(
            "pipefy_mcp.server.ServicesContainer.get_instance",
            return_value=mock_container,
        ),
        patch("pipefy_mcp.server.ToolRegistry") as mock_registry_cls,
    ):
        mock_registry = MagicMock()
        mock_registry_cls.return_value = mock_registry
        mock_registry.pipefy_tool_names = frozenset({"create_card"})
        mock_registry.register_tools.side_effect = RuntimeError("register failed")

        with pytest.raises(RuntimeError, match="register failed"):
            async with lifespan(app):
                pass

    assert getattr(app, ptl.PIPEFY_REPEAT_VISIT_FLAG_ATTR, False) is False
    assert getattr(app, ptl.PIPEFY_OWNED_TOOL_NAMES_ATTR, None) is None


@pytest.mark.unit
@pytest.mark.anyio
async def test_lifespan_retry_after_failed_register_tools_succeeds():
    """After a failed ``register_tools``, a later successful run completes mark state."""
    import pipefy_mcp.core.pipefy_tool_lifecycle as ptl
    from pipefy_mcp.server import lifespan

    app = FastMCP("retry-after-fail")
    mock_container = MagicMock()
    mock_container.pipefy_client = MagicMock()

    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch(
            "pipefy_mcp.server.ServicesContainer.get_instance",
            return_value=mock_container,
        ),
        patch("pipefy_mcp.server.ToolRegistry") as mock_registry_cls,
    ):
        mock_fail = MagicMock()
        mock_fail.register_tools.side_effect = RuntimeError("register failed")
        mock_ok = MagicMock()
        mock_ok.register_tools.return_value = app
        mock_ok.pipefy_tool_names = frozenset({"create_card"})
        mock_registry_cls.side_effect = [mock_fail, mock_ok]

        with pytest.raises(RuntimeError, match="register failed"):
            async with lifespan(app):
                pass

        assert getattr(app, ptl.PIPEFY_REPEAT_VISIT_FLAG_ATTR, False) is False

        async with lifespan(app):
            pass

        mock_ok.register_tools.assert_called_once()
        assert getattr(app, ptl.PIPEFY_REPEAT_VISIT_FLAG_ATTR, False) is True
        assert getattr(app, ptl.PIPEFY_OWNED_TOOL_NAMES_ATTR) == {"create_card"}


@pytest.mark.unit
@pytest.mark.anyio
async def test_lifespan_tool_name_collision_fails_before_registration():
    """Foreign tool already named create_card: preflight raises; pending never set."""
    import pipefy_mcp.core.pipefy_tool_lifecycle as ptl
    from pipefy_mcp.server import lifespan

    app = FastMCP("collision-test")

    @app.tool()
    async def create_card() -> str:
        """Shadows Pipefy tool name; must trigger collision check."""
        return "foreign"

    mock_container = MagicMock()
    mock_container.pipefy_client = MagicMock()

    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch(
            "pipefy_mcp.server.ServicesContainer.get_instance",
            return_value=mock_container,
        ),
    ):
        with pytest.raises(
            RuntimeError, match="these names already exist: create_card"
        ):
            async with lifespan(app):
                pass

    assert not hasattr(app, ptl.PIPEFY_PENDING_TOOL_NAMES_ATTR)


@pytest.mark.unit
@pytest.mark.anyio
async def test_lifespan_partial_register_failure_cleans_pipefy_tools_retry_uses_new_client():
    """PipeTools registers then PipeConfigTools raises; cleanup; second run binds new client."""
    import pipefy_mcp.core.pipefy_tool_lifecycle as ptl
    from pipefy_mcp.server import lifespan
    from pipefy_mcp.tools.pipe_config_tools import PipeConfigTools
    from pipefy_mcp.tools.pipe_tools import PipeTools

    app = FastMCP("partial-reg")
    mock_container = MagicMock()
    client1 = MagicMock()
    client2 = MagicMock()
    mock_container.pipefy_client = client1

    pipe_tools_register_clients = []
    real_pipe_tools_register = PipeTools.register

    def wrapping_pipe_tools_register(mcp, client):
        pipe_tools_register_clients.append(client)
        return real_pipe_tools_register(mcp, client)

    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch(
            "pipefy_mcp.server.ServicesContainer.get_instance",
            return_value=mock_container,
        ),
        patch.object(PipeTools, "register", side_effect=wrapping_pipe_tools_register),
        patch.object(
            PipeConfigTools,
            "register",
            side_effect=RuntimeError("pipe config boom"),
        ),
    ):
        with pytest.raises(RuntimeError, match="pipe config boom"):
            async with lifespan(app):
                pass

    assert not hasattr(app, ptl.PIPEFY_PENDING_TOOL_NAMES_ATTR)
    assert getattr(app, ptl.PIPEFY_REPEAT_VISIT_FLAG_ATTR, False) is False
    after_fail_names = {t.name for t in app._tool_manager.list_tools()}
    assert "create_card" not in after_fail_names

    mock_container.pipefy_client = client2
    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch(
            "pipefy_mcp.server.ServicesContainer.get_instance",
            return_value=mock_container,
        ),
        patch.object(
            PipeTools,
            "register",
            side_effect=wrapping_pipe_tools_register,
        ),
    ):
        async with lifespan(app):
            pass

    assert pipe_tools_register_clients[0] is client1
    assert pipe_tools_register_clients[-1] is client2
    assert "create_card" in {t.name for t in app._tool_manager.list_tools()}
