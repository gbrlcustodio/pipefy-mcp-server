"""Reusable confirmation guard for destructive MCP tools.

Every tool with ``destructiveHint=True`` should call
:func:`check_destructive_confirmation` **before** executing the deletion.

* ``confirm=False`` → returns a preview payload; **never** deletes. Some MCP clients
  auto-accept elicitation prompts when tools are invoked programmatically; this
  guard therefore does **not** use elicitation to authorize deletion—only an
  explicit follow-up call with ``confirm=True`` does.
* ``confirm=True`` → returns ``None`` so the caller proceeds with the deletion.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from typing_extensions import NotRequired, TypedDict


class DestructivePreviewPayload(TypedDict):
    """Returned when the tool needs confirmation before deletion."""

    success: Literal[False]
    requires_confirmation: Literal[True]
    resource: str
    message: str
    dependents: NotRequired[dict[str, Any]]


DependentsResolver = Callable[[], Awaitable[dict[str, Any] | None]]


class DestructiveCancelledPayload(TypedDict):
    success: Literal[False]
    error: str


async def check_destructive_confirmation(
    _ctx: Context[ServerSession, None],
    *,
    confirm: bool,
    resource_descriptor: str,
    dependents_resolver: DependentsResolver | None = None,
) -> DestructivePreviewPayload | None:
    """Gate a destructive operation behind explicit ``confirm=True``.

    Call this **after** fetching resource info but **before** executing the
    deletion.

    Args:
        _ctx: MCP request context (reserved for future use / logging).
        confirm: Must be ``True`` to allow the deletion to run.
        resource_descriptor: Human-readable description of the resource about
            to be deleted (e.g. ``"phase 'Initial' (ID: 42)"``). Used in
            preview payloads.
        dependents_resolver: Optional async callable (no arguments) that returns
            a dict to attach under ``dependents`` on the preview, or ``None`` /
            empty dict to skip enrichment. Never invoked when ``confirm=True``.
            Exceptions are swallowed so the base preview is still returned.

    Returns:
        ``None`` when the caller should proceed with the deletion.
        A preview payload when ``confirm`` is false — the caller must return
        it as-is.
    """
    if confirm:
        return None

    preview = _build_preview_payload(resource_descriptor)
    if dependents_resolver is not None:
        try:
            deps = await dependents_resolver()
        except Exception:  # noqa: BLE001
            deps = None
        if deps:
            preview = {**preview, "dependents": deps}
    return preview


def _build_preview_payload(resource_descriptor: str) -> DestructivePreviewPayload:
    return {
        "success": False,
        "requires_confirmation": True,
        "resource": resource_descriptor,
        "message": (
            f"⚠️ You are about to permanently delete {resource_descriptor}. "
            "This action is irreversible. Set 'confirm=True' to proceed."
        ),
    }


__all__ = [
    "DependentsResolver",
    "DestructiveCancelledPayload",
    "DestructivePreviewPayload",
    "check_destructive_confirmation",
]
