"""Pipe and card relation subcommands."""

from __future__ import annotations

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    authenticated_client_from_ctx,
    confirm_destructive,
    parse_json_object,
    resource_id_argument,
    run_cli_command,
)

relation_app = typer.Typer(help="Pipe and card relations.", no_args_is_help=True)
relation_pipe_app = typer.Typer(help="Pipe-to-pipe relations.", no_args_is_help=True)
relation_card_app = typer.Typer(help="Card-to-card relations.", no_args_is_help=True)


@relation_pipe_app.command("list", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def relation_pipe_list(
    ctx: typer.Context,
    pipe_id: str = resource_id_argument(help="Pipe id."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List pipe relations for a pipe."""

    async def factory(client: PipefyClient):
        return await client.get_pipe_relations(pipe_id)

    run_cli_command(ctx, json_out, factory)


@relation_pipe_app.command("create")
def relation_pipe_create(
    ctx: typer.Context,
    parent_id: str = typer.Option(..., "--parent", help="Parent pipe id."),
    child_id: str = typer.Option(..., "--child", help="Child pipe id."),
    name: str = typer.Option(..., "--name", "-n", help="Relation name."),
    extra_json: str | None = typer.Option(
        None,
        "--extra",
        help="JSON object merged into CreatePipeRelationInput.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Create a pipe relation."""

    nm = name.strip()
    if not nm:
        typer.echo("--name must be non-empty.", err=True)
        raise typer.Exit(2)
    extra = parse_json_object(extra_json, "--extra")

    async def factory(client: PipefyClient):
        return await client.create_pipe_relation(
            parent_id, child_id, nm, extra_input=extra
        )

    run_cli_command(ctx, json_out, factory)


@relation_pipe_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def relation_pipe_update(
    ctx: typer.Context,
    relation_id: str = resource_id_argument(help="Pipe relation id."),
    name: str = typer.Option(..., "--name", "-n", help="New relation name."),
    extra_json: str | None = typer.Option(
        None,
        "--extra",
        help="JSON object merged into UpdatePipeRelationInput.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Update a pipe relation."""

    nm = name.strip()
    if not nm:
        typer.echo("--name must be non-empty.", err=True)
        raise typer.Exit(2)
    extra = parse_json_object(extra_json, "--extra")

    async def factory(client: PipefyClient):
        return await client.update_pipe_relation(relation_id, nm, extra_input=extra)

    run_cli_command(ctx, json_out, factory)


@relation_pipe_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def relation_pipe_delete(
    ctx: typer.Context,
    relation_id: str = resource_id_argument(help="Pipe relation id."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete a pipe relation permanently."""

    confirm_destructive(yes=yes, description=f"pipe relation {relation_id}")

    async def factory(client: PipefyClient):
        return await client.delete_pipe_relation(relation_id)

    run_cli_command(ctx, json_out, factory)


@relation_card_app.command("list", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def relation_card_list(
    ctx: typer.Context,
    card_id: str = resource_id_argument(help="Card id."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List parent and child relations for a card (raw ``get_card_relations`` payload)."""

    async def factory(client: PipefyClient):
        return await client.get_card_relations(card_id)

    run_cli_command(ctx, json_out, factory)


@relation_card_app.command("create")
def relation_card_create(
    ctx: typer.Context,
    parent_id: str = typer.Option(..., "--parent", help="Parent card id."),
    child_id: str = typer.Option(..., "--child", help="Child card id."),
    source_id: str = typer.Option(
        ...,
        "--source",
        help="Pipe relation id from ``relation pipe list``.",
    ),
    extra_json: str | None = typer.Option(
        None,
        "--extra",
        help="JSON object merged into CreateCardRelationInput.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Link two cards via an existing pipe relation."""

    extra = parse_json_object(extra_json, "--extra")

    async def factory(client: PipefyClient):
        return await client.create_card_relation(
            parent_id, child_id, source_id, extra_input=extra
        )

    run_cli_command(ctx, json_out, factory)


@relation_card_app.command("delete")
def relation_card_delete(
    ctx: typer.Context,
    child_id: str = typer.Option(..., "--child", help="Child card id."),
    parent_id: str = typer.Option(..., "--parent", help="Parent card id."),
    source_id: str = typer.Option(..., "--source", help="Pipe relation id."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Remove a card relation (requires service-account credentials; internal API)."""

    client = authenticated_client_from_ctx(ctx)
    if not client.internal_api_available:
        typer.echo(
            "delete_card_relation requires service-account credentials "
            "(PIPEFY_SERVICE_ACCOUNT_URL, PIPEFY_SERVICE_ACCOUNT_CLIENT_ID, "
            "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET). "
            "The deleteCardRelation mutation is only available on the internal API.",
            err=True,
        )
        raise typer.Exit(2)

    confirm_destructive(
        yes=yes,
        description=f"card relation (child={child_id}, parent={parent_id}, source={source_id})",
    )

    async def factory(c: PipefyClient):
        return await c.delete_card_relation(child_id, parent_id, source_id)

    run_cli_command(ctx, json_out, factory)


relation_app.add_typer(relation_pipe_app, name="pipe")
relation_app.add_typer(relation_card_app, name="card")
