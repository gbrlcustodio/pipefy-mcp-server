from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.tools.ai_agent_tools import AiAgentTools
from pipefy_mcp.tools.ai_automation_tools import AiAutomationTools
from pipefy_mcp.tools.attachment_tools import AttachmentTools
from pipefy_mcp.tools.automation_tools import AutomationTools
from pipefy_mcp.tools.field_condition_tools import FieldConditionTools
from pipefy_mcp.tools.introspection_tools import IntrospectionTools
from pipefy_mcp.tools.member_tools import MemberTools
from pipefy_mcp.tools.observability_tools import ObservabilityTools
from pipefy_mcp.tools.organization_tools import OrganizationTools
from pipefy_mcp.tools.pipe_config_tools import PipeConfigTools
from pipefy_mcp.tools.pipe_tools import PipeTools
from pipefy_mcp.tools.relation_tools import RelationTools
from pipefy_mcp.tools.report_tools import ReportTools
from pipefy_mcp.tools.table_tools import TableTools
from pipefy_mcp.tools.webhook_tools import WebhookTools

PIPEFY_TOOL_NAMES = frozenset(
    {
        "add_card_comment",
        "clone_pipe",
        "create_ai_agent",
        "create_ai_automation",
        "create_automation",
        "create_card",
        "create_card_relation",
        "create_field_condition",
        "create_label",
        "create_organization_report",
        "create_phase",
        "create_phase_field",
        "create_pipe",
        "create_pipe_relation",
        "create_pipe_report",
        "create_send_task_automation",
        "create_table",
        "create_table_field",
        "create_table_record",
        "create_webhook",
        "delete_ai_agent",
        "delete_ai_automation",
        "delete_automation",
        "delete_card",
        "delete_card_relation",
        "delete_comment",
        "delete_field_condition",
        "delete_label",
        "delete_organization_report",
        "delete_phase",
        "delete_phase_field",
        "delete_pipe",
        "delete_pipe_relation",
        "delete_pipe_report",
        "delete_table",
        "delete_table_field",
        "delete_table_record",
        "delete_webhook",
        "execute_graphql",
        "export_automation_jobs",
        "export_organization_report",
        "export_pipe_audit_logs",
        "export_pipe_report",
        "fill_card_phase_fields",
        "find_cards",
        "find_records",
        "get_agents_usage",
        "get_ai_agent",
        "get_ai_agent_log_details",
        "get_ai_agent_logs",
        "get_ai_agents",
        "get_ai_automation",
        "get_ai_automations",
        "get_ai_credit_usage",
        "get_automation",
        "get_automation_actions",
        "get_automation_events",
        "get_automation_jobs_export",
        "get_automation_jobs_export_csv",
        "get_automation_logs",
        "get_automation_logs_by_repo",
        "get_automations",
        "get_automations_usage",
        "get_field_condition",
        "get_field_conditions",
        "get_card",
        "get_card_inbox_emails",
        "get_card_relations",
        "get_cards",
        "get_email_templates",
        "get_labels",
        "get_organization",
        "get_organization_report",
        "get_organization_report_export",
        "get_organization_reports",
        "get_phase_fields",
        "get_pipe",
        "get_pipe_members",
        "get_pipe_relations",
        "get_pipe_report",
        "get_pipe_report_columns",
        "get_pipe_report_export",
        "get_pipe_report_filterable_fields",
        "get_pipe_reports",
        "get_start_form_fields",
        "get_table",
        "get_table_record",
        "get_table_records",
        "get_tables",
        "get_table_relations",
        "get_webhooks",
        "introspect_mutation",
        "introspect_query",
        "introspect_type",
        "invite_members",
        "move_card_to_phase",
        "remove_member_from_pipe",
        "search_pipes",
        "search_schema",
        "search_tables",
        "send_email_with_template",
        "send_inbox_email",
        "simulate_automation",
        "set_role",
        "set_table_record_field_value",
        "toggle_ai_agent_status",
        "update_ai_agent",
        "update_ai_automation",
        "update_automation",
        "update_card",
        "update_card_field",
        "update_comment",
        "update_field_condition",
        "update_label",
        "update_organization_report",
        "update_phase",
        "update_phase_field",
        "update_pipe",
        "update_pipe_relation",
        "update_pipe_report",
        "update_table",
        "update_table_field",
        "update_table_record",
        "update_webhook",
        "upload_attachment_to_card",
        "upload_attachment_to_table_record",
        "validate_ai_agent_behaviors",
        "validate_ai_automation_prompt",
    }
)


class ToolRegistry:
    """Responsible for registering tools with the MCP server."""

    def __init__(self, mcp: FastMCP, services_container: ServicesContainer):
        self.mcp = mcp
        self.services_container = services_container
        self.pipefy_tool_names: frozenset[str] = PIPEFY_TOOL_NAMES

    @staticmethod
    def _snapshot_tool_names(mcp: FastMCP) -> set[str]:
        try:
            tools = mcp._tool_manager.list_tools()
        except AttributeError:
            return set()
        try:
            tool_list = list(tools)
        except TypeError:
            return set()
        names: set[str] = set()
        for tool in tool_list:
            try:
                names.add(tool.name)
            except AttributeError:
                continue
        return names

    def check_for_name_collisions(self) -> None:
        """Fail fast if any Pipefy tool name is already registered on the app.

        FastMCP keeps the first handler when names collide; preflight avoids
        silently running a foreign ``create_card`` (or other) handler.
        """
        existing = self._snapshot_tool_names(self.mcp)
        collisions = existing & set(self.pipefy_tool_names)
        if collisions:
            names = ", ".join(sorted(collisions))
            raise RuntimeError(
                "Cannot register Pipefy tools because these names already exist: "
                f"{names}"
            )

    def register_tools(self) -> FastMCP:
        """Register tools with the MCP server."""
        if self.services_container.pipefy_client is None:
            raise ValueError("Pipefy client is not initialized in services container")

        PipeTools.register(self.mcp, self.services_container.pipefy_client)
        PipeConfigTools.register(self.mcp, self.services_container.pipefy_client)
        FieldConditionTools.register(self.mcp, self.services_container.pipefy_client)
        TableTools.register(self.mcp, self.services_container.pipefy_client)
        RelationTools.register(self.mcp, self.services_container.pipefy_client)
        ReportTools.register(self.mcp, self.services_container.pipefy_client)
        AttachmentTools.register(self.mcp, self.services_container.pipefy_client)
        MemberTools.register(self.mcp, self.services_container.pipefy_client)
        WebhookTools.register(self.mcp, self.services_container.pipefy_client)
        AutomationTools.register(self.mcp, self.services_container.pipefy_client)
        IntrospectionTools.register(self.mcp, self.services_container.pipefy_client)
        OrganizationTools.register(self.mcp, self.services_container.pipefy_client)
        ObservabilityTools.register(self.mcp, self.services_container.pipefy_client)

        AiAutomationTools.register(self.mcp, self.services_container.pipefy_client)
        AiAgentTools.register(self.mcp, self.services_container.pipefy_client)

        return self.mcp
