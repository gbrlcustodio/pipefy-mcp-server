"""Database table subcommands."""

from __future__ import annotations

from typing import Any

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    parse_json_object,
    resource_id_argument,
    run_cli_command,
)

table_app = typer.Typer(help="Database table operations.", no_args_is_help=True)
table_field_app = typer.Typer(
    help=(
        "Table field (column) operations. For pipe phase fields, use `pipefy field`."
    ),
    no_args_is_help=True,
)


@table_app.command("list")
def table_list(
    ctx: typer.Context,
    ids: str | None = typer.Option(
        None,
        "--ids",
        help="Comma-separated table ids; when set, loads those tables via get_tables.",
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        "-n",
        help="Optional table name filter (ignored when --ids is set).",
    ),
    first: int = typer.Option(
        100,
        "--first",
        min=1,
        max=500,
        help="Max tables per organization when searching (1-500, default 100).",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Search tables across organizations, or fetch specific tables by id."""

    id_list: list[str] | None = None
    if ids is not None and ids.strip():
        id_list = [p.strip() for p in ids.split(",") if p.strip()]
        if not id_list:
            raise typer.BadParameter("--ids must list at least one table id.")

    async def factory(client: PipefyClient):
        if id_list is not None:
            return await client.get_tables(id_list)
        return await client.search_tables(name, first=first)

    run_cli_command(ctx, json_out, factory)


@table_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def table_get(
    ctx: typer.Context,
    table_id: str = resource_id_argument(help="Table id."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Load one table by id."""

    async def factory(client: PipefyClient):
        return await client.get_table(table_id)

    run_cli_command(ctx, json_out, factory)


@table_app.command("create")
def table_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Table display name."),
    org_id: str = typer.Option(
        ...,
        "--org",
        help="Organization id that will own the table.",
    ),
    extra_json: str | None = typer.Option(
        None,
        "--extra",
        help="JSON object of extra CreateTableInput fields.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Create a database table."""

    stripped = name.strip()
    if not stripped:
        typer.echo("Table name must be non-empty.", err=True)
        raise typer.Exit(2)
    extra = parse_json_object(extra_json, "--extra") or {}

    async def factory(client: PipefyClient):
        return await client.create_table(stripped, org_id, **extra)

    run_cli_command(ctx, json_out, factory)


@table_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def table_update(
    ctx: typer.Context,
    table_id: str = resource_id_argument(help="Table id."),
    name: str | None = typer.Option(None, "--name"),
    description: str | None = typer.Option(None, "--description", "-d"),
    extra_json: str | None = typer.Option(
        None,
        "--extra",
        help="JSON object merged into UpdateTableInput.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Update table attributes."""

    extra = parse_json_object(extra_json, "--extra") or {}
    attrs: dict[str, Any] = {}
    if name is not None:
        attrs["name"] = name
    if description is not None:
        attrs["description"] = description
    attrs.update(extra)
    if not attrs:
        raise typer.BadParameter(
            "Provide at least one of: --name, --description, --extra (non-empty)."
        )

    async def factory(client: PipefyClient):
        return await client.update_table(table_id, **attrs)

    run_cli_command(ctx, json_out, factory)


@table_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def table_delete(
    ctx: typer.Context,
    table_id: str = resource_id_argument(help="Table id."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete a database table permanently."""

    confirm_destructive(yes=yes, description=f"table {table_id}")

    async def factory(client: PipefyClient):
        return await client.delete_table(table_id)

    run_cli_command(ctx, json_out, factory)


@table_field_app.command("create", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def table_field_create(
    ctx: typer.Context,
    table_id: str = resource_id_argument(help="Table id."),
    label: str = typer.Option(..., "--label", "-l", help="Field label in the UI."),
    field_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Pipefy field type (e.g. short_text, phone).",
    ),
    extra_json: str | None = typer.Option(
        None,
        "--extra",
        help="JSON object of extra CreateTableFieldInput fields.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Create a field (column) on a database table."""

    extra = parse_json_object(extra_json, "--extra") or {}
    lab = label.strip()
    ft = field_type.strip()
    if not lab or not ft:
        typer.echo("--label and --type must be non-empty.", err=True)
        raise typer.Exit(2)

    async def factory(client: PipefyClient):
        return await client.create_table_field(table_id, lab, ft, **extra)

    run_cli_command(ctx, json_out, factory)


@table_field_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def table_field_update(
    ctx: typer.Context,
    field_id: str = resource_id_argument(help="Table field id."),
    table: str | None = typer.Option(
        None,
        "--table",
        help="Table id containing this field (recommended; required by API).",
    ),
    label: str | None = typer.Option(None, "--label", "-l", help="New field label."),
    extra_json: str | None = typer.Option(
        None,
        "--extra",
        help="JSON object merged into UpdateTableFieldInput.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Update a database table field (column)."""

    extra = parse_json_object(extra_json, "--extra") or {}
    attrs: dict[str, Any] = {}
    if label is not None:
        attrs["label"] = label
    attrs.update(extra)
    if not attrs:
        raise typer.BadParameter(
            "Provide at least one of: --label, --extra (non-empty)."
        )

    async def factory(client: PipefyClient):
        return await client.update_table_field(field_id, table_id=table, **attrs)

    run_cli_command(ctx, json_out, factory)


@table_field_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def table_field_delete(
    ctx: typer.Context,
    field_id: str = resource_id_argument(help="Table field id."),
    table: str = typer.Option(..., "--table", help="Table id containing this field."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete a database table field (column) permanently."""

    confirm_destructive(yes=yes, description=f"table field {field_id}")

    async def factory(client: PipefyClient):
        return await client.delete_table_field(field_id, table)

    run_cli_command(ctx, json_out, factory)


table_app.add_typer(table_field_app, name="field")
