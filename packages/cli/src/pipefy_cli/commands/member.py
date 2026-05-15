"""Pipe member subcommands."""

from __future__ import annotations

import json
from typing import Any

import typer
from pipefy_sdk import (
    PipefyClient,
    format_service_account_removal_block_message,
    service_account_removal_blocked_user_ids,
)

from pipefy_cli.commands._common import (
    confirm_destructive,
    run_cli_command,
    settings_and_token,
)

member_app = typer.Typer(help="Pipe member operations.", no_args_is_help=True)


def _parse_members_json(raw: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON for --members: {exc}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise typer.BadParameter("--members must be a non-empty JSON array of objects.")
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise typer.BadParameter(f"--members[{i}] must be an object.")
        if "email" not in item or "role_name" not in item:
            raise typer.BadParameter(
                f"--members[{i}] must include 'email' and 'role_name'."
            )
    return parsed


def _parse_user_ids(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
    if not parts:
        raise typer.BadParameter(
            "Provide at least one user id (comma-separated or space-separated)."
        )
    return parts


@member_app.command("list")
def member_list(
    ctx: typer.Context,
    pipe_id: str = typer.Option(..., "--pipe", help="Pipe id."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List members of a pipe."""

    async def factory(client: PipefyClient):
        return await client.get_pipe_members(pipe_id)

    run_cli_command(ctx, json_out, factory)


@member_app.command("invite")
def member_invite(
    ctx: typer.Context,
    pipe_id: str = typer.Option(..., "--pipe", help="Pipe id."),
    members_json: str = typer.Option(
        ...,
        "--members",
        help='JSON array: [{"email":"a@b.com","role_name":"admin"}, ...].',
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Invite users to a pipe."""

    members = _parse_members_json(members_json)

    async def factory(client: PipefyClient):
        return await client.invite_members(pipe_id, members)

    run_cli_command(ctx, json_out, factory)


@member_app.command("remove")
def member_remove(
    ctx: typer.Context,
    pipe_id: str = typer.Option(..., "--pipe", help="Pipe id."),
    user_ids: str = typer.Option(
        ...,
        "--user-ids",
        help="Comma-separated Pipefy user ids or UUIDs to remove from the pipe.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Remove users from a pipe (same service-account guard as MCP when env is set)."""

    pipefy_settings, _token = settings_and_token(ctx)
    ids = _parse_user_ids(user_ids)
    blocked = service_account_removal_blocked_user_ids(
        ids, pipefy_settings.service_account_ids
    )
    if blocked:
        typer.echo(
            format_service_account_removal_block_message(blocked),
            err=True,
        )
        raise typer.Exit(2)

    confirm_destructive(
        yes=yes, verb="remove", description=f"{len(ids)} member(s) from pipe {pipe_id}"
    )

    async def factory(client: PipefyClient):
        return await client.remove_members_from_pipe(pipe_id, ids)

    run_cli_command(ctx, json_out, factory)


@member_app.command("set-role")
def member_set_role(
    ctx: typer.Context,
    pipe_id: str = typer.Option(..., "--pipe", help="Pipe id."),
    member_id: str = typer.Option(..., "--member", help="Member user id."),
    role_name: str = typer.Option(
        ..., "--role", help="Role name (e.g. member, admin)."
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Set a member's role on a pipe.

    When ``PIPEFY_SERVICE_ACCOUNT_IDS`` includes ``--member``, the response gains
    a ``warning`` field reminding callers to preserve write permissions on that
    account (parity with the MCP ``set_role`` tool).
    """

    rn = role_name.strip()
    if not rn:
        typer.echo("--role must be non-empty.", err=True)
        raise typer.Exit(2)

    pipefy_settings, _ = settings_and_token(ctx)
    protected_ids = pipefy_settings.service_account_ids

    async def factory(client: PipefyClient):
        raw = await client.set_role(pipe_id, member_id, rn)
        if protected_ids and member_id in protected_ids:
            return {
                "setRole": raw.get("setRole", raw) if isinstance(raw, dict) else raw,
                "warning": (
                    "Warning: you changed the role of a service account. "
                    "Ensure the new role retains write permissions."
                ),
            }
        return raw

    run_cli_command(ctx, json_out, factory)
