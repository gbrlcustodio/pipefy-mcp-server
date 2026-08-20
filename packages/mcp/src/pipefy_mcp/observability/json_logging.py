"""Pure builders and stderr JSON emitter for hosted structured log events."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, Literal

ToolCallOutcome = Literal["ok", "error", "cancelled", "elicitation"]

OBSERVABILITY_LOGGER_NAME = "pipefy_mcp.observability.structured"

# Structured events always emit at INFO on this logger. PIPEFY_MCP_LOG_LEVEL
# governs the SDK root logger (text) only, so quieting noisy text logs does
# not silently drop hosted request/tool lines.
STRUCTURED_LOG_LEVEL = logging.INFO

HTTP_REQUEST_EVENT_KEYS = frozenset(
    {
        "event",
        "timestamp",
        "method",
        "path",
        "status",
        "duration_ms",
        "client_ip",
        "session_id",
        "request_id",
        "sub",
        "client_id",
    }
)

TOOL_CALL_EVENT_KEYS = frozenset(
    {
        "event",
        "timestamp",
        "tool",
        "outcome",
        "duration_ms",
        "arg_keys",
        "request_id",
        "client_id",
    }
)

UNNAMED_TOOL = "<unnamed>"
"""The ``tool`` label for a ``tools/call`` that named no tool.

Middleware deliberately sees a request that will go on to fail request-layer
validation, so a ``tools/call`` whose params carry no ``name`` reaches the chain and
gets a line. Its ``tool_name`` is genuinely empty, but an empty label groups under a
blank bucket in any dashboard that facets by tool, next to the real ones. The angle
brackets cannot collide with a tool name (they are not valid in one), so the bucket
reads as what it is. ``ctx.tool_name`` itself stays ``""``: it is the raw view of what
the client sent, and a governance middleware matching on it must not see a name the
client did not send.
"""


_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def normalize_log_level(log_level: str) -> int:
    """Map a settings/env log level string to a ``logging`` level constant.

    An explicit map rather than ``getattr(logging, ...)``: the module carries
    uppercase attributes that are not levels (``BASIC_FORMAT``) and aliases the
    settings ``Literal`` rejects (``WARN``, ``FATAL``); both must fail here too.
    """
    normalized = log_level.upper()
    try:
        return _LOG_LEVELS[normalized]
    except KeyError as exc:
        raise ValueError(
            f"invalid log level: received {log_level!r}, expected one of "
            "DEBUG, INFO, WARNING, ERROR, CRITICAL"
        ) from exc


def configure_observability_logging() -> logging.Logger:
    """Attach a stderr JSON-line handler pinned at INFO (``propagate=False``).

    Does not take ``PIPEFY_MCP_LOG_LEVEL``: that knob configures the SDK's root
    logger only. Hosted structured lines stay at INFO so an operator can quiet
    text logs without losing request/tool debugging events.
    """
    logger = logging.getLogger(OBSERVABILITY_LOGGER_NAME)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(STRUCTURED_LOG_LEVEL)
    logger.setLevel(STRUCTURED_LOG_LEVEL)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def reset_observability_logging() -> None:
    """Remove observability handlers (test isolation)."""
    logger = logging.getLogger(OBSERVABILITY_LOGGER_NAME)
    logger.handlers.clear()
    logger.propagate = True


def emit_structured_event(event: dict[str, Any]) -> None:
    """Emit one allowlisted event as a single JSON line on stderr."""
    line = json.dumps(event, separators=(",", ":"))
    logging.getLogger(OBSERVABILITY_LOGGER_NAME).info(line)


def _utc_timestamp_iso(timestamp: datetime | None) -> str:
    instant = timestamp or datetime.now(UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(UTC).isoformat()


def build_http_request_event(
    *,
    method: str,
    path: str,
    status: int | None,
    duration_ms: int | float,
    client_ip: str | None,
    session_id: str | None,
    request_id: str,
    sub: str | None,
    client_id: str | None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Build the allowlisted dict for one HTTP request log line."""
    return {
        "event": "http_request",
        "timestamp": _utc_timestamp_iso(timestamp),
        "method": method,
        "path": path,
        "status": status,
        "duration_ms": duration_ms,
        "client_ip": client_ip,
        "session_id": session_id,
        "request_id": request_id,
        "sub": sub,
        "client_id": client_id,
    }


def build_tool_call_event(
    *,
    tool: str,
    outcome: ToolCallOutcome,
    duration_ms: int | float,
    arg_keys: list[str],
    request_id: str | None,
    client_id: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Build the allowlisted dict for one tool-call log line."""
    return {
        "event": "tool_call",
        "timestamp": _utc_timestamp_iso(timestamp),
        "tool": tool,
        "outcome": outcome,
        "duration_ms": duration_ms,
        "arg_keys": arg_keys,
        "request_id": request_id,
        "client_id": client_id,
    }
