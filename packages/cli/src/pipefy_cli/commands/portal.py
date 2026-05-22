"""Portal read subcommands."""

from __future__ import annotations

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    resource_id_argument,
    run_cli_command,
)

portal_app = typer.Typer(help="Portal operations.", no_args_is_help=True)


@portal_app.command("list")
def portal_list(
    ctx: typer.Context,
    organization_uuid: str = typer.Option(
        ...,
        "--organization-uuid",
        help="Organization UUID, or numeric organization id (string).",
    ),
    search_term: str | None = typer.Option(
        None,
        "--search-term",
        help="Optional portal name filter.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """List portals for an organization."""

    async def factory(client: PipefyClient):
        return await client.list_portals(organization_uuid, search_term=search_term)

    run_cli_command(ctx, json_out, factory)


@portal_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def portal_get(
    ctx: typer.Context,
    portal_uuid: str = resource_id_argument(help="Portal UUID."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Fetch a portal by UUID."""

    async def factory(client: PipefyClient):
        return await client.get_portal(portal_uuid)

    run_cli_command(ctx, json_out, factory)
