"""Reusable confirmation guard for destructive MCP tools.

Every tool with ``destructiveHint=True`` should call
:func:`check_destructive_confirmation` **before** executing the deletion.
The guard handles three scenarios:

* **Elicitation available** → prompts the user interactively.
* **No elicitation, ``confirm=False``** → returns a preview payload (no deletion).
* **``confirm=True``** → returns ``None`` so the caller proceeds.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class DestructiveActionConfirmation(BaseModel):
    """Schema shown to the user when the MCP client supports elicitation."""

    confirm: bool = Field(
        ...,
        description="Set to true to confirm the action, or false to cancel.",
    )


class DestructivePreviewPayload(TypedDict):
    """Returned when the tool needs confirmation and elicitation is not available."""

    success: Literal[False]
    requires_confirmation: Literal[True]
    resource: str
    message: str


class DestructiveCancelledPayload(TypedDict):
    success: Literal[False]
    error: str


_CANCEL_MESSAGE = "Action cancelled by user."


async def check_destructive_confirmation(
    ctx: Context[ServerSession, None],
    *,
    confirm: bool,
    resource_descriptor: str,
) -> dict[str, Any] | None:
    """Gate a destructive operation behind user confirmation.

    Call this **after** fetching resource info but **before** executing the
    deletion.  The function handles elicitation (when supported) and the
    two-step ``confirm`` fallback.

    Args:
        ctx: MCP request context (used to check elicitation support and prompt
            the user).
        confirm: Explicit confirmation flag from the tool caller.
        resource_descriptor: Human-readable description of the resource about
            to be deleted (e.g. ``"phase 'Initial' (ID: 42)"``).  Used in
            preview payloads and elicitation prompts.

    Returns:
        ``None`` when the caller should proceed with the deletion.
        A ``dict`` payload when the operation was cancelled or needs
        confirmation — the caller should return this payload as-is.
    """
    can_elicit = ctx.session.client_params.capabilities.elicitation

    if not can_elicit and not confirm:
        return _build_preview_payload(resource_descriptor)

    if can_elicit:
        return await _elicit_confirmation(ctx, resource_descriptor)

    return None


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


async def _elicit_confirmation(
    ctx: Context[ServerSession, None],
    resource_descriptor: str,
) -> dict[str, Any] | None:
    """Prompt the user via MCP elicitation. Returns ``None`` to proceed."""
    confirmation_message = (
        f"⚠️ You are about to permanently delete {resource_descriptor}. "
        "This action is irreversible. Are you sure you want to proceed?"
    )

    try:
        result = await ctx.elicit(
            message=confirmation_message,
            schema=DestructiveActionConfirmation,
        )

        if result.action != "accept":
            return _build_cancel_payload()

        if not result.data.model_dump().get("confirm"):
            return _build_cancel_payload()

    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Failed to request confirmation: {exc!s}"}

    return None


def _build_cancel_payload() -> DestructiveCancelledPayload:
    return {"success": False, "error": _CANCEL_MESSAGE}


__all__ = [
    "DestructiveActionConfirmation",
    "DestructiveCancelledPayload",
    "DestructivePreviewPayload",
    "check_destructive_confirmation",
]
