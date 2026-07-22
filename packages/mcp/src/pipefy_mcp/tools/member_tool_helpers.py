"""Payload builders and GraphQL error mapping for member MCP tools."""

from __future__ import annotations

from typing import Any, Literal, cast

from pipefy_sdk import PipefyClient
from typing_extensions import TypedDict

from pipefy_mcp.core.tool_error_envelope import tool_error
from pipefy_mcp.tools.graphql_error_helpers import (
    handle_tool_graphql_error,
)


async def service_account_is_member(
    client: PipefyClient,
    pipe_id: str,
    email: str,
) -> bool | None:
    """Whether ``email`` is present among the pipe's members after an invite.

    Returns ``True``/``False`` when membership could be checked, or ``None``
    when it could not (non-numeric ``pipe_id``, which ``get_pipe_members``
    cannot resolve, or a failing verification query). ``None`` means "unknown",
    so the caller does not treat an unverifiable invite as a failure.
    """
    pipe_id_str = str(pipe_id).strip()
    if not pipe_id_str.isdigit():
        return None

    try:
        members_data = await client.get_pipe_members(pipe_id_str)
    except Exception:  # noqa: BLE001
        return None

    members = (members_data.get("pipe") or {}).get("members", [])
    target = email.strip().lower()
    for m in members:
        user = m.get("user") if isinstance(m.get("user"), dict) else {}
        if str(user.get("email", "")).lower() == target:
            return True
    return False


class MemberMutationSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    result: dict[str, Any]


class MemberMutationWarningPayload(TypedDict):
    success: Literal[True]
    message: str
    warning: str
    result: dict[str, Any]


def build_member_success_payload(
    *,
    message: str,
    data: dict[str, Any],
    warning: str | None = None,
) -> MemberMutationSuccessPayload | MemberMutationWarningPayload:
    """``success``, ``message``, and mutation ``result``.

    Args:
        message: Short summary for the client.
        data: Raw mutation payload (stored as ``result``).
        warning: Optional warning appended when the operation succeeded
            but post-verification detected an anomaly.
    """
    payload: dict[str, Any] = {"success": True, "message": message, "result": data}
    if warning is not None:
        payload["warning"] = warning
    return cast(MemberMutationSuccessPayload, payload)


def build_member_error_payload(
    *, message: str, code: str | None = None
) -> dict[str, Any]:
    """``success: False`` with ``error`` text.

    Args:
        message: User-visible failure reason.
        code: Optional machine-readable error code (e.g. ``INVALID_ARGUMENTS``).
    """
    return tool_error(message, code=code)


def handle_member_tool_graphql_error(
    exc: BaseException,
    fallback_msg: str,
    *,
    debug: bool = False,
    resource_kind: str | None = None,
    resource_id: str | None = None,
    invalid_args_hint: str | None = None,
) -> dict[str, Any]:
    """Delegate to :func:`handle_tool_graphql_error` with enrichment opt-ins."""
    return handle_tool_graphql_error(
        exc,
        fallback_msg,
        debug=debug,
        resource_kind=resource_kind,
        resource_id=resource_id,
        invalid_args_hint=invalid_args_hint,
    )


__all__ = [
    "MemberMutationSuccessPayload",
    "MemberMutationWarningPayload",
    "build_member_error_payload",
    "build_member_success_payload",
    "handle_member_tool_graphql_error",
    "service_account_is_member",
]
