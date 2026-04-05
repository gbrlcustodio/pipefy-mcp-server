"""GraphQL operations for pipe member management (invite, remove, set role)."""

from __future__ import annotations

import re
from typing import Any

from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.pipe_service import PipeService
from pipefy_mcp.services.pipefy.queries.member_queries import (
    INVITE_MEMBERS_MUTATION,
    REMOVE_MEMBERS_FROM_PIPE_MUTATION,
    SET_ROLE_MUTATION,
)
from pipefy_mcp.settings import PipefySettings

_PIPE_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class MemberService(BasePipefyClient):
    """Invite, remove, and set roles for pipe members."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
        *,
        pipe_service: PipeService | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)
        self._pipe_service = pipe_service or PipeService(settings=settings, auth=auth)

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
            {"input": {"pipe_id": int(pipe_id), "emails": emails}},
        )

    async def remove_members_from_pipe(
        self,
        pipe_id: str,
        user_ids: list[str],
    ) -> dict[str, Any]:
        """Remove one or more users from a pipe.

        Resolves numeric pipe and user IDs to UUIDs when needed (API expects
        ``pipeUuid`` and ``usersUuids``).

        Args:
            pipe_id: Numeric pipe ID or pipe UUID (with hyphens).
            user_ids: User IDs or UUIDs to remove.
        """
        pipe_id_str = str(pipe_id).strip()
        pipe_obj: dict[str, Any] = {}
        if pipe_id_str.isdigit():
            pipe_data = await self._pipe_service.get_pipe(int(pipe_id_str))
            pipe_obj = pipe_data.get("pipe") or {}
        elif _PIPE_UUID_RE.match(pipe_id_str):
            pipe_data = await self._pipe_service.get_pipe(pipe_id_str)
            pipe_obj = pipe_data.get("pipe") or {}
        else:
            raise ValueError(
                f"pipe_id must be a numeric pipe ID or a pipe UUID, got {pipe_id!r}."
            )

        pipe_uuid = pipe_obj.get("uuid") or pipe_id_str
        pipe_numeric_id = pipe_obj.get("id")
        if isinstance(pipe_numeric_id, str) and pipe_numeric_id.isdigit():
            pipe_numeric_id = int(pipe_numeric_id)

        user_uuids = list(user_ids)
        needs_resolution = any(
            "-" not in str(uid) and str(uid).isdigit() for uid in user_ids
        )
        if needs_resolution and pipe_numeric_id is not None:
            members_data = await self._pipe_service.get_pipe_members(pipe_numeric_id)
            members = (members_data.get("pipe") or {}).get("members", [])
            id_to_uuid = {}
            for m in members:
                u = m.get("user") if isinstance(m.get("user"), dict) else {}
                if u and "uuid" in u:
                    id_to_uuid[str(u.get("id"))] = u["uuid"]
            user_uuids = [id_to_uuid.get(str(uid), uid) for uid in user_ids]

        return await self.execute_query(
            REMOVE_MEMBERS_FROM_PIPE_MUTATION,
            {
                "input": {
                    "pipeUuid": pipe_uuid,
                    "usersUuids": user_uuids,
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
                    "pipe_id": int(pipe_id),
                    "member": {"user_id": member_id, "role_name": role_name},
                }
            },
        )
