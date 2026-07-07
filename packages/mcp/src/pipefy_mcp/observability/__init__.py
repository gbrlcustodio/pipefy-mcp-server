"""Hosted observability: structured JSON request and tool-call logging.

Only the stdlib-only emitter surface is re-exported here; the middleware and
wiring stay submodule imports so importing this package never pulls
``starlette`` or the MCP SDK.
"""

from pipefy_mcp.observability.json_logging import (
    OBSERVABILITY_LOGGER_NAME,
    build_http_request_event,
    build_tool_call_event,
    configure_observability_logging,
    emit_structured_event,
    normalize_log_level,
    reset_observability_logging,
)

__all__ = [
    "OBSERVABILITY_LOGGER_NAME",
    "build_http_request_event",
    "build_tool_call_event",
    "configure_observability_logging",
    "emit_structured_event",
    "normalize_log_level",
    "reset_observability_logging",
]
