"""Subject-domain taxonomy for the MCP tool surface.

``DOMAINS`` is a disjoint partition of every registered tool: each tool name
belongs to exactly one domain, keyed by the subject the tool is *about*. The
partition backs the tool-catalog map and the build-time drift-guard in
``tests/tools/test_toolsets.py`` (a newly registered tool with no domain fails
the build). The "Subject-domain taxonomy" section in ``packages/mcp/AGENTS.md``
covers the Domain vs Profile distinction, what each domain owns, and why subject
domains are chosen over the doc-area grouping.

Persona *profiles* (overlapping, journey-sized selections) are a separate axis
added on top of this partition; they are not defined here.
"""

from __future__ import annotations

# Disjoint partition of ``PIPEFY_TOOL_NAMES`` by subject. Every registered tool
# appears in exactly one domain; the drift-guard enforces completeness against
# ``PIPEFY_TOOL_NAMES`` (no hardcoded count). Add a new tool's name here when you
# register it, or the build fails.
DOMAINS: dict[str, frozenset[str]] = {
    "workflow": frozenset(
        {
            "add_card_comment",
            "clone_pipe",
            "create_attachment_presigned_url",
            "create_card",
            "create_card_relation",
            "create_field_condition",
            "create_label",
            "create_phase",
            "create_phase_field",
            "create_pipe",
            "create_pipe_relation",
            "delete_card",
            "delete_card_relation",
            "delete_comment",
            "delete_field_condition",
            "delete_label",
            "delete_phase",
            "delete_phase_field",
            "delete_pipe",
            "delete_pipe_relation",
            "fill_card_phase_fields",
            "find_cards",
            "get_card",
            "get_card_inbox_emails",
            "get_card_relations",
            "get_cards",
            "get_email_templates",
            "get_field_condition",
            "get_field_conditions",
            "get_labels",
            "get_phase_allowed_move_targets",
            "get_phase_cards",
            "get_phase_cards_count",
            "get_phase_fields",
            "get_pipe",
            "get_pipe_members",
            "get_pipe_relations",
            "get_start_form_fields",
            "move_card_to_phase",
            "search_pipes",
            "send_email_with_template",
            "send_inbox_email",
            "update_card",
            "update_card_field",
            "update_comment",
            "update_field_condition",
            "update_label",
            "update_phase",
            "update_phase_field",
            "update_pipe",
            "update_pipe_relation",
            "upload_attachment_to_card",
        }
    ),
    "database": frozenset(
        {
            "create_table",
            "create_table_field",
            "create_table_record",
            "delete_table",
            "delete_table_field",
            "delete_table_record",
            "find_records",
            "get_table",
            "get_table_record",
            "get_table_records",
            "get_table_relations",
            "get_tables",
            "search_tables",
            "set_table_record_field_value",
            "update_table",
            "update_table_field",
            "update_table_record",
            "upload_attachment_to_table_record",
        }
    ),
    "interfaces": frozenset(
        {
            "create_portal",
            "create_portal_element",
            "create_portal_page",
            "create_sub_portal",
            "delete_portal",
            "delete_portal_element",
            "delete_portal_page",
            "delete_sub_portal",
            "delete_sub_portal_element",
            "duplicate_portal_element",
            "get_portal",
            "list_portals",
            "publish_sub_portal",
            "sort_portal_pages",
            "unpublish_sub_portal",
            "update_portal",
            "update_portal_element",
            "update_portal_page",
            "update_portal_page_layout",
            "update_sub_portal_element",
        }
    ),
    "automation": frozenset(
        {
            "create_ai_automation",
            "create_automation",
            "create_send_task_automation",
            "delete_ai_automation",
            "delete_automation",
            "export_automation_jobs",
            "get_ai_automation",
            "get_ai_automations",
            "get_automation",
            "get_automation_actions",
            "get_automation_event_attributes",
            "get_automation_events",
            "get_automation_execution_metrics",
            "get_automation_jobs_export",
            "get_automation_jobs_export_csv",
            "get_automation_logs",
            "get_automation_logs_by_repo",
            "get_automations",
            "get_automations_usage",
            "simulate_automation",
            "update_ai_automation",
            "update_automation",
            "validate_ai_automation_prompt",
        }
    ),
    "intelligence": frozenset(
        {
            "create_ai_agent",
            "create_ai_knowledge_base_data_lookup",
            "create_ai_knowledge_base_document",
            "create_ai_knowledge_base_plain_text",
            "create_llm_provider",
            "delete_ai_agent",
            "delete_ai_knowledge_base_data_lookup",
            "delete_ai_knowledge_base_document",
            "delete_ai_knowledge_base_plain_text",
            "delete_llm_provider",
            "get_agents_usage",
            "get_ai_agent",
            "get_ai_agent_log_details",
            "get_ai_agent_logs",
            "get_ai_agents",
            "get_ai_credit_usage",
            "get_ai_knowledge_base_data_lookup",
            "get_ai_knowledge_base_document",
            "get_ai_knowledge_base_plain_text",
            "get_ai_knowledge_bases",
            "get_available_ai_models",
            "get_default_llm_provider",
            "get_llm_provider_dependencies",
            "get_llm_providers",
            "reset_default_llm_provider",
            "set_default_llm_provider",
            "set_llm_provider_active_status",
            "toggle_ai_agent_status",
            "update_ai_agent",
            "update_ai_knowledge_base_data_lookup",
            "update_ai_knowledge_base_document",
            "update_ai_knowledge_base_plain_text",
            "update_llm_provider",
            "validate_ai_agent_behaviors",
            "validate_knowledge_base_access",
            "validate_llm_provider_access",
        }
    ),
    "analytics": frozenset(
        {
            "create_organization_report",
            "create_pipe_report",
            "delete_organization_report",
            "delete_pipe_report",
            "export_organization_report",
            "export_pipe_report",
            "get_organization_report",
            "get_organization_report_export",
            "get_organization_reports",
            "get_pipe_report",
            "get_pipe_report_columns",
            "get_pipe_report_export",
            "get_pipe_report_filterable_fields",
            "get_pipe_reports",
            "update_organization_report",
            "update_pipe_report",
        }
    ),
    "governance": frozenset(
        {
            "add_service_account_to_pipe",
            "create_service_account",
            "delete_service_account",
            "export_pipe_audit_logs",
            "get_organization",
            "invite_members",
            "list_organizations",
            "remove_member_from_pipe",
            "set_role",
        }
    ),
    "integration": frozenset(
        {
            "call_ipaas_tool",
            "create_ipaas_connection",
            "create_webhook",
            "delete_webhook",
            "execute_graphql",
            "get_ipaas_connection_auth_url",
            "get_ipaas_tools",
            "get_webhooks",
            "introspect_mutation",
            "introspect_query",
            "introspect_type",
            "search_schema",
            "update_webhook",
        }
    ),
}

# Reserved keywords that mean "no curation" — the full (post-floor) surface.
_NO_CURATION = frozenset({"all", "default"})


def resolve_selection(spec: str | None) -> frozenset[str] | None:
    """Resolve a ``--toolsets`` / ``PIPEFY_MCP_TOOLSETS`` spec to a set of tool names.

    ``spec`` is a comma-separated list of subject-domain names (case-insensitive).
    Returns the union of the named domains' tools, or ``None`` for no curation —
    an empty spec or the ``all`` / ``default`` keywords. ``None`` means the caller
    applies no selection at all (backward-compatible default).

    Selection only ever narrows: the returned names are matched against the
    already-registered (and, on the remote profile, already-floored) surface, so a
    name here can never widen the surface past the floor.

    Raises:
        ValueError: if any name is neither a known domain nor a reserved keyword.
            The message names the unknown values and lists the known toolsets, so
            the CLI can render it as a usage error.
    """
    if spec is None:
        return None
    names = [part.strip().lower() for part in spec.split(",") if part.strip()]
    if not names:
        return None
    unknown = [n for n in names if n not in DOMAINS and n not in _NO_CURATION]
    if unknown:
        known = ", ".join(sorted(set(DOMAINS) | _NO_CURATION))
        raise ValueError(
            f"unknown toolset(s): {', '.join(unknown)}. Known toolsets: {known}."
        )
    if any(n in _NO_CURATION for n in names):
        return None
    return frozenset().union(*(DOMAINS[n] for n in names))
