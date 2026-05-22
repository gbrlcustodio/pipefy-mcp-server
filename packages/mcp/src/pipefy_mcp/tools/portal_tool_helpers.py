"""Payload builders and error mappers for portal MCP tools."""

from __future__ import annotations

from gql.transport.exceptions import TransportQueryError

from pipefy_mcp.tools.graphql_error_helpers import extract_graphql_error_codes

_PORTAL_PERMISSION_GUIDANCE = (
    "Permission denied. Request organization permissions such as "
    "`create_portal` or `manage_portals` from your admin."
)


def map_portal_error_to_message(exc: BaseException) -> str:
    """Map portal SDK/GraphQL failures to agent-friendly messages.

    Args:
        exc: Exception raised by ``PipefyClient`` portal methods or GraphQL transport.

    Returns:
        User-visible error string; permission failures mention ``create_portal``
        and ``manage_portals``.
    """
    text = str(exc).strip()
    lowered = text.lower()
    if "create_portal" in lowered or "manage_portals" in lowered:
        return text

    codes: list[str] = []
    if isinstance(exc, TransportQueryError):
        codes = extract_graphql_error_codes(exc)
    errors = getattr(exc, "errors", None)
    if isinstance(errors, list):
        for err in errors:
            if not isinstance(err, dict):
                continue
            extensions = err.get("extensions") or {}
            code = extensions.get("code")
            if isinstance(code, str):
                codes.append(code)

    if "PERMISSION_DENIED" in codes or "permission denied" in lowered:
        return _PORTAL_PERMISSION_GUIDANCE

    return text if text else "Portal operation failed. Try again or contact support."


__all__ = [
    "map_portal_error_to_message",
]
