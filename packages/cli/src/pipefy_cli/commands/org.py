"""Organization metadata (read-only)."""

from __future__ import annotations

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import run_cli_command

org_app = typer.Typer(help="Organization operations.", no_args_is_help=True)


@org_app.command("get")
def org_get(
    ctx: typer.Context,
    organization_id: str = typer.Argument(..., help="Numeric organization id."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Fetch organization details (``get_organization``)."""

    async def factory(client: PipefyClient):
        return await client.get_organization(organization_id)

    run_cli_command(ctx, json_out, factory)
