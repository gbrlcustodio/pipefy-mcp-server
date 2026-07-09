"""Structured per-tool-call logging as a tool-call middleware.

The first consumer of the tool-call middleware chain (see
:mod:`pipefy_mcp.core.tool_middleware`): it emits one JSON line per call with the
tool name, outcome, duration, the caller's client id, argument key names, and a
request id for correlation. Being the first consumer, it also exercises the
chain end to end.

Privacy: never logs the bearer, and never logs argument values, only their
(bounded) key names.

Output goes through the standard ``logging`` module, which writes to stderr. It
must never write to stdout: the stdio transport frames JSON-RPC over stdout, so a
stray log line there corrupts the protocol.

Line integrity depends on the process's root log handler, which this module does
not configure. FastMCP's default ``RichHandler`` wraps at width 80 in a non-TTY,
which would split an event across physical lines; and a deployment that
reconfigures root logging before construction can drop these INFO lines. The
hosted logging wiring (the structured-log emitter) owns installing a plain,
non-wrapping formatter at INFO so the one-line contract holds; until then a host
that cares must install one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Literal

from mcp import UrlElicitationRequiredError, types

from pipefy_mcp.core.tool_middleware import CallNext, ToolCallContext

logger = logging.getLogger("pipefy_mcp.observability.tool_call")

# "cancelled" (client disconnect) and "elicitation" (the tool is asking the client
# to visit a URL) are normal control flow, kept out of "error" so an error-rate
# alert is not tripped by them. A governance short-circuit still reads as "error":
# it returns isError=True and is indistinguishable from a tool-reported failure at
# the result boundary.
ToolCallOutcome = Literal["ok", "error", "cancelled", "elicitation"]


def _outcome(result: types.ServerResult) -> ToolCallOutcome:
    """Map a terminal result to an outcome.

    Reads ``isError`` off the result's root defensively: an experimental
    ``CreateTaskResult`` root has no ``isError`` and reads as ``ok`` rather than
    raising.
    """
    return "error" if getattr(result.root, "isError", False) else "ok"


def _emit(event: dict[str, object]) -> None:
    """Write one structured line via logging (stderr), never stdout."""
    logger.info(json.dumps(event, separators=(",", ":")))


async def tool_log_middleware(
    ctx: ToolCallContext, call_next: CallNext
) -> types.ServerResult:
    """Emit one structured log line around a tool call, then propagate the result.

    A tool body error surfaces as a result with ``isError=True`` (FastMCP's
    terminal turns tool exceptions into an error result), so the common path logs
    from the returned result. The two exceptions that DO propagate through the
    chain each get their own non-error outcome and are re-raised: ``CancelledError``
    (client disconnect / ``notifications/cancelled``) and
    ``UrlElicitationRequiredError`` (the client must visit a URL to continue).
    Swallowing either would break cancellation and elicitation. ``BaseException``
    (not ``Exception``) is caught so a ``CancelledError`` cannot skip the handler
    and let ``finally`` emit a stale ``ok``.
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
        # Guard here, not inside _emit, so the event dict is not built when the
        # line would be discarded.
        if logger.isEnabledFor(logging.INFO):
            duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
            _emit(
                {
                    "event": "tool_call",
                    "tool": ctx.tool_name,
                    "outcome": outcome,
                    "duration_ms": duration_ms,
                    "arg_keys": list(ctx.argument_keys),
                    "client_id": ctx.identity.client_id,
                    "request_id": ctx.request_id,
                }
            )
