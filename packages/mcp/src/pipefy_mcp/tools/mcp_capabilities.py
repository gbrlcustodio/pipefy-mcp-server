"""Safe access to MCP client capability flags.

MCP transports and SDK versions differ in whether ``client_params`` and nested
``capabilities`` are present. Tools must not assume the full chain exists.
"""

from __future__ import annotations

from mcp.server.mcpserver import Context


def supports_elicitation(ctx: Context) -> bool:
    """Return whether this request can actually elicit from the client.

    Two independent conditions have to hold. The client must advertise the
    ``elicitation`` capability, and the request's channel must be able to carry
    a server-initiated request. The advertised capability alone is not enough:
    a client on protocol revision 2026-07-28 still declares ``elicitation`` in
    its request envelope, but that revision has no server-to-client back
    channel, so ``ctx.elicit`` raises ``NoBackChannelError``. The same is true
    on a stateless HTTP transport at any revision, where the client's reply to
    a server request would have nowhere to land.

    ``ServerSession.can_send_request`` is the SDK's own gate:
    ``DispatchContext.send_raw_request`` raises ``NoBackChannelError`` exactly
    when it is ``False``. A session object that does not expose it (an older
    SDK, a hand-built test double) is treated as able to send, and the
    ``NoBackChannelError`` handling at the elicitation call sites covers that
    case.

    Args:
        ctx: MCP request context for the active call.

    Returns:
        ``True`` when ``capabilities.elicitation`` is truthy and the request
        channel can send; ``False`` if any link in the chain is missing,
        ``elicitation`` is false/absent, or there is no back channel.
    """
    session = getattr(ctx, "session", None)
    if session is None:
        return False
    if getattr(session, "can_send_request", True) is False:
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
