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
"""

from __future__ import annotations

import json
import logging
import time
from typing import Literal

from mcp import types

from pipefy_mcp.core.tool_middleware import CallNext, ToolCallContext

logger = logging.getLogger("pipefy_mcp.observability.tool_call")

ToolCallOutcome = Literal["ok", "error"]


def _outcome(result: types.ServerResult) -> ToolCallOutcome:
    """Map a terminal result to an outcome.

    Reads ``isError`` off the result's ``CallToolResult`` root. The attribute is
    read defensively: an experimental ``CreateTaskResult`` root has no ``isError``,
    which should read as ``ok`` rather than raise.
    """
    root = getattr(result, "root", None)
    return "error" if getattr(root, "isError", False) else "ok"


def _emit(event: dict[str, object]) -> None:
    """Write one structured line via logging (stderr), never stdout.

    Serialization runs before ``logger.info``, so it would otherwise be paid even
    when the line is discarded; the ``isEnabledFor`` guard skips it when the level
    is off.
    """
    if not logger.isEnabledFor(logging.INFO):
        return
    logger.info(json.dumps(event, separators=(",", ":")))


async def tool_log_middleware(
    ctx: ToolCallContext, call_next: CallNext
) -> types.ServerResult:
    """Emit one structured log line around a tool call, then propagate the result.

    A tool body error surfaces as a result with ``isError=True`` (FastMCP's
    terminal turns tool exceptions into an error result), so the common path logs
    from the returned result. The exceptions that DO propagate through the chain,
    ``CancelledError`` (client disconnect / ``notifications/cancelled``) and
    ``UrlElicitationRequiredError``, are logged as errors and re-raised: swallowing
    them would break cancellation and elicitation. ``BaseException`` (not
    ``Exception``) is caught so a ``CancelledError`` cannot skip the handler and let
    ``finally`` emit a stale ``ok``.
    """
    started_at = time.perf_counter()
    outcome: ToolCallOutcome = "ok"
    try:
        result = await call_next(ctx)
        outcome = _outcome(result)
        return result
    except BaseException:
        outcome = "error"
        raise
    finally:
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
