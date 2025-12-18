import pytest
from unittest.mock import MagicMock, patch

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.tools.registry import ToolRegistry


@pytest.fixture
def mock_mcp_server():
    """Fixture to create a mock FastMCP server."""
    return MagicMock(spec=FastMCP)


@pytest.fixture
def mock_services_container():
    """Fixture to create a mock ServicesContainer."""
    return MagicMock(spec=ServicesContainer)


def test_tool_registry_register_tools(mock_mcp_server, mock_services_container):
    """Test that the ToolRegistry correctly registers tools."""
    # Arrange
    with patch("pipefy_mcp.tools.registry.PipeTools") as mock_pipe_tools:
        registry = ToolRegistry(mcp=mock_mcp_server, services_container=mock_services_container)

        # Act
        registered_mcp = registry.register_tools()

        # Assert
        mock_pipe_tools.register.assert_called_once_with(mock_mcp_server)
        mock_mcp_server.tool.assert_called_once()
        mock_mcp_server.resource.assert_called_once()
        assert registered_mcp == mock_mcp_server
