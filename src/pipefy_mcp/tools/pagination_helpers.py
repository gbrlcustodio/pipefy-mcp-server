"""Bounds validation and top-level ``pagination`` for unified MCP tool responses."""

from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict

from pipefy_mcp.tools.tool_error_envelope import tool_error

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "PaginationInfo",
    "build_pagination_info",
    "validate_page_size",
]


DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


class PaginationInfo(TypedDict, total=False):
    """Top-level pagination block for unified-envelope responses."""

    has_more: bool
    end_cursor: str | None
    page_size: int


def validate_page_size(
    first: int | None,
    *,
    arg_name: str = "first",
    max_size: int = MAX_PAGE_SIZE,
) -> tuple[int, dict[str, Any] | None]:
    """Normalize and validate a pagination ``first`` argument.

    Returns ``(DEFAULT_PAGE_SIZE, None)`` when ``first`` is None. On valid
    integer input returns ``(n, None)``. On invalid input returns
    ``(0, error_dict)``; return that dict from the tool unchanged.

    Args:
        first: The requested page size, or None to use the default.
        arg_name: Name of the tool argument (appears in the error message to
            help agents fix their call). Default "first".
        max_size: Upper bound. Defaults to ``MAX_PAGE_SIZE``; tools with an
            API-imposed narrower range may pass a smaller value.
    """
    if first is None:
        return DEFAULT_PAGE_SIZE, None
    try:
        n = int(first)
    except (TypeError, ValueError):
        return 0, tool_error(
            f"Invalid '{arg_name}': must be an integer between 1 and {max_size}.",
            code="INVALID_ARGUMENTS",
        )
    if n < 1 or n > max_size:
        return 0, tool_error(
            f"Invalid '{arg_name}': must be between 1 and {max_size} (got {n}).",
            code="INVALID_ARGUMENTS",
            details={"min": 1, "max": max_size, "provided": n},
        )
    return n, None


def build_pagination_info(
    *,
    page_info: dict[str, Any] | None,
    page_size: int,
) -> PaginationInfo:
    """Build a ``PaginationInfo`` from a GraphQL ``pageInfo`` subtree.

    Args:
        page_info: The ``pageInfo`` dict as returned by Pipefy's GraphQL
            connections (keys ``hasNextPage``, ``endCursor``). ``None`` or an
            empty dict yields ``has_more=False, end_cursor=None``.
        page_size: Page size used for the request (already validated).
    """
    info: PaginationInfo = {"page_size": page_size}
    if page_info:
        info["has_more"] = bool(page_info.get("hasNextPage"))
        info["end_cursor"] = page_info.get("endCursor")
    else:
        info["has_more"] = False
        info["end_cursor"] = None
    return info
