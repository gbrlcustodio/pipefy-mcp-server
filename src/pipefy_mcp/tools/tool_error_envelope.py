"""Canonical MCP tool error shapes (Cons3).

All tools that return ``{"success": false, ...}`` should use
:func:`tool_error` so ``error`` is a structured object (not a bare string).

**Convention**

* **Failure** - ``{"success": false, "error": {"message": str, "code"?: str, "details"?: dict}}``.
  Optional top-level fields (e.g. ``valid_destinations``) are allowed for tools
  that already expose extra context.
* **Success** - use :func:`tool_success` for the unified shape; other tools may
  still return legacy flat payloads.

**User-visible text (N1):** Strings passed to :func:`tool_error` and other returned
``error.message`` (and equivalent warnings) use ASCII only: straight ``'`` / ``"``,
hyphen ``-`` or sem ``;`` for pauses, and ``->`` for mappings. Avoid Unicode
em dashes (U+2014) and arrow characters in those strings.

Use :func:`tool_error_message` when reading a payload in clients or tests so
string comparisons stay stable.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

from typing_extensions import NotRequired, TypedDict

__all__ = [
    "ToolErrorDetail",
    "ToolFailurePayload",
    "ToolSuccessPayload",
    "tool_error",
    "tool_error_message",
    "tool_success",
]


class ToolErrorDetail(TypedDict):
    """User-visible error body (``message`` required; other keys optional)."""

    message: str
    code: NotRequired[str]
    details: NotRequired[dict[str, Any]]


class ToolFailurePayload(TypedDict):
    """``success: false`` with a structured ``error`` object."""

    success: Literal[False]
    error: ToolErrorDetail


class ToolSuccessPayload(TypedDict, total=False):
    """``success: true`` with optional ``data``, ``message``, ``pagination``."""

    success: Literal[True]
    data: dict[str, Any]
    message: str
    pagination: dict[str, Any]


def tool_error(
    message: str,
    *,
    code: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standard tool failure dict with ``error.message`` (and optional code/details).

    Args:
        message: User-visible explanation (keep free of raw secrets; sanitize upstream).
        code: Optional machine-friendly code (e.g. first GraphQL ``extensions.code``).
        details: Optional structured context (e.g. validation hints), keep JSON-serializable.
    """
    err: dict[str, Any] = {"message": message}
    if code is not None:
        err["code"] = code
    if details:
        err["details"] = details
    return {"success": False, "error": err}


def tool_success(
    data: dict[str, Any] | None = None,
    *,
    message: str | None = None,
    pagination: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical success payload. Optional keys omitted when args are ``None``.

    Args:
        data: Verbatim GraphQL subtree; keep query-root keys inside this dict.
        message: Optional short human-readable summary.
        pagination: Optional top-level pagination block (typically built by
            :func:`pipefy_mcp.tools.pagination_helpers.build_pagination_info`).
    """
    payload: dict[str, Any] = {"success": True}
    if data is not None:
        payload["data"] = data
    if message is not None:
        payload["message"] = message
    if pagination is not None:
        payload["pagination"] = pagination
    return payload


def tool_error_message(payload: Mapping[str, Any]) -> str:
    """Return the user-visible error string from a tool result dict.

    Accepts the canonical ``error: { "message": ... }`` form. If ``error`` is
    still a plain string (legacy), returns it unchanged.
    """
    err = payload.get("error")
    if isinstance(err, str):
        return err
    if isinstance(err, dict):
        msg = err.get("message")
        if isinstance(msg, str):
            return msg
    return ""
