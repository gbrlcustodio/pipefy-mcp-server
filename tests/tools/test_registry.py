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

    @patch("pipefy_mcp.tools.registry.IntrospectionTools.register")
    @patch("pipefy_mcp.tools.registry.AutomationTools.register")
    @patch("pipefy_mcp.tools.registry.WebhookTools.register")
    @patch("pipefy_mcp.tools.registry.MemberTools.register")
    @patch("pipefy_mcp.tools.registry.RelationTools.register")
    @patch("pipefy_mcp.tools.registry.TableTools.register")
    @patch("pipefy_mcp.tools.registry.FieldConditionTools.register")
    @patch("pipefy_mcp.tools.registry.PipeConfigTools.register")
    @patch("pipefy_mcp.tools.registry.PipeTools.register")
    def test_register_tools_calls_pipe_and_introspection_tools_register(
        self,
        mock_pipe_tools_register,
        mock_pipe_config_tools_register,
        mock_field_condition_tools_register,
        mock_table_tools_register,
        mock_relation_tools_register,
        mock_member_tools_register,
        mock_webhook_tools_register,
        mock_automation_tools_register,
        mock_introspection_tools_register,
    ):
        """Test that register_tools calls Pipe, PipeConfig, FieldCondition, Table, Relation, Member, Webhook, and Introspection tools."""
        mock_mcp = Mock(spec=FastMCP)
        mock_client = Mock()
        mock_container = Mock(spec=ServicesContainer)
        mock_container.pipefy_client = mock_client

        registry = ToolRegistry(mcp=mock_mcp, services_container=mock_container)
        result = registry.register_tools()

        mock_pipe_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_pipe_config_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_field_condition_tools_register.assert_called_once_with(
            mock_mcp, mock_client
        )
        mock_table_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_relation_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_member_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_webhook_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_automation_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_introspection_tools_register.assert_called_once_with(mock_mcp, mock_client)
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

    @patch("pipefy_mcp.tools.registry.IntrospectionTools.register")
    @patch("pipefy_mcp.tools.registry.AiAgentTools.register")
    @patch("pipefy_mcp.tools.registry.AiAutomationTools.register")
    @patch("pipefy_mcp.tools.registry.AutomationTools.register")
    @patch("pipefy_mcp.tools.registry.WebhookTools.register")
    @patch("pipefy_mcp.tools.registry.MemberTools.register")
    @patch("pipefy_mcp.tools.registry.RelationTools.register")
    @patch("pipefy_mcp.tools.registry.TableTools.register")
    @patch("pipefy_mcp.tools.registry.FieldConditionTools.register")
    @patch("pipefy_mcp.tools.registry.PipeConfigTools.register")
    @patch("pipefy_mcp.tools.registry.PipeTools.register")
    def test_register_tools_calls_ai_tools_register(
        self,
        mock_pipe_tools_register,
        mock_pipe_config_tools_register,
        mock_field_condition_tools_register,
        mock_table_tools_register,
        mock_relation_tools_register,
        mock_member_tools_register,
        mock_webhook_tools_register,
        mock_automation_tools_register,
        mock_ai_automation_tools_register,
        mock_ai_agent_tools_register,
        mock_introspection_tools_register,
    ):
        mock_mcp = Mock(spec=FastMCP)
        mock_client = Mock()
        mock_ai_automation_service = Mock()
        mock_ai_agent_service = Mock()
        mock_container = Mock(spec=ServicesContainer)
        mock_container.pipefy_client = mock_client
        mock_container.ai_automation_service = mock_ai_automation_service
        mock_container.ai_agent_service = mock_ai_agent_service

        registry = ToolRegistry(mcp=mock_mcp, services_container=mock_container)
        registry.register_tools()

        mock_pipe_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_pipe_config_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_field_condition_tools_register.assert_called_once_with(
            mock_mcp, mock_client
        )
        mock_table_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_relation_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_member_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_webhook_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_automation_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_introspection_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_ai_automation_tools_register.assert_called_once_with(
            mock_mcp, mock_ai_automation_service
        )
        mock_ai_agent_tools_register.assert_called_once_with(
            mock_mcp, mock_ai_agent_service
        )
