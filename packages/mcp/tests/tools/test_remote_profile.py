"""Tests for the default-deny remote-profile tool allowlist (#304)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.tools.registry import PIPEFY_TOOL_NAMES, ToolRegistry
from pipefy_mcp.tools.remote_profile import REMOTE, REMOTE_META_KEY, is_remote_tool

# Expected remote-safe seed. Every addition here is a deliberate, reviewed change:
# a tool earns a place only by carrying meta=REMOTE on its registration AND being
# listed here, and the drift guard below asserts the two stay in lockstep.
REMOTE_SEED = frozenset(
    {
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
    }
)


def _registry_with_all_tools() -> tuple[ToolRegistry, FastMCP]:
    """Register every Pipefy tool on a real FastMCP, as the lifespan does."""
    mcp = FastMCP("remote-profile-test")
    container = Mock(spec=ServicesContainer)
    container.pipefy_client = MagicMock()
    registry = ToolRegistry(mcp=mcp, services_container=container)
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
