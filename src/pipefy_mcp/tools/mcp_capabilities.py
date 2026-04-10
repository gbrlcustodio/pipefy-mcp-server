"""Safe access to MCP client capability flags.

MCP transports and SDK versions differ in whether ``client_params`` and nested
``capabilities`` are present. Tools must not assume the full chain exists.
"""

from __future__ import annotations

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession


def supports_elicitation(ctx: Context[ServerSession, None]) -> bool:
    """Return whether the connected client advertises elicitation support.

    Args:
        ctx: MCP request context for the active call.

    Returns:
        ``True`` when ``capabilities.elicitation`` is truthy; ``False`` if any
        link in the chain is missing or ``elicitation`` is false/absent.
    """
    session = getattr(ctx, "session", None)
    if session is None:
        return False
    client_params = getattr(session, "client_params", None)
    if client_params is None:
        return False
    capabilities = getattr(client_params, "capabilities", None)
    if capabilities is None:
        return False
    elicitation = getattr(capabilities, "elicitation", None)
    return bool(elicitation)


__all__ = ["supports_elicitation"]
