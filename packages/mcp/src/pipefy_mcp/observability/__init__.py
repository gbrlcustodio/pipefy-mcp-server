"""Hosted-profile observability: middleware that ride the tool-call chain."""

from pipefy_mcp.observability.tool_log_middleware import tool_log_middleware

__all__ = ["tool_log_middleware"]
