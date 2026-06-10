"""Pipe label subcommands."""

from __future__ import annotations

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    resource_id_argument,
    run_cli_command,
    validate_label_color_cli,
    validate_label_name_cli,
)

label_app = typer.Typer(help="Pipe label operations.", no_args_is_help=True)


@label_app.command("list")
def label_list(
    ctx: typer.Context,
    pipe_id: str = typer.Option(..., "--pipe", help="Pipe id."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List labels on a pipe (from ``get_pipe``); JSON shape matches MCP ``get_labels``."""

    async def factory(client: PipefyClient):
        raw = await client.get_pipe(pipe_id)
        pipe_node = (raw or {}).get("pipe")
        if pipe_node is None:
            return {"success": False, "error": "Pipe not found or access denied."}
        labels = pipe_node.get("labels")
        if labels is None:
            labels = []
        return {
            "success": True,
            "message": "Labels loaded.",
            "labels": labels,
        }

    run_cli_command(ctx, json_out, factory)


@label_app.command("create")
def label_create(
    ctx: typer.Context,
    pipe_id: str = typer.Option(..., "--pipe", help="Pipe id."),
    name: str = typer.Option(..., "--name", "-n", help="Label name."),
    color: str = typer.Option(
        ...,
        "--color",
        "-c",
        help="Label color as hex #RRGGBB (e.g. #E50000, #FF0000).",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Create a label on a pipe."""

    nm = validate_label_name_cli(name)
    col = validate_label_color_cli(color)

    async def factory(client: PipefyClient):
        return await client.create_label(pipe_id, nm, col)

    run_cli_command(ctx, json_out, factory)


@label_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def label_update(
    ctx: typer.Context,
    label_id: str = resource_id_argument(help="Label id."),
    name: str = typer.Option(
        ..., "--name", "-n", help="New label name (required by API)."
    ),
    color: str = typer.Option(
        ...,
        "--color",
        "-c",
        help="New label color as hex #RRGGBB (required by API).",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Update a label (name and color are both required by Pipefy)."""

    nm = validate_label_name_cli(name)
    col = validate_label_color_cli(color)

    async def factory(client: PipefyClient):
        return await client.update_label(label_id, name=nm, color=col)

    run_cli_command(ctx, json_out, factory)


@label_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def label_delete(
    ctx: typer.Context,
    label_id: str = resource_id_argument(help="Label id."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete a label permanently."""

    confirm_destructive(yes=yes, description=f"label {label_id}")

    async def factory(client: PipefyClient):
        return await client.delete_label(label_id)

    run_cli_command(ctx, json_out, factory)
