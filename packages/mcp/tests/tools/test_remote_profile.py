"""Tests for the default-deny remote-profile tool allowlist (#304)."""

from types import SimpleNamespace

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.tools.registry import PIPEFY_TOOL_NAMES, ToolRegistry
from pipefy_mcp.tools.remote_profile import REMOTE, REMOTE_META_KEY, is_remote_tool

# Expected remote-safe seed. Every addition here is a deliberate, reviewed change:
# a tool earns a place only by carrying meta=REMOTE on its registration AND being
# listed here, and the drift guard below asserts the two stay in lockstep.
REMOTE_SEED = frozenset(
    {
        # iPaaS meta tools: per-request identity end-to-end (the pipe token is
        # minted with the caller's own bearer), stateless shared gateway, and
        # the one process-global input ($env credential references) is
        # rejected at call time under the remote profile.
        "get_ipaas_tools",
        "call_ipaas_tool",
        "get_ipaas_connection_auth_url",
        "create_ipaas_connection",
        "search_pipes",
        "get_organization",
        "get_pipe",
        "get_card",
        "get_cards",
        "find_cards",
        "find_records",
        "get_table",
        "get_tables",
        "get_table_record",
        "get_table_records",
        "get_phase_cards",
        "get_phase_fields",
        "get_start_form_fields",
        "search_tables",
        "search_schema",
        "introspect_query",
        "introspect_mutation",
        "introspect_type",
        # AI agent & automation reads (#437): read/validate tools that reach the
        # API with the request-scoped bearer and are governed by API permissions;
        # no filesystem or per-user process-global settings reads.
        "get_ai_agent",
        "get_ai_agents",
        "get_ai_agent_logs",
        "get_ai_agent_log_details",
        "get_agents_usage",
        "validate_ai_agent_behaviors",
        "get_ai_automation",
        "get_ai_automations",
        "validate_ai_automation_prompt",
        "get_ai_credit_usage",
        "get_available_ai_models",
        # knowledge base & LLM provider reads (#438): read/validate tools that
        # reach the API with the request-scoped bearer and are governed by API
        # permissions; no filesystem or per-user process-global settings reads.
        "get_ai_knowledge_bases",
        "get_ai_knowledge_base_plain_text",
        "get_ai_knowledge_base_document",
        "get_ai_knowledge_base_data_lookup",
        "validate_knowledge_base_access",
        "get_llm_providers",
        "get_llm_provider_dependencies",
        "get_default_llm_provider",
        "validate_llm_provider_access",
        # traditional automation reads (#439): read/log tools that reach the API
        # with the request-scoped bearer and are governed by API permissions; no
        # filesystem or per-user process-global settings reads. The export CSV
        # tool downloads in-memory (no local file) with per-call size caps.
        "get_automation",
        "get_automations",
        "get_automation_actions",
        "get_automation_events",
        "get_automation_event_attributes",
        "get_automation_execution_metrics",
        "get_automation_logs",
        "get_automation_logs_by_repo",
        "get_automations_usage",
        "get_automation_jobs_export",
        "get_automation_jobs_export_csv",
        # report reads (#440): read/status tools that reach the API with the
        # request-scoped bearer and are governed by API permissions; no filesystem
        # or per-user process-global settings reads. The export tools poll export
        # status (a GraphQL query returning a fileURL string), not a local write.
        "get_organization_report",
        "get_organization_reports",
        "get_organization_report_export",
        "get_pipe_report",
        "get_pipe_reports",
        "get_pipe_report_columns",
        "get_pipe_report_filterable_fields",
        "get_pipe_report_export",
        # pipe / card / field / member / webhook / portal reads (#441): read tools
        # that reach the API with the request-scoped bearer and are governed by API
        # permissions; no filesystem or per-user process-global settings reads. The
        # relation reads use the public GraphQL API only and the portal reads use
        # the Interfaces schema; Pipefy's Internal API is reached only by mutations
        # such as delete_card_relation, which stay withheld.
        "get_card_relations",
        "get_card_inbox_emails",
        "get_field_condition",
        "get_field_conditions",
        "get_labels",
        "get_pipe_members",
        "get_pipe_relations",
        "get_phase_allowed_move_targets",
        "get_phase_cards_count",
        "get_table_relations",
        "get_webhooks",
        "get_email_templates",
        "get_portal",
        "list_portals",
        # service-account tools: the first public-GraphQL write mutations on the
        # seed (the iPaaS meta-tools are also writes, but reach the iPaaS host, not
        # the public API). Each reaches the API with the request-scoped bearer and
        # is fully governed by API permissions (org-admin to create/delete,
        # pipe-admin to add-to-pipe);
        # no filesystem or per-user process-global settings reads (org/pipe are
        # per-request arguments). create_service_account returns the new account's
        # own client secret to the authenticated caller — the hosted logging layer
        # excludes response bodies, so it is not logged. delete_service_account is
        # guarded by two-step confirmation.
        "create_service_account",
        "delete_service_account",
        "add_service_account_to_pipe",
        # card / comment / card-relation writes (#472): create/update/delete and
        # action-style mutations that reach the public (or, for delete_card_relation,
        # Internal) API with the request-scoped bearer and are governed by API
        # permissions; no filesystem or per-user process-global settings reads, and
        # every input is a per-request value (ids, titles, field values). The deletes
        # carry the two-step confirm UX guard; authorization stays the API's.
        "add_card_comment",
        "create_card",
        "update_card",
        "update_card_field",
        "delete_card",
        "move_card_to_phase",
        "fill_card_phase_fields",
        "update_comment",
        "delete_comment",
        "create_card_relation",
        "delete_card_relation",
    }
)


def _registry_with_all_tools() -> tuple[ToolRegistry, FastMCP]:
    """Register every Pipefy tool on a real FastMCP, as the lifespan does."""
    mcp = FastMCP("remote-profile-test")
    registry = ToolRegistry(mcp=mcp)
    registry.register_tools()
    return registry, mcp


def _registered_names(mcp: FastMCP) -> set[str]:
    return {tool.name for tool in mcp._tool_manager.list_tools()}


class TestIsRemoteTool:
    def test_marked_tool_is_remote(self):
        assert is_remote_tool(SimpleNamespace(meta=REMOTE)) is True
        assert is_remote_tool(SimpleNamespace(meta={REMOTE_META_KEY: True})) is True

    def test_unmarked_tool_is_not_remote(self):
        assert is_remote_tool(SimpleNamespace(meta=None)) is False
        assert is_remote_tool(SimpleNamespace(meta={})) is False
        assert is_remote_tool(SimpleNamespace(meta={"other": True})) is False
        assert is_remote_tool(SimpleNamespace(meta={REMOTE_META_KEY: False})) is False


class TestApplyRemoteProfile:
    def test_off_is_noop_keeps_all_tools(self):
        registry, mcp = _registry_with_all_tools()

        withheld = registry.apply_remote_profile(remote_mode=False)

        assert withheld == set()
        assert _registered_names(mcp) & PIPEFY_TOOL_NAMES == set(PIPEFY_TOOL_NAMES)

    def test_on_exposes_seed_and_withholds_the_rest(self):
        registry, mcp = _registry_with_all_tools()

        withheld = registry.apply_remote_profile(remote_mode=True)

        exposed = _registered_names(mcp) & set(PIPEFY_TOOL_NAMES)
        assert exposed == set(REMOTE_SEED)
        assert withheld == set(PIPEFY_TOOL_NAMES) - set(REMOTE_SEED)
        # Filesystem-bound tools must never be exposed remotely.
        assert "upload_attachment_to_card" not in exposed
        assert "upload_attachment_to_table_record" not in exposed


class TestSeedDriftGuard:
    def test_seed_is_subset_of_all_tool_names(self):
        assert REMOTE_SEED <= PIPEFY_TOOL_NAMES

    def test_marked_tools_equal_the_seed(self):
        """The tools carrying meta=REMOTE must be exactly REMOTE_SEED.

        Adding meta=REMOTE to a tool without updating REMOTE_SEED (or vice
        versa) fails here, forcing every allowlist change through review.
        """
        _, mcp = _registry_with_all_tools()

        marked = {
            tool.name for tool in mcp._tool_manager.list_tools() if is_remote_tool(tool)
        }

        assert marked == set(REMOTE_SEED)


class TestRetainOnlyReuse:
    def test_arbitrary_predicate_keeps_only_matches_and_spares_foreign(self):
        """retain_only is the reusable seam #308 (dynamic toolsets) builds on.

        It is independent of the remote marker: any predicate works, and tools
        outside PIPEFY_TOOL_NAMES (third-party, test) are never removed.
        """
        registry, mcp = _registry_with_all_tools()

        @mcp.tool()
        def foreign_probe() -> str:
            return "x"

        keep = {"get_card", "get_pipe"}
        withheld = registry.retain_only(lambda tool: tool.name in keep)

        registered = _registered_names(mcp)
        assert registered & set(PIPEFY_TOOL_NAMES) == keep
        assert withheld == set(PIPEFY_TOOL_NAMES) - keep
        # Foreign tool is outside pipefy_tool_names, so it is never touched.
        assert "foreign_probe" in registered
        assert "foreign_probe" not in withheld
