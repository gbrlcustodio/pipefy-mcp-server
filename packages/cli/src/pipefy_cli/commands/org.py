"""Organization metadata (read-only)."""

from __future__ import annotations

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    resource_id_argument,
    run_cli_command,
)

org_app = typer.Typer(help="Organization operations.", no_args_is_help=True)


@org_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def org_get(
    ctx: typer.Context,
    organization_id: str = resource_id_argument(help="Numeric organization id."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Fetch organization details (``get_organization``)."""

    async def factory(client: PipefyClient):
        return await client.get_organization(organization_id)

    run_cli_command(ctx, json_out, factory)
