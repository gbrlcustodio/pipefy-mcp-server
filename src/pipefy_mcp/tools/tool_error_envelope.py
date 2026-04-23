"""Canonical MCP tool error shapes (Cons3).

All tools that return ``{"success": false, ...}`` should use
:func:`tool_error` so ``error`` is a structured object (not a bare string).

**Convention**

* **Failure** - ``{"success": false, "error": {"message": str, "code"?: str, "details"?: dict}}``.
  Optional top-level fields (e.g. ``valid_destinations``) are allowed for tools
  that already expose extra context.
* **Success** - remains tool-specific (flat fields or ``data``) until a follow-up
  unification pass.

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
    "tool_error",
    "tool_error_message",
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
