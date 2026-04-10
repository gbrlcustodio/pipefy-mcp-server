"""Pipefy tool rebinding when FastMCP ``lifespan`` runs more than once in-process."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipefy_mcp.core.fastmcp_tool_lifecycle import remove_fastmcp_tools_by_name

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

PIPEFY_REPEAT_VISIT_FLAG_ATTR = "_pipefy_cleared_tools_once"
PIPEFY_OWNED_TOOL_NAMES_ATTR = "_pipefy_tool_names"


def prepare_app_for_repeat_pipefy_tool_registration(app: FastMCP) -> None:
    """Remove only Pipefy-owned tools before re-registering on a repeat lifespan visit.

    Runs **only** after a prior lifespan completed tool registration successfully
    (see :func:`mark_pipefy_tool_registration_complete`). Does not mutate the
    repeat-visit flag: that is set only after ``register_tools()`` succeeds so a
    failed initialization cannot leave the app marked as a consolidated repeat visit.

    FastMCP's ToolManager keeps the first registered callable when names collide.
    In-process MCP sessions (tests, Cursor) can enter lifespan multiple times;
    ``initialize_services`` then updates the container but tools would still call
    the old client unless we remove stale Pipefy tools before ``register_tools``.

    Tools registered outside :class:`pipefy_mcp.tools.registry.ToolRegistry` are left intact.

    Args:
        app: FastMCP server instance bound to this process.
    """
    if not getattr(app, PIPEFY_REPEAT_VISIT_FLAG_ATTR, False):
        return
    owned = getattr(app, PIPEFY_OWNED_TOOL_NAMES_ATTR, None)
    if not owned:
        logger.warning(
            "Repeat MCP lifespan visit but %s is missing or empty; "
            "skipping selective Pipefy tool cleanup.",
            PIPEFY_OWNED_TOOL_NAMES_ATTR,
        )
        return
    remove_fastmcp_tools_by_name(app, set(owned))


def mark_pipefy_tool_registration_complete(app: FastMCP, names: set[str]) -> None:
    """Persist owned tool names and mark that a lifespan registration completed.

    Call only after ``ToolRegistry.register_tools()`` succeeds.

    Args:
        app: FastMCP server instance.
        names: Exact tool names from :class:`pipefy_mcp.tools.registry.ToolRegistry`
            (must match ``ToolManager.remove_tool``).
    """
    setattr(app, PIPEFY_OWNED_TOOL_NAMES_ATTR, set(names))
    setattr(app, PIPEFY_REPEAT_VISIT_FLAG_ATTR, True)
