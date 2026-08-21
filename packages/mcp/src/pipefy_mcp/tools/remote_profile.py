"""Remote-profile exposure marker for MCP tools.

Default-deny model for the hosted/remote profile: a tool is exposed in remote
mode only if its registration carries ``meta=REMOTE``. Any unmarked tool is
implicitly withheld. The marker is the single co-located source of truth (it
rides on the ``@mcp.tool`` decorator), and is enforced at registration time by
:meth:`pipefy_mcp.tools.registry.ToolRegistry.apply_remote_profile`.

The marker is greppable (``rg 'meta=REMOTE'``) and machine-enforced, unlike the
retired ``GATED:<PROFILE>`` comment convention it replaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.mcpserver.tools.base import Tool

REMOTE_META_KEY = "remote"

# The only marker. Pass to ``meta=`` on a tool whose decorator opts it into the
# remote profile. The dict shape is forward-compatible: a later toolset feature
# can add keys (e.g. ``{"remote": True, "toolset": "automation"}``) without
# breaking ``is_remote_tool``, which reads only ``REMOTE_META_KEY``.
REMOTE: dict[str, Any] = {REMOTE_META_KEY: True}


def is_remote_tool(tool: Tool) -> bool:
    """Return True when ``tool`` is marked remote-safe via ``meta=REMOTE``."""
    return (tool.meta or {}).get(REMOTE_META_KEY) is True
