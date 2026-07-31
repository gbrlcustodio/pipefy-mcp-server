"""Structured per-tool-call logging as a tool-call middleware.

The first consumer of the tool-call middleware chain (see
:mod:`pipefy_mcp.core.tool_middleware`): it emits one JSON line per call via the
hosted structured emitter (``build_tool_call_event`` /
``emit_structured_event``). Being the first consumer, it also exercises the
chain end to end.

Privacy: never logs the bearer, and never logs argument values, only their
(bounded) key names.

Output goes through the dedicated observability logger on stderr. It must never
write to stdout: the stdio transport frames JSON-RPC over stdout, so a stray log
line there corrupts the protocol. Under HTTP, ``configure_observability_logging``
pins that logger at INFO independently of ``PIPEFY_MCP_LOG_LEVEL``.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from mcp import UrlElicitationRequiredError

from pipefy_mcp.core.tool_middleware import CallNext, ToolCallContext, result_is_error
from pipefy_mcp.observability.json_logging import (
    UNNAMED_TOOL,
    ToolCallOutcome,
    build_tool_call_event,
    emit_structured_event,
)

if TYPE_CHECKING:
    from mcp.server.context import HandlerResult


def _outcome(result: HandlerResult) -> ToolCallOutcome:
    """Map a terminal result to an outcome.

    Delegates the flag read to :func:`result_is_error`, which handles both shapes a
    middleware sees: the wire dict the SDK's handler returns for a real tool call,
    and the ``CallToolResult`` model a short-circuit builds. Reading the attribute
    directly would report every real tool failure as ``ok``.
    """
    return "error" if result_is_error(result) else "ok"


async def tool_log_middleware(
    ctx: ToolCallContext, call_next: CallNext
) -> HandlerResult:
    """Emit one structured log line around a tool call, then propagate the result.

    A tool body error surfaces as a result with ``isError=True`` (the SDK's
    handler turns tool exceptions into an error result), so the common path logs
    from the returned result. The two exceptions that DO propagate through the
    chain each get their own non-error outcome and are re-raised: ``CancelledError``
    (client disconnect / ``notifications/cancelled``) and
    ``UrlElicitationRequiredError`` (the client must visit a URL to continue).
    Swallowing either would break cancellation and elicitation. ``BaseException``
    (not ``Exception``) is caught so a ``CancelledError`` cannot skip the handler
    and let ``finally`` emit a stale ``ok``.

    A ``tools/call`` that named no tool reaches the chain too (middleware sees raw
    params), and is logged under :data:`UNNAMED_TOOL` rather than an empty ``tool``,
    so it does not land in a dashboard's blank bucket beside the real tool names.
    """
    started_at = time.perf_counter()
    outcome: ToolCallOutcome = "ok"
    try:
        result = await call_next(ctx)
        outcome = _outcome(result)
        return result
    except asyncio.CancelledError:
        outcome = "cancelled"
        raise
    except UrlElicitationRequiredError:
        outcome = "elicitation"
        raise
    except BaseException:
        outcome = "error"
        raise
    finally:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
        emit_structured_event(
            build_tool_call_event(
                tool=ctx.tool_name or UNNAMED_TOOL,
                outcome=outcome,
                duration_ms=duration_ms,
                arg_keys=list(ctx.argument_keys),
                request_id=ctx.request_id,
                client_id=ctx.identity.client_id,
            )
        )
