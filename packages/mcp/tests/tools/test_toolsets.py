"""Drift-guard for the subject-domain partition in ``tools/toolsets.py``.

The partition must stay a complete, disjoint cover of every registered tool.
Completeness is keyed to ``PIPEFY_TOOL_NAMES`` (no hardcoded count): registering
a new tool without assigning it a domain fails ``test_partition_is_complete``,
which is the point — the guard is the repo's tool-surface completeness gate.
"""

from itertools import combinations

from pipefy_mcp.tools.registry import PIPEFY_TOOL_NAMES
from pipefy_mcp.tools.toolsets import DOMAINS

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
