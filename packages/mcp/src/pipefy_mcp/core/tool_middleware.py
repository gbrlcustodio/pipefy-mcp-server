"""Ordered middleware chain around MCP tool invocation.

The server needs a seam to run cross-cutting logic around each tool call. Some of
it spans every deployment (observability, and downstream protection such as
honoring the API's 429s or circuit-breaking); some is specific to the multi-tenant
hosted profile (per-user quotas, rate limiting, and cost attribution keyed on the
validated caller). The MCP SDK offers no such seam: FastMCP dispatches every tool
call through a single ``CallToolRequest`` entry in the low-level server's
``request_handlers`` dict, and the only way to observe or govern a call is to
overwrite that one private slot, so the next feature that needs it clobbers the
previous.

This module turns that single slot into an ordered chain. Middleware register on
:class:`~pipefy_mcp.core.runtime.McpRuntime` (the public seam) and this module
wraps FastMCP's handler exactly once, at build time, composing the registered
middleware around it. Middleware run outer-to-inner in registration order, may
short-circuit (return an error result without invoking the tool), and read the
validated caller from the per-message request context.

The wrap targets ``app._mcp_server.request_handlers[CallToolRequest]`` and is
tested against ``mcp==1.25.0``. If that pin moves, re-verify the handler is still
a single ``async def handler(req: CallToolRequest) -> ServerResult`` populated by
``FastMCP._setup_handlers``.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcp import types
from mcp.server.lowlevel.server import request_ctx

from pipefy_mcp.auth.request_identity import CallerIdentity, caller_identity

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

__all__ = [
    "CallNext",
    "CallerIdentity",
    "ToolCallContext",
    "ToolCallMiddleware",
    "compose",
    "context_from_request",
    "install_tool_call_middleware",
    "short_circuit_error",
]

# The bounded, values-free view of a call's arguments. Keys come straight off the
# JSON-RPC body before any validation, so an authenticated caller controls their
# count and length; the caps keep one call from flooding a downstream log line.
_MAX_ARG_KEYS = 64
_MAX_ARG_KEY_LENGTH = 200

# Holds the middleware set the installed chain was built from, so a second install
# with the same set is a no-op and one with a different set fails loud rather than
# silently dropping the newcomers. The marker lives on the wrapped function (per
# app), not on a module or class global: each FastMCP instance has its own handler,
# so a global would wrap the first app and silently skip every later one built in
# the same process.
_INSTALLED_MARKER = "__pipefy_tool_call_chain__"


@dataclass(frozen=True)
class ToolCallContext:
    """What a tool-call middleware sees for one invocation.

    ``tool_name`` and ``arguments`` are read-only views over ``req.params``, so the
    context cannot drift from the request it wraps. ``arguments`` is the raw
    JSON-RPC argument map: FastMCP registers the terminal with
    ``validate_input=False`` and does its own coercion/defaulting downstream, so
    middleware observes the un-coerced, client-sent arguments. ``argument_keys`` is
    the bounded, values-free view a privacy-sensitive consumer (logging) should
    prefer; ``arguments`` values are passed unbounded to any consumer that opts to
    read them.

    ``request_id`` correlates a call to its HTTP request when one is available;
    otherwise it falls back to the JSON-RPC message id, which is client-chosen and
    only unique within a session (see :func:`context_from_request`). ``req`` is the
    untouched request the terminal handler is called with.
    """

    argument_keys: tuple[str, ...]
    identity: CallerIdentity
    request_id: str | None
    req: types.CallToolRequest

    @property
    def tool_name(self) -> str:
        return self.req.params.name

    @property
    def arguments(self) -> dict[str, Any] | None:
        return self.req.params.arguments


# A middleware calls ``call_next(ctx)`` to run the inner chain (ending at the
# tool), or returns its own ServerResult to short-circuit without running it.
CallNext = Callable[[ToolCallContext], Awaitable[types.ServerResult]]
ToolCallMiddleware = Callable[
    [ToolCallContext, CallNext], Awaitable[types.ServerResult]
]

# FastMCP's registered ``CallToolRequest`` handler: the innermost callable the
# chain wraps.
_TerminalHandler = Callable[[types.CallToolRequest], Awaitable[types.ServerResult]]


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


def _request_scope() -> tuple[Any | None, str | None]:
    """Return ``(request, request_id)`` from the in-flight message context.

    The low-level server sets ``request_ctx`` per JSON-RPC message before calling
    the handler, so both are available at chain entry. ``request`` is the Starlette
    request under HTTP (``None`` over stdio). ``request_id`` prefers an HTTP-layer
    correlation id stamped into ``scope["state"]`` (what a request-logging ASGI
    middleware would set) and falls back to the JSON-RPC message id.
    """
    try:
        ctx = request_ctx.get()
    except LookupError:
        return None, None

    request = ctx.request
    request_id: Any = None
    if request is not None:
        # scope["state"] is a dict under Starlette, but guard the type: the default
        # only covers an absent key, so a present non-dict would crash the read.
        state = request.scope.get("state")
        if isinstance(state, dict):
            request_id = state.get("request_id")
    if request_id is None:
        request_id = ctx.request_id
    return request, (str(request_id) if request_id is not None else None)


def context_from_request(req: types.CallToolRequest) -> ToolCallContext:
    """Build the :class:`ToolCallContext` for the in-flight call."""
    request, request_id = _request_scope()
    return ToolCallContext(
        argument_keys=_argument_keys(req.params.arguments),
        identity=caller_identity(request),
        request_id=request_id,
        req=req,
    )


def compose(
    middlewares: Sequence[ToolCallMiddleware], terminal: _TerminalHandler
) -> CallNext:
    """Fold ``middlewares`` around ``terminal`` into one ``call_next``.

    Registration order is outer-to-inner: ``[A, B]`` runs ``A`` then ``B`` then the
    tool, and unwinds in reverse. A middleware that returns without awaiting
    ``call_next`` short-circuits the rest of the chain and the tool.
    """

    async def call_terminal(ctx: ToolCallContext) -> types.ServerResult:
        return await terminal(ctx.req)

    call_next: CallNext = call_terminal
    for middleware in reversed(middlewares):
        call_next = _bind(middleware, call_next)
    return call_next


def _bind(middleware: ToolCallMiddleware, call_next: CallNext) -> CallNext:
    """Bind one middleware ahead of ``call_next`` (own scope, no late binding)."""

    async def run(ctx: ToolCallContext) -> types.ServerResult:
        return await middleware(ctx, call_next)

    return run


def short_circuit_error(
    message: str,
    *,
    code: str | None = None,
    details: dict[str, Any] | None = None,
) -> types.ServerResult:
    """A short-circuit result a middleware returns instead of running the tool.

    Carries the canonical ``tool_error`` envelope so the body matches an in-tool
    failure, but sets ``isError=True`` deliberately: a governance stop (quota,
    rate limit) means the tool never ran, which is distinct from a tool that ran
    and reported a business error (``isError=False``). Because this bypasses
    FastMCP's terminal, it replicates FastMCP's dict normalization itself (the
    same envelope in both ``structuredContent`` and serialized ``content``).
    """
    # Imported lazily: pipefy_mcp.tools.tool_error_envelope pulls the tools
    # package, which imports the runtime, which imports this module. A top-level
    # import would form a cycle at load time.
    from pipefy_mcp.tools.tool_error_envelope import tool_error

    envelope = tool_error(message, code=code, details=details)
    return types.ServerResult(
        types.CallToolResult(
            content=[
                types.TextContent(type="text", text=json.dumps(envelope, indent=2))
            ],
            structuredContent=envelope,
            isError=True,
        )
    )


def install_tool_call_middleware(
    app: FastMCP, middlewares: Sequence[ToolCallMiddleware]
) -> None:
    """Wrap ``app``'s ``CallToolRequest`` handler with the composed chain, once.

    A no-op when ``middlewares`` is empty: FastMCP's handler is left untouched, so
    the default (no middleware) path pays nothing per call rather than routing every
    tool call through a pass-through wrapper that builds and discards a context.

    Idempotent per app: the marker lives on the installed handler, so a repeat
    install on the same app with the same middleware set is a no-op while a
    different app (built later in the same process) wraps its own fresh handler. A
    repeat install with a *different* set raises rather than silently drop the
    newcomers, because the marker snapshots the set at install time (the supported
    pattern is to register everything, then install once). Raises too if FastMCP
    has not registered the handler, so an SDK-internal change fails loud rather than
    silently skipping the chain.
    """
    if not middlewares:
        return

    handlers = app._mcp_server.request_handlers
    if types.CallToolRequest not in handlers:
        raise RuntimeError(
            "CallToolRequest handler missing from request_handlers; the FastMCP "
            f"internal contract changed. Present keys: {list(handlers.keys())!r}"
        )

    terminal = handlers[types.CallToolRequest]
    installed = getattr(terminal, _INSTALLED_MARKER, None)
    if installed is not None:
        if tuple(middlewares) != installed:
            raise RuntimeError(
                "a tool-call chain is already installed on this app with a "
                "different middleware set; register all middleware before calling "
                "install_tool_call_middleware once"
            )
        return

    chain = compose(middlewares, terminal)

    async def chained(req: types.CallToolRequest) -> types.ServerResult:
        return await chain(context_from_request(req))

    setattr(chained, _INSTALLED_MARKER, tuple(middlewares))
    handlers[types.CallToolRequest] = chained
