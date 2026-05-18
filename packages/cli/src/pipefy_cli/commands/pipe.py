"""Pipe subcommands."""

from __future__ import annotations

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    parse_json_object,
    resource_id_argument,
    run_cli_command,
)

pipe_app = typer.Typer(help="Pipe operations.", no_args_is_help=True)


@pipe_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def pipe_get(
    ctx: typer.Context,
    pipe_id: str = resource_id_argument(help="Pipe id."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Load a pipe by id (phases, labels, start form)."""

    async def factory(client: PipefyClient):
        return await client.get_pipe(pipe_id)

    run_cli_command(ctx, json_out, factory)


@pipe_app.command("list")
def pipe_list(
    ctx: typer.Context,
    name: str | None = typer.Option(
        None,
        "--name",
        "-n",
        help="Optional pipe name filter (fuzzy match server-side).",
    ),
    max_per_org: int = typer.Option(
        500,
        "--max-per-org",
        min=1,
        max=500,
        help="Maximum pipes returned per organization (1-500).",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Search pipes across organizations (same as MCP ``search_pipes``)."""

    async def factory(client: PipefyClient):
        return await client.search_pipes(name, max_pipes_per_org=max_per_org)

    run_cli_command(ctx, json_out, factory)


@pipe_app.command("create")
def pipe_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Display name for the new pipe."),
    org_id: str = typer.Option(
        ...,
        "--org",
        help="Organization id that will own the pipe.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Create an empty pipe in an organization."""

    stripped = name.strip()
    if not stripped:
        typer.echo("Pipe name must be non-empty.", err=True)
        raise typer.Exit(2)

    async def factory(client: PipefyClient):
        return await client.create_pipe(stripped, org_id)

    run_cli_command(ctx, json_out, factory)


@pipe_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def pipe_update(
    ctx: typer.Context,
    pipe_id: str = resource_id_argument(help="Pipe id."),
    name: str | None = typer.Option(None, "--name"),
    icon: str | None = typer.Option(None, "--icon"),
    color: str | None = typer.Option(None, "--color"),
    preferences_json: str | None = typer.Option(
        None,
        "--preferences",
        help="JSON object for pipe preferences (UpdatePipeInput).",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Update pipe settings (pass at least one attribute)."""

    preferences = parse_json_object(preferences_json, "--preferences")
    if preferences == {}:
        preferences = None
    if all(x is None for x in (name, icon, color, preferences)):
        raise typer.BadParameter(
            "Provide at least one of: --name, --icon, --color, --preferences (non-empty)."
        )

    async def factory(client: PipefyClient):
        return await client.update_pipe(
            pipe_id,
            name=name,
            icon=icon,
            color=color,
            preferences=preferences,
        )

    run_cli_command(ctx, json_out, factory)


@pipe_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def pipe_delete(
    ctx: typer.Context,
    pipe_id: str = resource_id_argument(help="Pipe id."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete a pipe permanently."""

    confirm_destructive(yes=yes, description=f"pipe {pipe_id}")

    async def factory(client: PipefyClient):
        return await client.delete_pipe(pipe_id)

    run_cli_command(ctx, json_out, factory)


@pipe_app.command("clone", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def pipe_clone(
    ctx: typer.Context,
    template_pipe_id: str = resource_id_argument(
        help="Source pipe id to use as template.",
    ),
    org_id: str | None = typer.Option(
        None,
        "--org",
        help="Optional organization id for the cloned pipe.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Clone a pipe from a template pipe id."""

    async def factory(client: PipefyClient):
        return await client.clone_pipe(
            template_pipe_id,
            organization_id=org_id,
        )

    run_cli_command(ctx, json_out, factory)
