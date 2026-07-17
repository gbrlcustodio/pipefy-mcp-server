from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.fastmcp_tool_lifecycle import remove_fastmcp_tools_by_name
from pipefy_mcp.tools.ai_agent_tools import AiAgentTools
from pipefy_mcp.tools.ai_automation_tools import AiAutomationTools
from pipefy_mcp.tools.attachment_tools import AttachmentTools
from pipefy_mcp.tools.automation_tools import AutomationTools
from pipefy_mcp.tools.field_condition_tools import FieldConditionTools
from pipefy_mcp.tools.introspection_tools import IntrospectionTools
from pipefy_mcp.tools.ipaas_tools import IpaasTools
from pipefy_mcp.tools.llm_provider_tools import LlmProviderTools
from pipefy_mcp.tools.member_tools import MemberTools
from pipefy_mcp.tools.observability_tools import ObservabilityTools
from pipefy_mcp.tools.organization_tools import OrganizationTools
from pipefy_mcp.tools.pipe_config_tools import PipeConfigTools
from pipefy_mcp.tools.pipe_tools import PipeTools
from pipefy_mcp.tools.portal_tools import PortalTools
from pipefy_mcp.tools.relation_tools import RelationTools
from pipefy_mcp.tools.remote_profile import is_remote_tool
from pipefy_mcp.tools.report_tools import ReportTools
from pipefy_mcp.tools.table_tools import TableTools
from pipefy_mcp.tools.webhook_tools import WebhookTools

if TYPE_CHECKING:
    from mcp.server.fastmcp.tools.base import Tool

logger = logging.getLogger(__name__)

# Keep PIPEFY_TOOL_NAMES in sync with docs/parity.md and README MCP totals.
PIPEFY_TOOL_NAMES = frozenset(
    {
        "add_card_comment",
        "call_ipaas_tool",
        "clone_pipe",
        "create_ai_agent",
        "create_ai_automation",
        "create_automation",
        "create_card",
        "create_card_relation",
        "create_field_condition",
        "create_ipaas_connection",
        "create_label",
        "create_organization_report",
        "create_phase",
        "create_phase_field",
        "create_pipe",
        "create_pipe_relation",
        "create_pipe_report",
        "create_portal",
        "create_portal_element",
        "create_portal_page",
        "create_sub_portal",
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
        "delete_portal",
        "delete_portal_element",
        "delete_portal_page",
        "delete_sub_portal",
        "delete_sub_portal_element",
        "delete_table",
        "delete_table_field",
        "delete_table_record",
        "delete_webhook",
        "duplicate_portal_element",
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
        "get_automation_event_attributes",
        "get_automation_execution_metrics",
        "get_automation_events",
        "get_automation_jobs_export",
        "get_automation_jobs_export_csv",
        "get_automation_logs",
        "get_automation_logs_by_repo",
        "get_automations",
        "get_automations_usage",
        "get_available_ai_models",
        "get_default_llm_provider",
        "get_field_condition",
        "get_field_conditions",
        "get_card",
        "get_card_inbox_emails",
        "get_card_relations",
        "get_cards",
        "get_email_templates",
        "get_ipaas_connection_auth_url",
        "get_ipaas_tools",
        "get_labels",
        "get_llm_provider_dependencies",
        "get_llm_providers",
        "get_organization",
        "get_organization_report",
        "get_organization_report_export",
        "get_organization_reports",
        "get_phase_allowed_move_targets",
        "get_phase_cards",
        "get_phase_cards_count",
        "get_phase_fields",
        "get_portal",
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
        "list_portals",
        "move_card_to_phase",
        "publish_sub_portal",
        "remove_member_from_pipe",
        "search_pipes",
        "search_schema",
        "search_tables",
        "send_email_with_template",
        "send_inbox_email",
        "simulate_automation",
        "sort_portal_pages",
        "set_role",
        "set_table_record_field_value",
        "toggle_ai_agent_status",
        "unpublish_sub_portal",
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
        "update_portal",
        "update_portal_element",
        "update_portal_page",
        "update_portal_page_layout",
        "update_sub_portal_element",
        "update_table",
        "update_table_field",
        "update_table_record",
        "update_webhook",
        "upload_attachment_to_card",
        "upload_attachment_to_table_record",
        "validate_ai_agent_behaviors",
        "validate_ai_automation_prompt",
        "validate_llm_provider_access",
    }
)


# Toolsets registered on the server, in registration order. Each exposes a
# ``register(mcp, client)`` static method. Add a toolset by appending it here.
_TOOLSETS = (
    PipeTools,
    PipeConfigTools,
    FieldConditionTools,
    TableTools,
    RelationTools,
    ReportTools,
    AttachmentTools,
    MemberTools,
    WebhookTools,
    AutomationTools,
    IntrospectionTools,
    IpaasTools,
    OrganizationTools,
    PortalTools,
    ObservabilityTools,
    AiAutomationTools,
    AiAgentTools,
    LlmProviderTools,
)


class ToolRegistry:
    """Responsible for registering tools with the MCP server."""

    def __init__(self, mcp: FastMCP):
        self.mcp = mcp
        self.pipefy_tool_names: frozenset[str] = PIPEFY_TOOL_NAMES

    @staticmethod
    def _snapshot_tool_names(mcp: FastMCP) -> set[str]:
        return {tool.name for tool in mcp._tool_manager.list_tools()}

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

    def register_tools(self) -> None:
        """Register tools with the MCP server.

        Tool functions resolve the live Pipefy client per request from the MCP
        lifespan context (see
        :func:`pipefy_mcp.tools.tool_context.get_pipefy_client`), so registration
        needs no client and runs once, at construction, rather than inside the
        lifespan.
        """
        for toolset in _TOOLSETS:
            toolset.register(self.mcp)

    def retain_only(self, predicate: Callable[[Tool], bool]) -> set[str]:
        """Remove every Pipefy tool that does not satisfy ``predicate``.

        Runs after :meth:`register_tools`: the marker rides on the ``@mcp.tool``
        decorator, so a tool must be registered before its marker can be read.
        Only names in ``pipefy_tool_names`` are eligible for removal, so
        third-party or test-registered tools are never touched.

        Returns the set of withheld (removed) tool names.
        """
        withheld = {
            tool.name
            for tool in self.mcp._tool_manager.list_tools()
            if tool.name in self.pipefy_tool_names and not predicate(tool)
        }
        remove_fastmcp_tools_by_name(self.mcp, withheld)
        return withheld

    def apply_remote_profile(self, *, remote_mode: bool) -> set[str]:
        """When ``remote_mode`` is on, withhold every tool not marked remote-safe.

        Default-deny: only tools carrying ``meta=REMOTE`` survive. When off, a
        no-op that returns an empty set (local stdio profile keeps all tools).
        """
        if not remote_mode:
            return set()
        withheld = self.retain_only(is_remote_tool)
        logger.info(
            "Remote profile: exposed %d, withheld %d Pipefy tools.",
            len(self.pipefy_tool_names) - len(withheld),
            len(withheld),
        )
        return withheld
