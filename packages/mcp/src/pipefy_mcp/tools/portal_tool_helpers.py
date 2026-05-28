"""Payload builders and error mappers for portal MCP tools."""

from __future__ import annotations

from gql.transport.exceptions import TransportQueryError
from pipefy_sdk.exceptions import PortalPermissionError
from pydantic import ValidationError

from pipefy_mcp.tools.graphql_error_helpers import extract_graphql_error_codes
from pipefy_mcp.tools.tool_error_envelope import tool_error

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
    if isinstance(exc, PortalPermissionError):
        return str(exc).strip()

    text = str(exc).strip()
    lowered = text.lower()

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


def validate_portal_optional_string(
    value: str | None,
    field: str,
) -> tuple[str | None, dict[str, object] | None]:
    """Validate optional portal string fields at the MCP tool boundary.

    Args:
        value: Raw string from the tool parameter, or ``None`` when omitted.
        field: Parameter name for error messages (e.g. ``name``).

    Returns:
        ``(stripped_value, None)`` on success, ``(None, error_payload)`` when
        a non-empty string was required but missing or whitespace-only.
    """
    if value is None:
        return None, None
    if not isinstance(value, str) or not value.strip():
        return None, tool_error(
            f"Invalid '{field}': when provided, must be a non-empty string.",
            code="INVALID_ARGUMENTS",
        )
    return value.strip(), None


def validate_portal_page_index(
    index: int | None,
) -> dict[str, object] | None:
    """Reject negative or non-integer sort index at the MCP tool boundary.

    Args:
        index: Optional page sort index from the tool parameter.

    Returns:
        ``None`` when valid or omitted; otherwise an ``INVALID_ARGUMENTS`` envelope.
    """
    if index is None:
        return None
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        return tool_error(
            "Invalid 'index': must be a non-negative integer.",
            code="INVALID_ARGUMENTS",
        )
    return None


def validate_sort_page_ids_no_duplicates(
    page_ids: list[str],
) -> dict[str, object] | None:
    """Reject duplicate entries in an ordered ``page_ids`` list.

    Args:
        page_ids: Cleaned page identifiers after per-item validation.

    Returns:
        ``None`` when all entries are unique; otherwise an ``INVALID_ARGUMENTS`` envelope.
    """
    if len(set(page_ids)) != len(page_ids):
        return tool_error(
            "Invalid 'page_ids': must not contain duplicate page UUIDs.",
            code="INVALID_ARGUMENTS",
        )
    return None


def portal_element_validation_error(exc: ValidationError) -> dict[str, object]:
    """Map SDK portal element model validation to an MCP ``INVALID_ARGUMENTS`` envelope.

    Args:
        exc: Raised by ``CreatePortalElementInput`` or ``UpdatePortalElementInput``.

    Returns:
        Tool failure payload with an actionable ``error.message`` (no Pydantic URLs).
    """
    clauses: list[str] = []
    for err in exc.errors():
        err_type = err.get("type", "")
        if err_type == "value_error":
            ctx = err.get("ctx") or {}
            inner = ctx.get("error")
            if inner is not None:
                clauses.append(str(inner))
                continue
        loc = ".".join(str(part) for part in err.get("loc", ()))
        msg = str(err.get("msg", ""))
        if loc == "type" and err_type == "literal_error":
            clauses.append(
                "Invalid 'type': must be a supported InterfacePageElementType value."
            )
        elif loc:
            clauses.append(f"{loc}: {msg}")
        elif msg:
            clauses.append(msg)
    message = "; ".join(clause for clause in clauses if clause)
    if not message:
        message = "Invalid portal element arguments."
    return tool_error(message, code="INVALID_ARGUMENTS")


__all__ = [
    "map_portal_error_to_message",
    "portal_element_validation_error",
    "validate_portal_optional_string",
    "validate_portal_page_index",
    "validate_sort_page_ids_no_duplicates",
]
