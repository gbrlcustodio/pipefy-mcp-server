"""MCP tools for pipe member management (invite, remove, set role)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.member_tool_helpers import (
    build_member_error_payload,
    build_member_success_payload,
    handle_member_tool_graphql_error,
)
from pipefy_mcp.tools.validation_helpers import valid_repo_id


class MemberTools:
    """MCP tools for inviting, removing, and setting roles for pipe members."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def invite_members(
            pipe_id: str,
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
            if not valid_repo_id(pipe_id):
                return build_member_error_payload(
                    message="Invalid 'pipe_id': provide a non-empty string or positive integer.",
                )
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
            pipe_id: str,
            user_ids: list[str],
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Permanently remove one or more users from a pipe.

            Two-step operation: call without ``confirm`` to preview, then with
            ``confirm=True`` after user approval. When the MCP client supports
            elicitation, the user is prompted interactively instead.

            Args:
                pipe_id: ID of the pipe.
                user_ids: List of user IDs to remove.
                confirm: Set to True to execute the removal (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_repo_id(pipe_id):
                return build_member_error_payload(
                    message="Invalid 'pipe_id': provide a non-empty string or positive integer.",
                )
            if not isinstance(user_ids, list) or not user_ids:
                return build_member_error_payload(
                    message="Invalid 'user_ids': provide a non-empty list of user IDs.",
                )
            if not all(isinstance(uid, str) and uid.strip() for uid in user_ids):
                return build_member_error_payload(
                    message="Invalid 'user_ids': each ID must be a non-empty string.",
                )

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"{len(user_ids)} member(s) from pipe {pipe_id}",
            )
            if guard is not None:
                return guard

            try:
                raw = await client.remove_members_from_pipe(pipe_id, user_ids)
            except ValueError as exc:
                return build_member_error_payload(message=str(exc))
            except Exception as exc:  # noqa: BLE001
                return handle_member_tool_graphql_error(
                    exc, "Remove members from pipe failed.", debug=debug
                )
            return build_member_success_payload(
                message="Members removed from pipe.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def set_role(
            pipe_id: str,
            member_id: str,
            role_name: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Set a member's role on a pipe.

            Args:
                pipe_id: ID of the pipe.
                member_id: User ID of the member.
                role_name: New role name (e.g. 'member', 'admin').
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_repo_id(pipe_id):
                return build_member_error_payload(
                    message="Invalid 'pipe_id': provide a non-empty string or positive integer.",
                )
            if not isinstance(member_id, str) or not member_id.strip():
                return build_member_error_payload(
                    message="Invalid 'member_id': provide a non-empty string.",
                )
            if not isinstance(role_name, str) or not role_name.strip():
                return build_member_error_payload(
                    message="Invalid 'role_name': provide a non-empty string.",
                )
            try:
                raw = await client.set_role(
                    pipe_id, member_id.strip(), role_name.strip()
                )
            except Exception as exc:  # noqa: BLE001
                return handle_member_tool_graphql_error(
                    exc, "Set role failed.", debug=debug
                )
            return build_member_success_payload(
                message="Role updated.",
                data=raw,
            )
