"""Phase field subcommands."""

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

field_app = typer.Typer(help="Phase field operations.", no_args_is_help=True)


@field_app.command("list")
def field_list(
    ctx: typer.Context,
    phase_id: str = typer.Option(..., "--phase", help="Phase id."),
    required_only: bool = typer.Option(
        False,
        "--required-only",
        help="Return only required fields.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List fields on a phase (``get_phase_fields``)."""

    async def factory(client: PipefyClient):
        return await client.get_phase_fields(phase_id, required_only=required_only)

    run_cli_command(ctx, json_out, factory)


@field_app.command("create")
def field_create(
    ctx: typer.Context,
    phase_id: str = typer.Option(..., "--phase", help="Phase id."),
    label: str = typer.Option(..., "--label", "-l", help="Field label in the UI."),
    field_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Pipefy field type (e.g. short_text, number).",
    ),
    extra_json: str | None = typer.Option(
        None,
        "--extra",
        help="JSON object of extra CreatePhaseFieldInput fields.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Create a field on a phase."""

    extra = parse_json_object(extra_json, "--extra") or {}
    lab = label.strip()
    ft = field_type.strip()
    if not lab or not ft:
        typer.echo("--label and --type must be non-empty.", err=True)
        raise typer.Exit(2)

    async def factory(client: PipefyClient):
        return await client.create_phase_field(phase_id, lab, ft, **extra)

    run_cli_command(ctx, json_out, factory)


@field_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def field_update(
    ctx: typer.Context,
    field_id: str = resource_id_argument(help="Phase field id."),
    extra_json: str | None = typer.Option(
        None,
        "--extra",
        help="JSON object of UpdatePhaseFieldInput fields (snake_case / API keys).",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Update a phase field (pass attributes via ``--extra`` JSON)."""

    extra = parse_json_object(extra_json, "--extra")
    if not extra:
        raise typer.BadParameter("Provide --extra with a non-empty JSON object.")

    async def factory(client: PipefyClient):
        return await client.update_phase_field(field_id, **extra)

    run_cli_command(ctx, json_out, factory)


@field_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def field_delete(
    ctx: typer.Context,
    field_id: str = resource_id_argument(help="Phase field id."),
    pipe_uuid: str | None = typer.Option(
        None,
        "--pipe-uuid",
        help="Optional pipe UUID (passed through to the API when required).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete a phase field permanently."""

    confirm_destructive(yes=yes, description=f"phase field {field_id}")

    async def factory(client: PipefyClient):
        return await client.delete_phase_field(field_id, pipe_uuid=pipe_uuid)

    run_cli_command(ctx, json_out, factory)
