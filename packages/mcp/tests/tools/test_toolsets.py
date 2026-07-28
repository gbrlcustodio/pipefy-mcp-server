"""Drift-guard for the subject-domain partition in ``tools/toolsets.py``.

The partition must stay a complete, disjoint cover of every registered tool.
Completeness is keyed to ``PIPEFY_TOOL_NAMES`` (no hardcoded count): registering
a new tool without assigning it a domain fails ``test_partition_is_complete``,
which is the point — the guard is the repo's tool-surface completeness gate.
"""

from itertools import combinations

import pytest
from mcp.server.fastmcp import FastMCP

from pipefy_mcp.tools.registry import PIPEFY_TOOL_NAMES, ToolRegistry
from pipefy_mcp.tools.toolsets import DOMAINS, resolve_selection

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


def _registry_with_all_tools() -> tuple[ToolRegistry, FastMCP]:
    mcp = FastMCP("toolset-selection-test")
    registry = ToolRegistry(mcp=mcp)
    registry.register_tools()
    return registry, mcp


def _live_pipefy_names(mcp: FastMCP) -> set[str]:
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
