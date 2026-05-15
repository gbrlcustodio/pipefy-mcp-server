"""GraphQL operations for pipe member management (invite, remove, set role)."""

from __future__ import annotations

import re
from typing import Any

from httpx import Auth
from pydantic import ValidationError

from pipefy_sdk.base_client import BasePipefyClient
from pipefy_sdk.models.member_invite import MemberInvite
from pipefy_sdk.queries.member_queries import (
    INVITE_MEMBERS_MUTATION,
    REMOVE_MEMBERS_FROM_PIPE_MUTATION,
    SET_ROLE_MUTATION,
)
from pipefy_sdk.services.pipe_service import PipeService
from pipefy_sdk.settings import PipefySettings

_PIPE_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _format_member_invite_error(index: int, exc: ValidationError) -> str:
    """Compact one-line message for a single ``MemberInvite`` row failure."""
    first = next(iter(exc.errors()), None)
    if first is None:
        return f"Invalid members[{index}]: validation error."
    loc = ".".join(str(p) for p in first.get("loc", ())) or "row"
    detail = first.get("msg", "validation error")
    return f"Invalid members[{index}].{loc}: {detail}"


class MemberService(BasePipefyClient):
    """Invite, remove, and set roles for pipe members."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: Auth | None = None,
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
        validated: list[dict[str, str]] = []
        for i, row in enumerate(members):
            try:
                inv = MemberInvite.model_validate(row)
            except ValidationError as exc:
                raise ValueError(_format_member_invite_error(i, exc)) from exc
            validated.append(
                {"email": str(inv.email), "role_name": inv.role_name.strip()}
            )
        return await self.execute_query(
            INVITE_MEMBERS_MUTATION,
            {"input": {"pipe_id": str(pipe_id), "emails": validated}},
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
            pipe_data = await self._pipe_service.get_pipe(pipe_id_str)
            pipe_obj = pipe_data.get("pipe") or {}
        elif _PIPE_UUID_RE.match(pipe_id_str):
            raise ValueError(
                f"pipe_id must be a numeric pipe ID, not a UUID ({pipe_id_str}). "
                "Use the numeric pipe ID from get_pipe instead."
            )
        else:
            raise ValueError(f"pipe_id must be a numeric pipe ID, got {pipe_id!r}.")

        pipe_uuid = pipe_obj.get("uuid") or pipe_id_str
        pipe_numeric_id = pipe_obj.get("id")

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
                    "pipe_id": str(pipe_id),
                    "member": {"user_id": member_id, "role_name": role_name},
                }
            },
        )


def service_account_removal_blocked_user_ids(
    user_ids: list[str],
    protected_ids: list[str],
) -> list[str]:
    """Return user ids that cannot be removed because they appear in ``protected_ids``.

    Args:
        user_ids: Candidate user IDs to remove from a pipe.
        protected_ids: Service account IDs from settings (e.g. ``PIPEFY_SERVICE_ACCOUNT_IDS``).
    """
    if not protected_ids:
        return []
    protected_set = set(protected_ids)
    return [uid for uid in user_ids if uid.strip() in protected_set]


def format_service_account_removal_block_message(blocked: list[str]) -> str:
    """Format the user-facing error when removal targets protected service accounts.

    Args:
        blocked: Non-empty list of user ids that matched the protected set.
    """
    if len(blocked) == 1:
        return (
            f"Cannot remove service account {blocked[0]} - "
            "this would break all write operations for this pipe. "
            "Remove it via the Pipefy UI if intentional."
        )
    return (
        f"Cannot remove service accounts {', '.join(blocked)} - "
        "this would break all write operations for this pipe. "
        "Remove it via the Pipefy UI if intentional."
    )
