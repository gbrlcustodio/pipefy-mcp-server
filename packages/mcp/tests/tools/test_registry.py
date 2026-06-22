from unittest.mock import MagicMock, Mock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import PipefyClientProxy, ServicesContainer
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
        """Each tool group is registered once with the shared client proxy."""
        mock_mcp = Mock(spec=FastMCP)
        mock_container = Mock(spec=ServicesContainer)
        mock_container.pipefy_client = Mock()

        registry = ToolRegistry(mcp=mock_mcp, services_container=mock_container)
        result = registry.register_tools()

        # Tools bind a single PipefyClientProxy, not the concrete client, so a
        # later service re-init is picked up without re-registering.
        proxy = mock_pipe_tools_register.call_args.args[1]
        assert isinstance(proxy, PipefyClientProxy)

        for mock_register in (
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
            mock_register.assert_called_once_with(mock_mcp, proxy)
        assert result is mock_mcp
        assert registry.pipefy_tool_names == PIPEFY_TOOL_NAMES

    def test_register_tools_succeeds_when_pipefy_client_is_none(self):
        """Registration binds a proxy, so it works before services are initialized.

        The proxy defers client resolution to call time, which is what lets
        tools register once at construction (before the lifespan runs). The
        absence of a live client only surfaces when a tool is actually invoked.
        """
        mock_mcp = Mock(spec=FastMCP)
        mock_container = Mock(spec=ServicesContainer)
        mock_container.pipefy_client = None

        registry = ToolRegistry(mcp=mock_mcp, services_container=mock_container)

        assert registry.register_tools() is mock_mcp

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
        mock_container = Mock(spec=ServicesContainer)
        mock_container.pipefy_client = Mock()

        registry = ToolRegistry(mcp=mock_mcp, services_container=mock_container)
        registry.register_tools()

        proxy = mock_pipe_tools_register.call_args.args[1]
        assert isinstance(proxy, PipefyClientProxy)

        for mock_register in (
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
            mock_ai_automation_tools_register,
            mock_ai_agent_tools_register,
        ):
            mock_register.assert_called_once_with(mock_mcp, proxy)
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
