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


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def client_session():
    return create_client_session(
        mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )


# Minimal settings for server lifespan (test only lists tools).
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
    expected_tool_names = [
        "add_card_comment",
        "create_card",
        "delete_card",
        "fill_card_phase_fields",
        "find_cards",
        "get_card",
        "get_cards",
        "get_phase_fields",
        "get_pipe",
        "get_pipe_members",
        "get_start_form_fields",
        "move_card_to_phase",
        "search_pipes",
        "update_card",
        "update_card_field",
    ]

    with patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS):
        async with client_session as session:
            result = await session.list_tools()
            actual_tool_names = [tool.name for tool in result.tools]

            assert sorted(expected_tool_names) == sorted(actual_tool_names), (
                "Expected create_card to be available"
            )


@pytest.mark.unit
def test_run_server_calls_logger_and_mcp_run():
    """run_server logs and calls mcp.run()."""
    with (
        patch("pipefy_mcp.server.logger") as mock_logger,
        patch("pipefy_mcp.server.mcp") as mock_mcp,
    ):
        run_server()
        mock_logger.info.assert_called()
        mock_mcp.run.assert_called_once()


@pytest.mark.unit
@pytest.mark.anyio
async def test_lifespan_logs_error_when_initialization_raises():
    """When lifespan initialization raises, logger.error is called with the exception."""
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

        with pytest.raises(RuntimeError, match="didn't yield"):
            async with lifespan(app):
                pass

        mock_logger.error.assert_called_once()
        call_msg = mock_logger.error.call_args[0][0]
        assert "Error during server lifespan" in call_msg
        assert "init failed" in call_msg
