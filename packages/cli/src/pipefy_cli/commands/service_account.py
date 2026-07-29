"""Organization service-account subcommands (create, delete)."""

from __future__ import annotations

from typing import Any

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    confirm_destructive,
    run_cli_command,
)

service_account_app = typer.Typer(
    help="Organization service account operations.", no_args_is_help=True
)

_NAME_MAX = 20
_EXPIRATION_UNITS = {"seconds", "minutes", "hours", "days"}


def _missing_secret_failure(account_uuid: Any) -> dict[str, Any]:
    """Fail closed when the create payload reports success but carries no secret.

    The account may still exist while its one-shot credentials reached nobody, so
    the uuid is surfaced for cleanup. Nothing else from the payload is echoed.
    """
    uuid_text = account_uuid.strip() if isinstance(account_uuid, str) else ""
    if not uuid_text:
        return {
            "success": False,
            "error": (
                "Create service account returned no client secret and no account "
                "UUID. The secret cannot be read back, and there is no API or "
                "command to list organization service accounts. Do not retry create "
                "until a human confirms in org settings whether a stray account was "
                "created."
            ),
        }
    return {
        "success": False,
        "error": (
            "Create service account returned no client secret. The secret cannot "
            f"be read back, so the account (UUID: {uuid_text}) is unusable - delete "
            "it with `pipefy service-account delete`, then retry."
        ),
        "service_account_uuid": uuid_text,
    }


@service_account_app.command("create")
def service_account_create(
    ctx: typer.Context,
    organization_uuid: str = typer.Option(..., "--org", help="Organization UUID."),
    name: str = typer.Option(..., "--name", help="Service account name (<=20 chars)."),
    role: str = typer.Option(
        "normal",
        "--role",
        help="Org role (admin, normal, company_guest, external_guest).",
    ),
    description: str = typer.Option(
        None, "--description", help="Optional description."
    ),
    expiration_unit: str = typer.Option(
        None,
        "--expiration-unit",
        help="Token lifetime unit (seconds/minutes/hours/days).",
    ),
    expiration_value: int = typer.Option(
        None, "--expiration-value", help="Token lifetime value (positive int)."
    ),
    pipe_ids: str = typer.Option(
        None,
        "--pipe-ids",
        help="Comma-separated pipe IDs to add the new account to immediately.",
    ),
    pipe_role: str = typer.Option(
        "admin", "--pipe-role", help="Pipe role for --pipe-ids (default admin)."
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Create an org service account. Prints the client secret once — store it now."""

    nm = name.strip()
    if not nm:
        typer.echo("--name must be non-empty.", err=True)
        raise typer.Exit(2)
    if len(nm) > _NAME_MAX:
        typer.echo(f"--name must be at most {_NAME_MAX} characters.", err=True)
        raise typer.Exit(2)
    rn = role.strip()
    if not rn:
        typer.echo("--role must be non-empty.", err=True)
        raise typer.Exit(2)
    if (expiration_unit is None) != (expiration_value is None):
        typer.echo(
            "--expiration-unit and --expiration-value must be given together.", err=True
        )
        raise typer.Exit(2)
    expiration = None
    if expiration_unit is not None:
        if expiration_unit not in _EXPIRATION_UNITS:
            typer.echo(
                "--expiration-unit must be seconds, minutes, hours, or days.", err=True
            )
            raise typer.Exit(2)
        if expiration_value <= 0:
            typer.echo("--expiration-value must be a positive integer.", err=True)
            raise typer.Exit(2)
        expiration = {"unit": expiration_unit, "value": expiration_value}
    pr = pipe_role.strip()
    ids = None
    if pipe_ids is not None:
        ids = [p.strip() for p in pipe_ids.replace(",", " ").split() if p.strip()]
        if not ids:
            typer.echo("--pipe-ids must contain at least one pipe id.", err=True)
            raise typer.Exit(2)
        if not pr:
            typer.echo("--pipe-role must be non-empty.", err=True)
            raise typer.Exit(2)

    async def factory(client: PipefyClient):
        result = await client.create_service_account(
            organization_uuid=organization_uuid,
            name=nm,
            role=rn,
            description=description,
            expiration=expiration,
            pipe_ids=ids,
            pipe_role=pr,
        )
        node = (result or {}).get("createServiceAccount") or {}
        if not node.get("success"):
            # A failed create can still carry the one-shot secret; never echo it.
            return {
                "success": False,
                "error": "Create service account did not succeed.",
            }
        account = node.get("serviceAccount") or {}
        if not (account.get("client") or {}).get("secret"):
            return _missing_secret_failure(account.get("uuid"))
        return {"success": True, **result}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@service_account_app.command("delete")
def service_account_delete(
    ctx: typer.Context,
    organization_uuid: str = typer.Option(..., "--org", help="Organization UUID."),
    service_account_uuid: str = typer.Option(..., "--id", help="Service account UUID."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Permanently delete an org service account (revokes its credentials)."""

    sa_uuid = service_account_uuid.strip()
    if not sa_uuid:
        typer.echo("--id must be non-empty.", err=True)
        raise typer.Exit(2)

    confirm_destructive(
        yes=yes, verb="delete", description=f"service account {sa_uuid}"
    )

    async def factory(client: PipefyClient):
        result = await client.delete_service_account(
            organization_uuid=organization_uuid,
            service_account_uuid=sa_uuid,
        )
        node = (result or {}).get("deleteServiceAccount") or {}
        if not node.get("success"):
            return {
                "success": False,
                "error": "Delete service account did not succeed.",
                "service_account_uuid": sa_uuid,
            }
        return {"success": True, **result}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)
