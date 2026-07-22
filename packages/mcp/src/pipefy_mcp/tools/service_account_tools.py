"""MCP tools for organization service accounts (create, delete).

Secrets contract: ``create_service_account`` returns the OAuth2 client secret and
token endpoint ONCE — there is no query to read them back. The tool therefore
returns them to the caller (they are needed to authenticate as the account) but
never logs them, and the toolset is excluded from the remote profile (org-level
provisioning is not a hosted, per-request operation).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from pipefy_mcp.core.tool_error_envelope import tool_error, tool_success
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.graphql_error_helpers import handle_tool_graphql_error
from pipefy_mcp.tools.member_tool_helpers import service_account_is_member
from pipefy_mcp.tools.tool_context import get_pipefy_client

_SA_NAME_MAX = 20
_EXPIRATION_UNITS = frozenset({"seconds", "minutes", "hours", "days"})


class ServiceAccountTools:
    """MCP tools for creating and deleting organization service accounts."""

    @staticmethod
    def register(mcp: FastMCP) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_service_account(
            organization_uuid: str,
            name: str,
            role: str,
            ctx: Context,
            description: str | None = None,
            expiration_unit: str | None = None,
            expiration_value: int | None = None,
            pipe_ids: list[str] | None = None,
            pipe_role: str = "admin",
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create an organization service account (an OAuth2 machine identity).

            Use this to provision a service account for integrations — e.g. the
            iPaaS (Advanced Automations) setup flow. The response includes the
            account's OAuth2 **client id and client secret** plus the **token
            endpoint**; mint access tokens with the client-credentials grant.

            IMPORTANT: the client secret is returned only once, here — there is
            no way to read it back later. Store it securely immediately.

            A freshly created account has NO pipe access. Pass `pipe_ids` to add
            it to those pipes (with `pipe_role`) right after creation — the
            response then carries a `pipe_memberships` list, one entry per pipe
            with its invite outcome and a verified `member` flag. Omit `pipe_ids`
            and add it later with `add_service_account_to_pipe`.

            Args:
                organization_uuid: The organization UUID (from `get_organization`).
                name: Service account name (max 20 characters).
                role: Organization role: 'admin', 'normal', 'company_guest', or
                    'external_guest'.
                description: Optional description.
                expiration_unit: Optional token-lifetime unit paired with
                    `expiration_value`: 'seconds', 'minutes', 'hours', or 'days'.
                expiration_value: Optional positive token lifetime (with
                    `expiration_unit`).
                pipe_ids: Optional pipes to add the new account to immediately.
                pipe_role: Pipe role to grant on `pipe_ids` (default 'admin').
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            client = get_pipefy_client(ctx)
            if not isinstance(organization_uuid, str) or not organization_uuid.strip():
                return tool_error(
                    "Invalid 'organization_uuid': provide the organization UUID.",
                    code="INVALID_ARGUMENTS",
                )
            if not isinstance(name, str) or not name.strip():
                return tool_error(
                    "Invalid 'name': provide a non-empty service account name.",
                    code="INVALID_ARGUMENTS",
                )
            name = name.strip()
            if len(name) > _SA_NAME_MAX:
                return tool_error(
                    f"Invalid 'name': must be at most {_SA_NAME_MAX} characters.",
                    code="INVALID_ARGUMENTS",
                )
            if not isinstance(role, str) or not role.strip():
                return tool_error(
                    "Invalid 'role': provide an organization role.",
                    code="INVALID_ARGUMENTS",
                )
            expiration, err = _build_expiration(expiration_unit, expiration_value)
            if err is not None:
                return err
            if pipe_ids is not None:
                if not isinstance(pipe_ids, list) or not all(
                    isinstance(p, str) and p.strip() for p in pipe_ids
                ):
                    return tool_error(
                        "Invalid 'pipe_ids': provide a list of non-empty pipe IDs.",
                        code="INVALID_ARGUMENTS",
                    )
                if not isinstance(pipe_role, str) or not pipe_role.strip():
                    return tool_error(
                        "Invalid 'pipe_role': provide a non-empty pipe role.",
                        code="INVALID_ARGUMENTS",
                    )
            clean_pipe_ids = (
                [p.strip() for p in pipe_ids] if pipe_ids is not None else None
            )
            try:
                raw = await client.create_service_account(
                    organization_uuid=organization_uuid.strip(),
                    name=name,
                    role=role.strip(),
                    description=description,
                    expiration=expiration,
                    pipe_ids=clean_pipe_ids,
                    pipe_role=pipe_role.strip(),
                )
            except Exception as exc:  # noqa: BLE001
                return handle_tool_graphql_error(
                    exc,
                    "Create service account failed.",
                    debug=debug,
                )
            account = (raw or {}).get("createServiceAccount") or {}
            data: dict[str, Any] = dict(account)
            memberships = raw.get("pipe_memberships")
            if memberships is not None:
                email = (account.get("serviceAccount") or {}).get("email")
                for entry in memberships:
                    entry["member"] = (
                        await service_account_is_member(client, entry["pipe_id"], email)
                        if email
                        else None
                    )
                data["pipe_memberships"] = memberships
            return tool_success(
                data=data,
                message=(
                    "Service account created. Store the client secret and token "
                    "endpoint now — they are shown only once."
                    + (
                        " Review 'pipe_memberships' to confirm pipe access."
                        if memberships is not None
                        else " Add the account to each target pipe with "
                        "add_service_account_to_pipe before use."
                    )
                ),
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_service_account(
            ctx: Context[ServerSession, None],
            organization_uuid: str,
            service_account_uuid: str,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Permanently delete an organization service account.

            Two-step operation: preview with ``confirm=False`` (default), then
            execute with ``confirm=True`` after explicit human approval. Deleting
            the account revokes its credentials — any integration using it stops
            working.

            Args:
                organization_uuid: The organization UUID.
                service_account_uuid: The service account UUID (from
                    `create_service_account`).
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            client = get_pipefy_client(ctx)
            if not isinstance(organization_uuid, str) or not organization_uuid.strip():
                return tool_error(
                    "Invalid 'organization_uuid': provide the organization UUID.",
                    code="INVALID_ARGUMENTS",
                )
            if (
                not isinstance(service_account_uuid, str)
                or not service_account_uuid.strip()
            ):
                return tool_error(
                    "Invalid 'service_account_uuid': provide the service account UUID.",
                    code="INVALID_ARGUMENTS",
                )

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"service account {service_account_uuid.strip()}",
            )
            if guard is not None:
                return guard

            try:
                raw = await client.delete_service_account(
                    organization_uuid=organization_uuid.strip(),
                    service_account_uuid=service_account_uuid.strip(),
                )
            except Exception as exc:  # noqa: BLE001
                return handle_tool_graphql_error(
                    exc,
                    "Delete service account failed.",
                    debug=debug,
                )
            return tool_success(
                data=(raw or {}).get("deleteServiceAccount") or {},
                message="Service account deleted.",
            )


def _build_expiration(
    unit: str | None, value: int | None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Validate the optional expiration pair into ``{unit, value}`` or an error.

    Returns ``(expiration, None)`` when valid (``(None, None)`` when omitted) or
    ``(None, error_payload)`` on a bad pair.
    """
    if unit is None and value is None:
        return None, None
    if unit is None or value is None:
        return None, tool_error(
            "Invalid expiration: provide both 'expiration_unit' and 'expiration_value'.",
            code="INVALID_ARGUMENTS",
        )
    if unit not in _EXPIRATION_UNITS:
        return None, tool_error(
            "Invalid 'expiration_unit': use 'seconds', 'minutes', 'hours', or 'days'.",
            code="INVALID_ARGUMENTS",
        )
    if value <= 0:
        return None, tool_error(
            "Invalid 'expiration_value': provide a positive integer.",
            code="INVALID_ARGUMENTS",
        )
    return {"unit": unit, "value": value}, None
