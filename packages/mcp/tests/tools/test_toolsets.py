"""Drift-guard for the subject-domain partition in ``tools/toolsets.py``.

The partition must stay a complete, disjoint cover of every registered tool.
Completeness is keyed to ``PIPEFY_TOOL_NAMES`` (no hardcoded count): registering
a new tool without assigning it a domain fails ``test_partition_is_complete``,
which is the point — the guard is the repo's tool-surface completeness gate.
"""

from itertools import combinations

import pytest
from mcp.server.mcpserver import MCPServer

from pipefy_mcp.tools.registry import PIPEFY_TOOL_NAMES, ToolRegistry
from pipefy_mcp.tools.toolsets import (
    DOMAIN_DESCRIPTIONS,
    DOMAINS,
    POWER_GRAPHQL_TOOLS,
    PROFILES,
    domain_of,
    resolve_selection,
    wants_power,
)

EXPECTED_DOMAINS = frozenset(
    {
        "workflow",
        "database",
        "interfaces",
        "automation",
        "intelligence",
        "analytics",
        "governance",
        "integration",
    }
)


class TestDomainPartition:
    """``DOMAINS`` is a complete, disjoint partition of ``PIPEFY_TOOL_NAMES``."""

    def test_domain_keys_are_the_locked_set(self):
        """Adding or removing a domain must be a deliberate edit to this test."""
        assert set(DOMAINS) == EXPECTED_DOMAINS

    def test_every_domain_is_non_empty(self):
        empty = sorted(name for name, tools in DOMAINS.items() if not tools)
        assert not empty, f"empty domains: {empty}"

    def test_no_phantom_tool_names(self):
        """No domain lists a name that is not a registered tool."""
        phantom = {
            name: sorted(tools - PIPEFY_TOOL_NAMES)
            for name, tools in DOMAINS.items()
            if tools - PIPEFY_TOOL_NAMES
        }
        assert not phantom, f"domains reference unregistered tools: {phantom}"

    def test_domains_are_disjoint(self):
        """No tool belongs to two domains."""
        overlaps = {
            f"{a}&{b}": sorted(DOMAINS[a] & DOMAINS[b])
            for a, b in combinations(sorted(DOMAINS), 2)
            if DOMAINS[a] & DOMAINS[b]
        }
        assert not overlaps, f"tools shared across domains: {overlaps}"

    def test_partition_is_complete(self):
        """Every registered tool has exactly one domain (keyed to the registry,
        no magic count). An orphan here means a new tool needs a domain."""
        covered: set[str] = set().union(*DOMAINS.values())
        orphans = sorted(PIPEFY_TOOL_NAMES - covered)
        assert not orphans, f"registered tools with no domain: {orphans}"

    def test_every_domain_has_a_description(self):
        """``get_tool_categories`` reads ``DOMAIN_DESCRIPTIONS``; keys must match."""
        assert set(DOMAIN_DESCRIPTIONS) == set(DOMAINS)
        assert all(text.strip() for text in DOMAIN_DESCRIPTIONS.values())

    def test_domain_of_maps_names_to_their_domain(self):
        assert domain_of("get_pipe") == "workflow"
        assert domain_of("get_table") == "database"
        assert domain_of("not_a_tool") is None


class TestResolveSelection:
    """``resolve_selection`` maps a comma-spec to a set of tool names or None."""

    @pytest.mark.parametrize("spec", [None, "", "   ", " , ,"])
    def test_empty_specs_are_no_curation(self, spec):
        assert resolve_selection(spec) is None

    @pytest.mark.parametrize(
        "spec", ["all", "default", "all,workflow", "workflow,default"]
    )
    def test_no_curation_keywords_win(self, spec):
        """``all`` / ``default`` mean no curation even mixed with a domain."""
        assert resolve_selection(spec) is None

    def test_single_domain_resolves_to_its_tools(self):
        assert resolve_selection("workflow") == DOMAINS["workflow"]

    def test_multiple_domains_are_unioned(self):
        assert resolve_selection("workflow,database") == (
            DOMAINS["workflow"] | DOMAINS["database"]
        )

    def test_names_are_trimmed_and_case_insensitive(self):
        assert resolve_selection(" Workflow , DATABASE ") == (
            DOMAINS["workflow"] | DOMAINS["database"]
        )

    def test_unknown_name_raises_naming_the_unknown_and_the_known(self):
        with pytest.raises(ValueError) as exc:
            resolve_selection("workflow,bogus")
        message = str(exc.value)
        assert "bogus" in message
        assert "workflow" in message  # lists the known toolsets

    @pytest.mark.parametrize("spec", ["power", "architect"])
    def test_power_keywords_are_known_and_yield_no_domain_selection(self, spec):
        """``power`` / ``architect`` validate (no raise); the registry applies them."""
        assert resolve_selection(spec) is None

    def test_resolves_a_persona_profile_to_its_tools(self):
        assert resolve_selection("requester") == PROFILES["requester"]

    def test_unions_a_domain_and_a_profile(self):
        assert resolve_selection("database,admin") == (
            DOMAINS["database"] | PROFILES["admin"]
        )


class TestWantsPower:
    @pytest.mark.parametrize("spec", ["power", "architect", "PoWeR", "workflow,power"])
    def test_true_when_a_power_keyword_is_present(self, spec):
        assert wants_power(spec) is True

    @pytest.mark.parametrize("spec", [None, "", "workflow", "all", "default"])
    def test_false_otherwise(self, spec):
        assert wants_power(spec) is False


def _registry_with_all_tools() -> tuple[ToolRegistry, MCPServer]:
    mcp = MCPServer("toolset-selection-test")
    registry = ToolRegistry(mcp=mcp)
    registry.register_tools()
    return registry, mcp


def _live_pipefy_names(mcp: MCPServer) -> set[str]:
    return {t.name for t in mcp._tool_manager.list_tools()} & set(PIPEFY_TOOL_NAMES)


class TestApplyToolsetSelection:
    """``apply_toolset_selection`` narrows the live surface via ``retain_only``."""

    @pytest.mark.parametrize("spec", [None, "", "all", "default"])
    def test_no_curation_is_a_noop(self, spec):
        registry, mcp = _registry_with_all_tools()
        withheld = registry.apply_toolset_selection(spec)
        assert withheld == set()
        assert _live_pipefy_names(mcp) == set(PIPEFY_TOOL_NAMES)

    def test_selection_keeps_only_the_named_domains(self):
        registry, mcp = _registry_with_all_tools()
        registry.apply_toolset_selection("database,analytics")
        assert _live_pipefy_names(mcp) == set(
            DOMAINS["database"] | DOMAINS["analytics"]
        )

    def test_floor_then_selection_intersects(self):
        """Selection runs after the remote floor, so survivors are floor ∩ selection."""
        registry, mcp = _registry_with_all_tools()
        registry.apply_remote_profile(remote_mode=True)
        floored = _live_pipefy_names(mcp)
        registry.apply_toolset_selection("intelligence")
        live = _live_pipefy_names(mcp)
        assert live == floored & set(DOMAINS["intelligence"])
        # intelligence has remote-safe tools, so the intersection is non-empty
        assert live

    def test_selection_cannot_widen_past_the_floor(self):
        """A domain tool the floor withheld is not re-added by selecting its domain."""
        registry, mcp = _registry_with_all_tools()
        registry.apply_remote_profile(remote_mode=True)
        registry.apply_toolset_selection("intelligence")
        # create_llm_provider is in `intelligence` but not remote-safe (floored out).
        assert "create_llm_provider" not in _live_pipefy_names(mcp)

    def test_selects_a_persona_profile(self):
        registry, mcp = _registry_with_all_tools()
        registry.apply_toolset_selection("requester")
        assert _live_pipefy_names(mcp) == set(PROFILES["requester"])


EXPECTED_PROFILES = frozenset(
    {"requester", "operator", "manager", "builder", "admin", "auditor"}
)


class TestProfiles:
    """``PROFILES`` are overlapping, journey-sized subsets of the registered tools."""

    def test_profile_keys_are_the_locked_set(self):
        assert set(PROFILES) == EXPECTED_PROFILES

    def test_every_profile_is_a_non_empty_subset_of_registered_tools(self):
        for name, tools in PROFILES.items():
            assert tools, f"empty profile: {name}"
            phantom = sorted(tools - PIPEFY_TOOL_NAMES)
            assert not phantom, (
                f"profile {name} references unregistered tools: {phantom}"
            )

    def test_profile_names_never_collide_with_domains_or_keywords(self):
        reserved = set(DOMAINS) | {"all", "default", "power", "architect"}
        assert set(PROFILES).isdisjoint(reserved)

    def test_operator_is_contained_in_manager(self):
        """Manager is the operator surface plus oversight, so it must be a superset."""
        assert PROFILES["operator"] <= PROFILES["manager"]


_META_TOOLS = frozenset(
    {"get_tool_categories", "search_tools", "describe_tool", "execute_tool"}
)


class TestApplyPowerProfile:
    """``apply_power_profile`` hides curated tools behind the catalog meta-tools."""

    def test_local_exposes_meta_tools_and_raw_graphql_only(self):
        registry, mcp = _registry_with_all_tools()
        hidden = registry.apply_power_profile()
        visible = {t.name for t in mcp._tool_manager.list_tools()}
        # Only the 4 meta-tools plus the 5 raw-GraphQL tools remain visible.
        assert visible == _META_TOOLS | POWER_GRAPHQL_TOOLS
        # Everything else is hidden but snapshotted (reachable via execute_tool).
        assert "get_pipe" in hidden
        assert hidden == set(PIPEFY_TOOL_NAMES) - POWER_GRAPHQL_TOOLS

    def test_remote_then_power_hides_only_the_floored_surface(self):
        """Power runs after the floor: the visible raw-GraphQL set is floor ∩ power."""
        registry, mcp = _registry_with_all_tools()
        registry.apply_remote_profile(remote_mode=True)
        floored = _live_pipefy_names(mcp)
        hidden = registry.apply_power_profile()
        # A tool the floor already withheld is never in the power catalog.
        assert "create_llm_provider" not in hidden
        # Hidden catalog is exactly the floored surface minus the visible raw-GraphQL.
        assert hidden == floored - POWER_GRAPHQL_TOOLS
