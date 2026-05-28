from unittest.mock import MagicMock, Mock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.tools.registry import PIPEFY_TOOL_NAMES, ToolRegistry


class TestToolRegistry:
    """Test cases for ToolRegistry"""

    def test_init_sets_attributes(self):
        """Test that __init__ sets mcp and services_container attributes"""
        mock_mcp = Mock(spec=FastMCP)
        mock_container = Mock(spec=ServicesContainer)

        registry = ToolRegistry(mcp=mock_mcp, services_container=mock_container)

        assert registry.mcp is mock_mcp
        assert registry.services_container is mock_container
        assert registry.pipefy_tool_names == PIPEFY_TOOL_NAMES

    @patch("pipefy_mcp.tools.registry.ObservabilityTools.register")
    @patch("pipefy_mcp.tools.registry.IntrospectionTools.register")
    @patch("pipefy_mcp.tools.registry.AutomationTools.register")
    @patch("pipefy_mcp.tools.registry.WebhookTools.register")
    @patch("pipefy_mcp.tools.registry.MemberTools.register")
    @patch("pipefy_mcp.tools.registry.AttachmentTools.register")
    @patch("pipefy_mcp.tools.registry.ReportTools.register")
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
        mock_report_tools_register,
        mock_attachment_tools_register,
        mock_member_tools_register,
        mock_webhook_tools_register,
        mock_automation_tools_register,
        mock_introspection_tools_register,
        mock_observability_tools_register,
    ):
        """Test that register_tools calls Pipe, PipeConfig, FieldCondition, Table, Relation, Report, Member, Webhook, Introspection, and Observability tools."""
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
        mock_report_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_attachment_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_member_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_webhook_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_automation_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_introspection_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_observability_tools_register.assert_called_once_with(mock_mcp, mock_client)
        assert result is mock_mcp
        assert registry.pipefy_tool_names == PIPEFY_TOOL_NAMES

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

    @patch("pipefy_mcp.tools.registry.ObservabilityTools.register")
    @patch("pipefy_mcp.tools.registry.IntrospectionTools.register")
    @patch("pipefy_mcp.tools.registry.AiAgentTools.register")
    @patch("pipefy_mcp.tools.registry.AiAutomationTools.register")
    @patch("pipefy_mcp.tools.registry.AutomationTools.register")
    @patch("pipefy_mcp.tools.registry.WebhookTools.register")
    @patch("pipefy_mcp.tools.registry.MemberTools.register")
    @patch("pipefy_mcp.tools.registry.AttachmentTools.register")
    @patch("pipefy_mcp.tools.registry.ReportTools.register")
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
        mock_report_tools_register,
        mock_attachment_tools_register,
        mock_member_tools_register,
        mock_webhook_tools_register,
        mock_automation_tools_register,
        mock_ai_automation_tools_register,
        mock_ai_agent_tools_register,
        mock_introspection_tools_register,
        mock_observability_tools_register,
    ):
        mock_mcp = Mock(spec=FastMCP)
        mock_client = Mock()
        mock_container = Mock(spec=ServicesContainer)
        mock_container.pipefy_client = mock_client

        registry = ToolRegistry(mcp=mock_mcp, services_container=mock_container)
        registry.register_tools()

        mock_pipe_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_pipe_config_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_field_condition_tools_register.assert_called_once_with(
            mock_mcp, mock_client
        )
        mock_table_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_relation_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_report_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_attachment_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_member_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_webhook_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_automation_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_introspection_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_observability_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_ai_automation_tools_register.assert_called_once_with(mock_mcp, mock_client)
        mock_ai_agent_tools_register.assert_called_once_with(mock_mcp, mock_client)
        assert registry.pipefy_tool_names == PIPEFY_TOOL_NAMES

    def test_register_tools_records_pipefy_tool_names_on_real_fastmcp(self):
        mcp = FastMCP("tool-registry-names")
        mock_container = Mock(spec=ServicesContainer)
        mock_container.pipefy_client = MagicMock()
        registry = ToolRegistry(mcp=mcp, services_container=mock_container)
        registry.register_tools()

        assert registry.pipefy_tool_names == PIPEFY_TOOL_NAMES
        assert "create_card" in registry.pipefy_tool_names
        assert len(registry.pipefy_tool_names) > 50

    def test_check_for_name_collisions_raises_when_pipefy_name_already_registered(self):
        mock_mcp = Mock(spec=FastMCP)
        mock_container = Mock(spec=ServicesContainer)
        registry = ToolRegistry(mcp=mock_mcp, services_container=mock_container)
        with patch.object(
            ToolRegistry,
            "_snapshot_tool_names",
            return_value={"create_card", "foreign_tool"},
        ):
            with pytest.raises(
                RuntimeError, match="these names already exist: create_card"
            ):
                registry.check_for_name_collisions()

    def test_check_for_name_collisions_ok_when_no_overlap(self):
        mock_mcp = Mock(spec=FastMCP)
        mock_container = Mock(spec=ServicesContainer)
        registry = ToolRegistry(mcp=mock_mcp, services_container=mock_container)
        with patch.object(
            ToolRegistry,
            "_snapshot_tool_names",
            return_value={"foreign_tool"},
        ):
            registry.check_for_name_collisions()
