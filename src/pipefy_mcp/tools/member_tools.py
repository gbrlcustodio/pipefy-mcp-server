"""MCP tools for pipe member management (invite, remove, set role)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from pipefy_mcp.models.validators import PipefyId
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.member_tool_helpers import (
    build_member_error_payload,
    build_member_success_payload,
    handle_member_tool_graphql_error,
)
from pipefy_mcp.tools.validation_helpers import validate_tool_id


class MemberTools:
    """MCP tools for inviting, removing, and setting roles for pipe members."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def invite_members(
            pipe_id: PipefyId,
            members: list[dict[str, Any]],
            debug: bool = False,
        ) -> dict[str, Any]:
            """Invite one or more users to a pipe.

            `members` is a list of dicts with `email` and `role_name`.

            Args:
                pipe_id: ID of the pipe.
                members: List of member dicts with `email` and `role_name`.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            pipe_id, err = validate_tool_id(pipe_id, "pipe_id")
            if err is not None:
                return err
            if not isinstance(members, list) or not members:
                return build_member_error_payload(
                    message="Invalid 'members': provide a non-empty list of dicts with 'email' and 'role_name'.",
                )
            for i, m in enumerate(members):
                if not isinstance(m, dict):
                    return build_member_error_payload(
                        message=f"Invalid 'members': item {i} must be a dict with 'email' and 'role_name'.",
                    )
                if "email" not in m or "role_name" not in m:
                    return build_member_error_payload(
                        message=f"Invalid 'members': item {i} must have 'email' and 'role_name'.",
                    )
            try:
                raw = await client.invite_members(pipe_id, members)
            except Exception as exc:  # noqa: BLE001
                return handle_member_tool_graphql_error(
                    exc, "Invite members failed.", debug=debug
                )
            return build_member_success_payload(
                message="Members invited.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def remove_member_from_pipe(
            ctx: Context[ServerSession, None],
            pipe_id: PipefyId,
            user_ids: list[PipefyId],
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Permanently remove one or more users from a pipe.

            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval. Elicitation does not authorize
            deletion (only ``confirm=True`` does).

            Service account guard: when ``PIPEFY_SERVICE_ACCOUNT_IDS`` is set, user IDs in
            that list cannot be removed via this tool (returns an error); use the Pipefy UI
            if intentional. When the env var is unset or empty, the guard is not applied.

            Args:
                pipe_id: ID of the pipe.
                user_ids: List of user IDs to remove.
                confirm: Set to True to execute the removal (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            pipe_id, err = validate_tool_id(pipe_id, "pipe_id")
            if err is not None:
                return err
            if not isinstance(user_ids, list) or not user_ids:
                return build_member_error_payload(
                    message="Invalid 'user_ids': provide a non-empty list of user IDs.",
                )
            if not all(uid.strip() for uid in user_ids):
                return build_member_error_payload(
                    message="Invalid 'user_ids': each ID must be a non-empty string.",
                )

            protected_ids = settings.pipefy.service_account_ids
            if protected_ids:
                protected_set = set(protected_ids)
                blocked = [uid for uid in user_ids if uid in protected_set]
                if blocked:
                    if len(blocked) == 1:
                        msg = (
                            f"Cannot remove service account {blocked[0]} - "
                            "this would break all write operations for this pipe. "
                            "Remove it via the Pipefy UI if intentional."
                        )
                    else:
                        msg = (
                            f"Cannot remove service accounts {', '.join(blocked)} - "
                            "this would break all write operations for this pipe. "
                            "Remove it via the Pipefy UI if intentional."
                        )
                    return build_member_error_payload(message=msg)

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"{len(user_ids)} member(s) from pipe {pipe_id}",
            )
            if guard is not None:
                return guard

            await ctx.debug(
                f"remove_member_from_pipe: calling mutation with "
                f"pipe_id={pipe_id!r} (type={type(pipe_id).__name__}), "
                f"user_ids={user_ids!r}"
            )
            try:
                raw = await client.remove_members_from_pipe(pipe_id, user_ids)
            except ValueError as exc:
                return build_member_error_payload(message=str(exc))
            except Exception as exc:  # noqa: BLE001
                await ctx.debug(
                    f"remove_member_from_pipe: mutation failed: {type(exc).__name__}: {exc}"
                )
                return handle_member_tool_graphql_error(
                    exc, "Remove members from pipe failed.", debug=debug
                )

            await ctx.debug(
                "remove_member_from_pipe: mutation succeeded, verifying removal"
            )
            warning = await _verify_removal(client, pipe_id, user_ids)
            return build_member_success_payload(
                message="Members removed from pipe.",
                data=raw,
                warning=warning,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def set_role(
            pipe_id: PipefyId,
            member_id: PipefyId,
            role_name: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Set a member's role on a pipe.

            Service account warning: when ``PIPEFY_SERVICE_ACCOUNT_IDS`` includes ``member_id``,
            the success payload may include a ``warning`` field reminding you to keep write
            permissions for that account. When the env var is unset or empty, no warning is added.

            Args:
                pipe_id: ID of the pipe.
                member_id: User ID of the member.
                role_name: New role name (e.g. 'member', 'admin').
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            pipe_id, err = validate_tool_id(pipe_id, "pipe_id")
            if err is not None:
                return err
            member_id, err = validate_tool_id(member_id, "member_id")
            if err is not None:
                return err
            if not isinstance(role_name, str) or not role_name.strip():
                return build_member_error_payload(
                    message="Invalid 'role_name': provide a non-empty string.",
                )
            try:
                raw = await client.set_role(pipe_id, member_id, role_name.strip())
            except Exception as exc:  # noqa: BLE001
                return handle_member_tool_graphql_error(
                    exc, "Set role failed.", debug=debug
                )
            warning: str | None = None
            protected_ids = settings.pipefy.service_account_ids
            if protected_ids and member_id in protected_ids:
                warning = (
                    "Warning: you changed the role of a service account. "
                    "Ensure the new role retains write permissions."
                )
            return build_member_success_payload(
                message="Role updated.",
                data=raw,
                warning=warning,
            )


async def _verify_removal(
    client: PipefyClient,
    pipe_id: str,
    user_ids: list[str],
) -> str | None:
    """Check whether removed members are actually gone from the pipe.

    Returns a warning string when any requested user IDs are still present,
    or ``None`` when all were successfully removed.  Silently returns
    ``None`` on non-numeric ``pipe_id`` (verification requires ``int``)
    or if the verification query itself fails.
    """
    pipe_id_str = str(pipe_id).strip()
    if not pipe_id_str.isdigit():
        return None

    try:
        members_data = await client.get_pipe_members(pipe_id_str)
    except Exception:  # noqa: BLE001
        return None

    members = (members_data.get("pipe") or {}).get("members", [])
    remaining_ids: set[str] = set()
    for m in members:
        user = m.get("user") if isinstance(m.get("user"), dict) else {}
        if user.get("id"):
            remaining_ids.add(str(user["id"]))
        if user.get("uuid"):
            remaining_ids.add(str(user["uuid"]))

    requested = {str(uid) for uid in user_ids}
    still_present = requested & remaining_ids
    if not still_present:
        return None

    ids_str = ", ".join(sorted(still_present))
    return (
        f"API returned success but member(s) [{ids_str}] are still present in the pipe. "
        "They may have org-level permissions that override pipe-level removal."
    )
