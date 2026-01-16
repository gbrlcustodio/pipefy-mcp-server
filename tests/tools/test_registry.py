from unittest.mock import Mock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.tools.registry import ToolRegistry


class TestToolRegistry:
    """Test cases for ToolRegistry"""

    def test_init_sets_attributes(self):
        """Test that __init__ sets mcp and services_container attributes"""
        mock_mcp = Mock(spec=FastMCP)
        mock_container = Mock(spec=ServicesContainer)

        registry = ToolRegistry(mcp=mock_mcp, services_container=mock_container)

        assert registry.mcp is mock_mcp
        assert registry.services_container is mock_container

    @patch("pipefy_mcp.tools.registry.PipeTools.register")
    def test_register_tools_calls_pipe_tools_register(self, mock_pipe_tools_register):
        """Test that register_tools calls PipeTools.register with correct arguments"""
        mock_mcp = Mock(spec=FastMCP)
        mock_client = Mock()
        mock_container = Mock(spec=ServicesContainer)
        mock_container.pipefy_client = mock_client

        registry = ToolRegistry(mcp=mock_mcp, services_container=mock_container)
        result = registry.register_tools()

        mock_pipe_tools_register.assert_called_once_with(mock_mcp, mock_client)
        assert result is mock_mcp

    def test_register_tools_raises_when_pipefy_client_is_none(self):
        """Test that register_tools raises ValueError when pipefy_client is None"""
        mock_mcp = Mock(spec=FastMCP)
        mock_container = Mock(spec=ServicesContainer)
        mock_container.pipefy_client = None

        registry = ToolRegistry(mcp=mock_mcp, services_container=mock_container)

        with pytest.raises(ValueError) as exc:
            registry.register_tools()

        assert "Pipefy client is not initialized in services container" in str(
            exc.value
        )
