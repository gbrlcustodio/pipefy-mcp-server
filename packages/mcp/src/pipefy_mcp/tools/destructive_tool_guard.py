"""Reusable confirmation guard for destructive MCP tools.

Every tool with ``destructiveHint=True`` should call
:func:`check_destructive_confirmation` **before** executing the deletion.

MCP elicitation is unused: some clients auto-accept elicitation prompts when
tools are invoked programmatically.

Proceed requires ``confirm=True`` and a verified confirmation token. The token
orders the two-step protocol (preview, then confirm); it is not an authorization
control. API permission remains the boundary that allows or denies the deletion.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal

from mcp.server.mcpserver import Context
from typing_extensions import NotRequired, TypedDict

from pipefy_mcp.auth.request_identity import require_request_bearer
from pipefy_mcp.tools.destructive_confirmation_token import (
    ConfirmationTokenFailure,
    classify_confirmation_token_failure,
    mint_confirmation_token,
    verify_confirmation_token,
)

_PROCESS_SIGNING_KEY = secrets.token_bytes(32)


class DestructivePreviewPayload(TypedDict):
    """Returned when the tool needs confirmation before deletion."""

    success: Literal[False]
    requires_confirmation: Literal[True]
    resource: str
    message: str
    confirmation_token: str
    dependents: NotRequired[dict[str, Any]]


DependentsResolver = Callable[[], Awaitable[dict[str, Any] | None]]


def signing_key_for(ctx: Context) -> bytes:
    """HMAC key for this request: SHA-256 of the bearer, else a process key."""
    try:
        bearer = require_request_bearer(ctx.request_context.request)
    except Exception:  # noqa: BLE001
        return _PROCESS_SIGNING_KEY
    return hashlib.sha256(bearer.encode("utf-8")).digest()


async def check_destructive_confirmation(
    ctx: Context,
    *,
    confirm: bool,
    resource_descriptor: str,
    resource_identity: Mapping[str, Any],
    tool_name: str,
    confirmation_token: str | None = None,
    dependents_resolver: DependentsResolver | None = None,
    irreversible_sentence: str | None = None,
) -> DestructivePreviewPayload | None:
    """Gate a destructive operation behind ``confirm=True`` and a verified token.

    Call this **after** fetching resource info but **before** executing the
    deletion.

    Args:
        ctx: MCP request context; used to derive the HMAC signing key.
        confirm: Must be ``True`` together with a verified token to proceed.
        resource_descriptor: Human-readable description of the resource about
            to be deleted (e.g. ``"phase 'Initial' (ID: 42)"``). Used in
            preview payloads; never signed.
        resource_identity: Resource ids bound into the confirmation token.
        tool_name: Destructive tool name bound into the confirmation token.
        confirmation_token: Token from a prior preview, or ``None``.
        dependents_resolver: Optional async callable (no arguments) that returns
            a dict to attach under ``dependents`` on the preview, or ``None`` /
            empty dict to skip enrichment. Invoked on every preview path;
            never invoked when proceeding. Exceptions are swallowed so the
            base preview is still returned.
        irreversible_sentence: Optional first preview sentence. Defaults to
            ``Deleting {resource_descriptor} is permanent...``. Pass a custom
            sentence when the operation is not a deletion of that descriptor.

    Returns:
        ``None`` when ``confirm=True`` and the token verifies. The caller
        should proceed with the deletion.
        A preview payload otherwise. The caller must return it as-is.
    """
    identity = dict(resource_identity)
    key = signing_key_for(ctx)
    now = int(time.time())
    if confirm and verify_confirmation_token(
        confirmation_token,
        tool_name=tool_name,
        resource_identity=identity,
        key=key,
        now=now,
    ):
        return None

    token_status: ConfirmationTokenFailure | None = None
    if confirm:
        token_status = classify_confirmation_token_failure(
            confirmation_token,
            tool_name=tool_name,
            resource_identity=identity,
            key=key,
        )
    minted = mint_confirmation_token(
        tool_name=tool_name,
        resource_identity=identity,
        key=key,
        now=now,
    )
    preview = _build_preview_payload(
        resource_descriptor,
        confirmation_token=minted,
        token_status=token_status,
        irreversible_sentence=irreversible_sentence,
    )
    if dependents_resolver is not None:
        try:
            deps = await dependents_resolver()
        except Exception:  # noqa: BLE001
            deps = None
        if deps:
            preview = {**preview, "dependents": deps}
    return preview


def _build_preview_payload(
    resource_descriptor: str,
    *,
    confirmation_token: str,
    token_status: ConfirmationTokenFailure | None = None,
    irreversible_sentence: str | None = None,
) -> DestructivePreviewPayload:
    sentences = [
        irreversible_sentence
        or f"⚠️ Deleting {resource_descriptor} is permanent and cannot be undone.",
    ]
    if token_status == "missing":
        sentences.append("The confirmation token is missing.")
    elif token_status == "invalid_or_expired":
        sentences.append("The previous confirmation token was invalid or expired.")
    elif token_status == "identity_mismatch":
        sentences.append(
            "The previous confirmation token does not match this tool and resource identity."
        )
    sentences.append(
        "Show this preview to the user and get their explicit approval before continuing."
    )
    sentences.append(
        "Once they approve, call again with confirm=True "
        f'and confirmation_token="{confirmation_token}".'
    )
    return {
        "success": False,
        "requires_confirmation": True,
        "resource": resource_descriptor,
        "confirmation_token": confirmation_token,
        "message": " ".join(sentences),
    }


__all__ = [
    "DependentsResolver",
    "DestructivePreviewPayload",
    "check_destructive_confirmation",
]
