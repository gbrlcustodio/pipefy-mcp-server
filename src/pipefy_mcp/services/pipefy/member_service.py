"""GraphQL operations for pipe member management (invite, remove, set role)."""

from __future__ import annotations

from typing import Any

from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.member_queries import (
    INVITE_MEMBERS_MUTATION,
    REMOVE_MEMBERS_FROM_PIPE_MUTATION,
    SET_ROLE_MUTATION,
)
from pipefy_mcp.settings import PipefySettings


class MemberService(BasePipefyClient):
    """Invite, remove, and set roles for pipe members."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    async def invite_members(
        self,
        pipe_id: str,
        members: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Invite one or more users to a pipe by email.

        Args:
            pipe_id: ID of the pipe.
            members: List of dicts with at least `email` and `role_name`.
        """
        emails = [{"email": m["email"], "role_name": m["role_name"]} for m in members]
        return await self.execute_query(
            INVITE_MEMBERS_MUTATION,
            {"input": {"pipe_id": pipe_id, "emails": emails}},
        )

    async def remove_members_from_pipe(
        self,
        pipe_id: str,
        user_ids: list[str],
    ) -> dict[str, Any]:
        """Remove one or more users from a pipe.

        Args:
            pipe_id: ID of the pipe.
            user_ids: List of user IDs to remove.
        """
        return await self.execute_query(
            REMOVE_MEMBERS_FROM_PIPE_MUTATION,
            {
                "input": {
                    "pipeUuid": pipe_id,
                    "usersUuids": user_ids,
                }
            },
        )

    async def set_role(
        self,
        pipe_id: str,
        member_id: str,
        role_name: str,
    ) -> dict[str, Any]:
        """Set a member's role on a pipe.

        Args:
            pipe_id: ID of the pipe.
            member_id: User ID of the member.
            role_name: New role name (e.g. 'member', 'admin').
        """
        return await self.execute_query(
            SET_ROLE_MUTATION,
            {
                "input": {
                    "pipe_id": pipe_id,
                    "member": {"user_id": member_id, "role_name": role_name},
                }
            },
        )
