import pytest
from unittest.mock import MagicMock, patch

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.server import lifespan, run_server


@pytest.mark.asyncio
async def test_lifespan():
    """Test the lifespan function of the server."""
    # Arrange
    mock_app = MagicMock(spec=FastMCP)
    mock_services_container = MagicMock()
    mock_tool_registry = MagicMock()

    with patch("pipefy_mcp.server.ServicesContainer", return_value=mock_services_container):
        with patch("pipefy_mcp.server.ToolRegistry", return_value=mock_tool_registry):
            with patch("pipefy_mcp.server.settings") as mock_settings:
                with patch("os._exit") as mock_exit:
                    # Act
                    async with lifespan(mock_app):
                        # Assert
                        mock_services_container.get_instance.assert_called_once()
                        mock_services_container.initialize_services.assert_called_once_with(mock_settings)
                        mock_tool_registry.register_tools.assert_called_once()

                    mock_exit.assert_called_once_with(0)


def test_run_server():
    """Test the run_server function."""
    # Arrange
    with patch("pipefy_mcp.server.mcp") as mock_mcp:
        # Act
        run_server()

        # Assert
        mock_mcp.run.assert_called_once()
