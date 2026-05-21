"""Payload builders and error mapping for portal MCP read tools."""

from __future__ import annotations

from typing import Any

from pipefy_mcp.tools.introspection_tool_helpers import (
    build_error_payload,
    build_success_payload,
)


def build_list_portals_success_payload(portals: list[dict[str, Any]]) -> dict[str, Any]:
    """Build success payload for ``list_portals``.

    Args:
        portals: Portal summary nodes from the SDK.
    """
    return build_success_payload({"portals": portals}, include_parsed=True)


def build_get_portal_success_payload(portal: dict[str, Any]) -> dict[str, Any]:
    """Build success payload for ``get_portal``.

    Args:
        portal: Portal detail dict from the SDK.
    """
    return build_success_payload(portal, include_parsed=True)


def build_portal_error_payload(error_message: str) -> dict[str, Any]:
    """Build error envelope for portal read tools.

    Args:
        error_message: User-facing explanation.
    """
    return build_error_payload(error_message)


def map_portal_error_to_message(exc: ValueError) -> str:
    """Map SDK ``ValueError`` to a user-facing message.

    Args:
        exc: Raised when org or portal is not found.
    """
    return str(exc)


__all__ = [
    "build_get_portal_success_payload",
    "build_list_portals_success_payload",
    "build_portal_error_payload",
    "map_portal_error_to_message",
]
