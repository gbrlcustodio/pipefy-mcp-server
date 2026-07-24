"""Catalog meta-tools for the ``power`` discovery profile.

The ``power`` profile hides the curated tool bodies from ``tools/list`` and
exposes four meta-tools that discover and dispatch to them: ``get_tool_categories``
(the subject-domain map), ``search_tools`` (a keyword ranker), ``describe_tool``
(a hidden tool's schema), and ``execute_tool`` (invoke a hidden tool). The hidden
tools stay fully validated: ``execute_tool`` runs each through its own
``PipefyValidationTool.run``, so argument coercion and the error envelope apply
exactly as if the tool were called directly.

The catalog is a snapshot taken *after* the remote floor, so it holds only tools
the floor already allowed — ``execute_tool`` can never reach a withheld tool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from pipefy_mcp.core.tool_error_envelope import tool_error, tool_success
from pipefy_mcp.tools.toolsets import DOMAIN_DESCRIPTIONS, domain_of

if TYPE_CHECKING:
    from mcp.server.fastmcp.tools.base import Tool

# Cap on ``search_tools`` results so a broad keyword cannot flood the context.
_MAX_SEARCH_RESULTS = 25


def _rank(catalog: dict[str, Tool], keyword: str) -> list[Tool]:
    """Rank catalog tools against ``keyword`` — name matches outweigh description."""
    terms = keyword.lower().split()
    scored: list[tuple[int, str, Tool]] = []
    for tool in catalog.values():
        name = tool.name.lower()
        description = (tool.description or "").lower()
        score = sum(3 * (term in name) + (term in description) for term in terms)
        if score:
            scored.append((score, tool.name, tool))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [tool for _, _, tool in scored[:_MAX_SEARCH_RESULTS]]


def _summary(tool: Tool) -> dict[str, Any]:
    """One-line catalog entry: name, first docstring line, and subject domain."""
    description = (tool.description or "").strip()
    first_line = description.splitlines()[0] if description else ""
    return {
        "name": tool.name,
        "summary": first_line,
        "category": domain_of(tool.name),
    }


def register_meta_tools(mcp: FastMCP, catalog: dict[str, Tool]) -> None:
    """Register the four ``power``-profile meta-tools over a hidden-tool ``catalog``.

    ``catalog`` maps each hidden tool's name to its live ``Tool`` (a post-floor
    snapshot). The meta-tools close over it; nothing here re-reads the registry.
    """

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def get_tool_categories() -> dict:
        """List the subject-domain categories of the tools reachable via execute_tool.

        Each category has a description and the names of its hidden tools. Use it to
        orient before ``search_tools`` / ``describe_tool`` / ``execute_tool``.
        """
        by_domain: dict[str, list[str]] = {}
        for name in catalog:
            by_domain.setdefault(domain_of(name) or "other", []).append(name)
        categories = [
            {
                "category": domain,
                "description": DOMAIN_DESCRIPTIONS.get(domain, ""),
                "tool_count": len(sorted_names),
                "tools": sorted(sorted_names),
            }
            for domain, sorted_names in sorted(by_domain.items())
        ]
        return tool_success(data={"categories": categories})

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def search_tools(keyword: str) -> dict:
        """Find hidden tools whose name or description matches ``keyword``.

        Searches the tool catalog, not the GraphQL schema — for schema types use
        ``search_schema``. Space-separated terms are matched independently; name
        matches rank above description matches. Returns up to 25
        ``{name, summary, category}`` entries, best first. Follow up with
        ``describe_tool`` then ``execute_tool``.
        """
        matches = [_summary(tool) for tool in _rank(catalog, keyword)]
        return tool_success(data={"tools": matches, "count": len(matches)})

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def describe_tool(name: str) -> dict:
        """Return a hidden tool's full description and JSON input schema by name.

        Read this before ``execute_tool`` to learn the tool's required and optional
        arguments. Unknown names return an error pointing back to ``search_tools``.
        """
        tool = catalog.get(name)
        if tool is None:
            return tool_error(
                f"No tool named '{name}' is available. Use search_tools to find one.",
                code="TOOL_NOT_FOUND",
            )
        return tool_success(
            data={
                "name": tool.name,
                "category": domain_of(tool.name),
                "description": tool.description or "",
                "input_schema": tool.parameters,
            }
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
    async def execute_tool(
        name: str,
        ctx: Context,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Invoke a hidden tool by ``name`` with its ``arguments`` and return its result.

        Dispatches to a curated Pipefy tool — for raw GraphQL use ``execute_graphql``
        instead. Runs through the tool's own validation, so ``arguments`` are coerced
        and validated exactly as a direct call would be; an invalid-arguments error
        comes back as the same structured envelope. Only tools listed by
        ``search_tools`` / ``get_tool_categories`` are reachable — a name the profile
        withholds is never callable here.

        Args:
            name: The hidden tool to run (from ``search_tools``).
            arguments: The tool's own arguments, as a JSON object.
        """
        tool = catalog.get(name)
        if tool is None:
            return tool_error(
                f"No tool named '{name}' is available. Use search_tools to find one.",
                code="TOOL_NOT_FOUND",
            )
        # Transparent dispatch: return whatever the tool returns and let any raise
        # propagate exactly as a direct call would. A genuine execution failure
        # surfaces as a protocol error (isError), not a soft-wrapped business
        # envelope; an elicitation request reaches the client. Argument-validation
        # errors still come back as the standard envelope, because
        # PipefyValidationTool.run returns those rather than raising.
        return await tool.run(arguments or {}, context=ctx)
