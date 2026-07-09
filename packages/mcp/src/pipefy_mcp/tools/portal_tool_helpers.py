"""Payload builders and error mappers for portal MCP tools.

``unpublish_sub_portal`` uses internal_api ``updateSubPortalElement`` with
``subPortalUuid: null`` (not ``deleteSubPortalElement``): live integration
confirms ``get_portal`` -> ``subPortals[].published`` flips to false. CLI
``sub-portal detach`` calls ``deleteSubPortalElement`` to remove wiring only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from gql.transport.exceptions import TransportQueryError
from pipefy_sdk.exceptions import PortalPermissionError
from pydantic import ValidationError

from pipefy_mcp.core.tool_error_envelope import tool_error
from pipefy_mcp.tools.graphql_error_helpers import (
    extract_error_strings,
    extract_graphql_error_codes,
    strip_internal_api_diagnostic_markers,
)
from pipefy_mcp.tools.introspection_tool_helpers import (
    build_error_payload,
    build_success_payload,
)
from pipefy_mcp.tools.validation_helpers import validate_tool_id

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

    if isinstance(exc, TransportQueryError):
        messages = extract_error_strings(exc)
        if messages:
            return strip_internal_api_diagnostic_markers("; ".join(messages))

    return (
        strip_internal_api_diagnostic_markers(text)
        if text
        else "Portal operation failed. Try again or contact support."
    )


def validate_tool_ids(
    raw: dict[str, str],
) -> tuple[dict[str, str] | None, dict[str, object] | None]:
    """Validate multiple Pipefy IDs at the MCP tool boundary.

    Args:
        raw: Map of parameter name to raw ID string.

    Returns:
        ``(cleaned_ids, None)`` on success, or ``(None, error_payload)`` on the
        first invalid ID.
    """
    cleaned: dict[str, str] = {}
    for name, value in raw.items():
        ok, err = validate_tool_id(value, name)
        if err is not None:
            return None, err
        cleaned[name] = ok
    return cleaned, None


def finalize_internal_api_mutation(
    result: dict[str, Any],
    mutation_key: str,
    failure_message: str,
) -> dict[str, object]:
    """Map an Internal API mutation result to MCP success or failure payloads.

    Args:
        result: Raw GraphQL response dict from the SDK.
        mutation_key: Top-level mutation field name (e.g. ``updateSubPortalElement``).
        failure_message: User-visible message when ``success`` is not true.

    Returns:
        Success or error envelope for the MCP tool caller.
    """
    payload = result.get(mutation_key) or {}
    if payload.get("success"):
        return build_success_payload(result, include_parsed=True)
    return build_error_payload(failure_message)


async def run_sub_portal_internal_api_tool(
    *,
    ids: dict[str, str],
    debug_message: str,
    ctx_debug: Callable[[str], Awaitable[None]],
    invoke: Callable[[dict[str, str]], Awaitable[dict[str, Any]]],
    mutation_key: str,
    failure_message: str,
) -> dict[str, object]:
    """Shared shell for sub-portal Internal API write tools.

    Args:
        ids: Tool ID parameters to validate (name -> raw value).
        debug_message: Message passed to ``ctx.debug``.
        ctx_debug: Async debug hook from the MCP tool context.
        invoke: Callable receiving validated IDs and calling ``PipefyClient``.
        mutation_key: Top-level mutation field in the GraphQL response.
        failure_message: User-visible message when ``success`` is not true.

    Returns:
        MCP tool result envelope.
    """
    cleaned, err = validate_tool_ids(ids)
    if err is not None or cleaned is None:
        return err or build_error_payload("Invalid tool IDs.")
    await ctx_debug(debug_message.format(**cleaned))
    try:
        result = await invoke(cleaned)
    except Exception as exc:  # noqa: BLE001
        return build_error_payload(map_portal_error_to_message(exc))
    return finalize_internal_api_mutation(
        result,
        mutation_key,
        failure_message.format(**cleaned),
    )


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
    "finalize_internal_api_mutation",
    "map_portal_error_to_message",
    "portal_element_validation_error",
    "run_sub_portal_internal_api_tool",
    "validate_portal_optional_string",
    "validate_portal_page_index",
    "validate_sort_page_ids_no_duplicates",
    "validate_tool_ids",
]
