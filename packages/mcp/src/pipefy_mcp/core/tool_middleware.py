"""Ordered middleware chain around MCP tool invocation.

The server needs a seam to run cross-cutting logic around each tool call. Some of
it spans every deployment (observability, and downstream protection such as
honoring the API's 429s or circuit-breaking); some is specific to the multi-tenant
hosted profile (per-user quotas, rate limiting, and cost attribution keyed on the
validated caller).

The SDK supplies the outer seam: ``MCPServer(middleware=[...])`` takes a list of
``ServerMiddleware``, each an ``async (ctx, call_next)`` wrapping every inbound
message. This module adapts that one message-level slot into the tool-level chain
the rest of the package registers against. The composition root builds the
middleware list per profile, passes it to :func:`build_tool_call_middleware`, and
hands the single resulting ``ServerMiddleware`` to the ``MCPServer`` constructor.
Middleware run outer-to-inner in list order, may short-circuit (return an error
result without invoking the tool), and read the validated caller from the
in-flight request.

Two reasons this adapter layer exists rather than having consumers write
``ServerMiddleware`` directly. The SDK marks its ``middleware`` list provisional,
so keeping :class:`ToolCallContext` and :data:`ToolCallMiddleware` as the
registration surface confines any churn there to this module. And a
``ServerMiddleware`` sees every method (``initialize``, ``tools/list``,
notifications), while every consumer here wants tool calls only; the filter
belongs in one place, not in each middleware.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcp import types
from mcp.types import methods as spec_methods

from pipefy_mcp.auth.request_identity import CallerIdentity, caller_identity
from pipefy_mcp.core.tool_error_envelope import tool_error

if TYPE_CHECKING:
    from mcp.server import ServerRequestContext
    from mcp.server.context import CallNext as SdkCallNext
    from mcp.server.context import HandlerResult, ServerMiddleware

__all__ = [
    "CallNext",
    "ToolCallContext",
    "ToolCallMiddleware",
    "build_tool_call_middleware",
    "compose",
    "context_from_server_request",
    "result_is_error",
    "short_circuit_error",
]

# The bounded, values-free view of a call's arguments. Keys come straight off the
# JSON-RPC body before any validation, so an authenticated caller controls their
# count and length; the caps keep one call from flooding a downstream log line.
_MAX_ARG_KEYS = 64
_MAX_ARG_KEY_LENGTH = 200

# The one method this chain wraps. Taken off the request model rather than
# hardcoded so a spec rename travels with the SDK.
TOOLS_CALL_METHOD: str = types.CallToolRequest.model_fields["method"].default


@dataclass(frozen=True)
class ToolCallContext:
    """What a tool-call middleware sees for one invocation.

    ``tool_name`` and ``arguments`` are read off the inbound params before any
    validation, so middleware observes the un-coerced, client-sent arguments (the
    SDK validates and coerces downstream, inside ``call_next``). A malformed
    ``tools/call`` therefore still reaches middleware, which is deliberate: a
    governance layer counting calls must see the ones that go on to fail
    validation. ``argument_keys`` is the bounded, values-free view a
    privacy-sensitive consumer (logging) should prefer; ``arguments`` values are
    passed unbounded to any consumer that opts to read them.

    ``request_id`` correlates a call to its HTTP request when one is available;
    otherwise it falls back to the JSON-RPC message id, which is client-chosen and
    only unique within a session (see :func:`context_from_server_request`).

    ``protocol_version`` is the revision negotiated for this connection. A
    middleware that short-circuits owns the wire shape of the result it returns,
    and that shape is per-revision, so :func:`short_circuit_error` needs it.
    """

    argument_keys: tuple[str, ...]
    identity: CallerIdentity
    protocol_version: str
    request_id: str | None
    tool_name: str
    arguments: dict[str, Any] | None


# A middleware calls ``call_next(ctx)`` to run the inner chain (ending at the
# tool), or returns its own result to short-circuit without running it.
CallNext = Callable[[ToolCallContext], Awaitable["HandlerResult"]]
ToolCallMiddleware = Callable[[ToolCallContext, CallNext], Awaitable["HandlerResult"]]


def _argument_keys(arguments: dict[str, Any] | None) -> tuple[str, ...]:
    """Sorted, values-free argument key names, bounded so one call can't flood a log."""
    if not arguments:
        return ()
    keys = sorted(str(key)[:_MAX_ARG_KEY_LENGTH] for key in arguments)
    if len(keys) > _MAX_ARG_KEYS:
        dropped = len(keys) - _MAX_ARG_KEYS
        keys = keys[:_MAX_ARG_KEYS]
        keys.append(f"...+{dropped} more")
    return tuple(keys)


def _request_id(ctx: ServerRequestContext[Any, Any]) -> str | None:
    """The correlation id for this call: the HTTP one when present, else the message id.

    Prefers the id an HTTP request-logging ASGI middleware stamped into
    ``scope["state"]``, so a tool line and its ``http_request`` line share a value.
    Falls back to the JSON-RPC message id, which is all stdio has.
    """
    request_id: Any = None
    if ctx.request is not None:
        # scope["state"] is a dict under Starlette, but guard the type: the default
        # only covers an absent key, so a present non-dict would crash the read.
        state = ctx.request.scope.get("state")
        if isinstance(state, dict):
            request_id = state.get("request_id")
    if request_id is None:
        request_id = ctx.request_id
    return str(request_id) if request_id is not None else None


def context_from_server_request(
    ctx: ServerRequestContext[Any, Any],
) -> ToolCallContext:
    """Build the :class:`ToolCallContext` for the in-flight ``tools/call``.

    Reads the raw inbound ``params`` mapping. A client that omits ``name`` cannot
    reach a tool at all, so an absent name is reported as ``""`` rather than
    raising here and turning a client's malformed request into a server fault.
    """
    params = ctx.params or {}
    name = params.get("name")
    arguments = params.get("arguments")
    if not isinstance(arguments, dict):
        arguments = None
    return ToolCallContext(
        argument_keys=_argument_keys(arguments),
        identity=caller_identity(ctx.request),
        protocol_version=ctx.protocol_version,
        request_id=_request_id(ctx),
        tool_name=name if isinstance(name, str) else "",
        arguments=arguments,
    )


def compose(middlewares: Sequence[ToolCallMiddleware], terminal: CallNext) -> CallNext:
    """Fold ``middlewares`` around ``terminal`` into one ``call_next``.

    Registration order is outer-to-inner: ``[A, B]`` runs ``A`` then ``B`` then the
    tool, and unwinds in reverse. A middleware that returns without awaiting
    ``call_next`` short-circuits the rest of the chain and the tool.
    """
    call_next = terminal
    for middleware in reversed(middlewares):
        call_next = _bind(middleware, call_next)
    return call_next


def _bind(middleware: ToolCallMiddleware, call_next: CallNext) -> CallNext:
    """Bind one middleware ahead of ``call_next`` (own scope, no late binding)."""

    async def run(ctx: ToolCallContext) -> HandlerResult:
        return await middleware(ctx, call_next)

    return run


def result_is_error(result: HandlerResult) -> bool:
    """Whether a tool-call result reports an error, whichever shape it arrives in.

    ``HandlerResult`` is polymorphic, and a middleware sees BOTH shapes, so read the
    flag through here rather than off an attribute:

    - the SDK's own handler and :func:`short_circuit_error` return the **serialized
      wire dict**, keyed ``isError`` in camelCase (``ServerRunner._on_request``
      shapes a handler's result for the wire inside the middleware chain, so the
      outermost span records a failing return);
    - a middleware that builds its own result may still return a ``CallToolResult``
      **model**, with a snake_case ``is_error``.

    Reading ``result.is_error`` directly is the trap: on the dict it silently
    returns the default, so every real tool failure reads as a success. Anything
    without the flag (an ``InputRequiredResult``) is not an error.
    """
    if isinstance(result, Mapping):
        # by_alias serialization gives camelCase; accept the field name too, so a
        # middleware that dumps a model without by_alias is read correctly.
        return bool(result.get("isError") or result.get("is_error"))
    return bool(getattr(result, "is_error", False))


def short_circuit_error(
    ctx: ToolCallContext,
    message: str,
    *,
    code: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A short-circuit result a middleware returns instead of running the tool.

    Carries the canonical ``tool_error`` envelope so a client reads a governance
    stop (quota, rate limit) the same way it reads a tool's own failure, but sets
    ``isError=True`` deliberately: the tool never ran, distinct from a tool that ran
    and reported a business error (``isError=False``). Bypassing the SDK's handler,
    it builds the result directly, putting the envelope in the serialized ``content``
    (where an in-tool error carries it too) and in ``structuredContent``. The match
    to an in-tool error is on the decoded envelope, not the byte serialization.

    Returns the **wire dict**, not the model, because a short-circuiting middleware
    owns its response envelope: the SDK shapes a handler's result per negotiated
    revision inside ``ServerRunner._serialize``, and that runs in ``call_next``, so
    a result returned without awaiting it is never shaped. Left as a model,
    ``CallToolResult`` would dump its 2026-era ``resultType`` default onto a
    connection whose revision has no such field, and the client's own surface
    validation ignores extras, so nothing would object. ``serialize_server_result``
    is the SDK's supported per-revision shaper (a legacy revision drops
    ``resultType``, 2026-07-28 keeps it), so this defers to it rather than deciding
    which keys belong at which revision.

    One shape difference from a real result remains, on 2026-07-28 only: the ``_meta``
    ``io.modelcontextprotocol/serverInfo`` stamp. ``_serialize`` applies it via
    ``_stamp_server_info`` after the per-revision shaper, on the ``call_next`` path
    only, and the SDK does not patch a middleware's own result up afterwards. So a
    modern client sees the stamp on a tool's result and not on a middleware denial
    (measured: real result carries ``_meta``, a short circuit has none). Left as is:
    the stamp comes off the ``MCPServer`` (``server.server_info_stamp``) and
    :class:`ToolCallContext` carries no route to it, so reproducing that pipeline step
    would mean widening the context for a ``_meta`` field no client is known to read.
    """
    envelope = tool_error(message, code=code, details=details)
    result = types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(envelope, indent=2))],
        structured_content=envelope,
        is_error=True,
    )
    return spec_methods.serialize_server_result(
        TOOLS_CALL_METHOD,
        ctx.protocol_version,
        result.model_dump(by_alias=True, mode="json", exclude_none=True),
    )


def build_tool_call_middleware(
    middlewares: Sequence[ToolCallMiddleware],
) -> ServerMiddleware[Any] | None:
    """Adapt the tool-call chain into one ``ServerMiddleware``, or ``None`` if empty.

    ``None`` for an empty list so the composition root registers nothing: the
    default (no middleware) path then pays nothing per call, rather than routing
    every inbound message through a pass-through that builds and discards a
    context.

    The returned middleware sees every inbound message and delegates all but
    ``tools/call`` straight to ``call_next``, untouched. Only a tool call is
    adapted into a :class:`ToolCallContext` and run through the chain.
    """
    if not middlewares:
        return None

    async def server_middleware(
        ctx: ServerRequestContext[Any, Any], call_next: SdkCallNext
    ) -> HandlerResult:
        if ctx.method != TOOLS_CALL_METHOD:
            return await call_next(ctx)

        async def terminal(_tool_ctx: ToolCallContext) -> HandlerResult:
            # The SDK context, not the tool-call view: `call_next` resumes the
            # dispatcher, which reads params off `ctx` itself. Note `ToolCallContext`
            # is frozen against rebinding only: its `arguments` is the same mapping
            # object as `ctx.params["arguments"]`, so a middleware that mutates it in
            # place does rewrite the call the tool receives. Rewriting deliberately
            # should go through the SDK's own `replace(ctx, params=...)`.
            return await call_next(ctx)

        chain = compose(middlewares, terminal)
        return await chain(context_from_server_request(ctx))

    return server_middleware
