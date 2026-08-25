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
    a server-initiated request. ``ServerSession.can_send_request`` is the SDK's
    own gate for the second: ``DispatchContext.send_raw_request`` raises
    ``NoBackChannelError`` exactly when it is ``False``.

    The advertised capability alone is not enough, because three deployment
    shapes clear it and still have no back channel:

    * Protocol revision 2026-07-28. A client on that revision still declares
      ``elicitation`` in its request envelope, but the revision has no
      server-to-client channel, so the modern HTTP entry builds its context
      with ``can_send_request=False`` (``_streamable_http_modern``).
    * A stateless HTTP transport at any revision. A server request can be
      written to the POST's response stream, but the client's reply has nowhere
      to land, so ``StreamableHTTPSessionManager`` stamps ``False``
      (``streamable_http_manager``).
    * ``json_response=True`` on the stateful Streamable HTTP transport, at any
      revision including 2025-11-25. A JSON body carries only the response, so
      ``StreamableHTTPServerTransport._message_metadata`` stamps
      ``can_send_request=not is_json_response_enabled`` (``streamable_http``).
      Measured over the real ASGI stack: ``json_response=False`` gives ``True``
      at 2025-11-25, ``json_response=True`` gives ``False``.

    The third case is the one an embedder controls, and it is the flag the
    hosted wrapper sets (``pipefy_remote_mcp.asgi`` passes
    ``json_response=True`` so a POST answers as plain JSON rather than SSE).
    ``wire_hosted_observability`` defaults the flag to ``False`` and the serving
    path leaves it there, so a deployment built from this repository keeps its
    back channel and another embedder decides for itself. A deployment that
    keeps that flag has no elicitation at any revision, so ``create_card`` and
    ``fill_card_phase_fields`` always take their no-elicitation path there and
    callers must pass ``fields`` explicitly.

    A session object that does not expose ``can_send_request`` (an older SDK, a
    hand-built test double) is treated as able to send, and the
    ``NoBackChannelError`` handling at the elicitation call sites covers that
    case.

    Revision 2026-07-28 replaces this mechanism rather than removing it: a
    resolved parameter carries the question and the negotiated revision decides
    the transport, so a new tool declares a resolver instead of calling this.
    ``docs/contributing/adr/0003-mcp-tools-express-outcomes.md`` holds that
    decision.

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
