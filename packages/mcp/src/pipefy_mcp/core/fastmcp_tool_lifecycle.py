"""FastMCP ``_tool_manager`` boundary for removing tools by name.

Used by :meth:`pipefy_mcp.tools.registry.ToolRegistry.retain_only` to withhold
tools that are not remote-safe when the remote profile is applied.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mcp.server.fastmcp.exceptions import ToolError

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)


def remove_fastmcp_tools_by_name(app: FastMCP, names: set[str]) -> None:
    """Remove tools registered on ``app`` by exact name.

    Removes only the named tools, leaving third-party or test-registered tools
    intact (used to withhold non-remote-safe tools under the remote profile).

    Args:
        app: FastMCP server instance.
        names: Names as returned by the tool manager (must match ``remove_tool``).

    """
    if not names:
        return
    try:
        tool_manager = app._tool_manager
    except AttributeError:
        logger.warning(
            "FastMCP internal API changed; missing _tool_manager. "
            "Cannot remove tools by name; re-registration may leave stale handlers."
        )
        return

    for name in names:
        try:
            tool_manager.remove_tool(name)
        except ToolError:
            logger.debug("Tool %r not registered; skipping remove.", name)
