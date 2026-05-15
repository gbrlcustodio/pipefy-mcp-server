"""Database table record subcommands."""

from __future__ import annotations

from typing import Any

import typer
from pipefy_sdk import (
    UPDATE_TABLE_RECORD_ALLOWED_FIELD_KEYS,
    UPDATE_TABLE_RECORD_FIELDS_ERROR_MESSAGE,
    PipefyClient,
)

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    parse_json_object,
    parse_json_value,
    run_cli_command,
)

record_app = typer.Typer(help="Table record operations.", no_args_is_help=True)

_TABLE_RECORDS_FIRST_MAX = 200


def _parse_fields_json(raw: str | None) -> dict[str, Any] | list[dict[str, Any]] | None:
    if raw is None or raw.strip() == "":
        return None
    parsed = parse_json_value(raw, "--fields")
    if isinstance(parsed, dict | list):
        return parsed
    raise typer.BadParameter("--fields must be a JSON object or array")


@record_app.command("find")
def record_find(
    ctx: typer.Context,
    table_id: str = typer.Option(..., "--table", help="Database table id."),
    filter_json: str | None = typer.Option(
        None,
        "--filter",
        help=(
            'JSON object: either {"field_id":"...","field_value":"..."} for findRecords, '
            "or omit field_id/field_value to page all records (get_table_records)."
        ),
    ),
    first: int | None = typer.Option(
        None,
        "--first",
        help="Page size (1-200 for listing; optional for field search).",
    ),
    after: str | None = typer.Option(None, "--after", help="Pagination cursor."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Find records: field match (``find_records``) or list page (``get_table_records``)."""

    filt = parse_json_object(filter_json, "--filter") if filter_json else {}
    has_field_id = "field_id" in filt
    has_field_value = "field_value" in filt
    if has_field_id != has_field_value:
        raise typer.BadParameter(
            "--filter must include both 'field_id' and 'field_value' as strings, or neither."
        )
    if has_field_id:
        fid = filt["field_id"]
        fval = filt["field_value"]
        if not (isinstance(fid, str) and isinstance(fval, str)):
            raise typer.BadParameter(
                "filter.field_id and filter.field_value must be strings."
            )
        nfirst = first
        if nfirst is not None and (nfirst < 1 or nfirst > _TABLE_RECORDS_FIRST_MAX):
            raise typer.BadParameter(
                f"--first must be between 1 and {_TABLE_RECORDS_FIRST_MAX}."
            )

        async def factory(client: PipefyClient):
            return await client.find_records(
                table_id,
                fid.strip(),
                fval,
                first=nfirst,
                after=after,
            )

        run_cli_command(ctx, json_out, factory)
        return

    nfirst = first if first is not None else 50
    if nfirst < 1 or nfirst > _TABLE_RECORDS_FIRST_MAX:
        raise typer.BadParameter(
            f"--first must be between 1 and {_TABLE_RECORDS_FIRST_MAX} (default 50)."
        )

    async def factory(client: PipefyClient):
        return await client.get_table_records(table_id, first=nfirst, after=after)

    run_cli_command(ctx, json_out, factory)


@record_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def record_get(
    ctx: typer.Context,
    record_id: str,
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Load one table record by id."""

    async def factory(client: PipefyClient):
        return await client.get_table_record(record_id)

    run_cli_command(ctx, json_out, factory)


@record_app.command("create")
def record_create(
    ctx: typer.Context,
    table_id: str = typer.Option(..., "--table", help="Database table id."),
    fields_json: str | None = typer.Option(
        None,
        "--fields",
        help="JSON object or array of field values for the new record.",
    ),
    title: str | None = typer.Option(None, "--title", "-t"),
    extra_json: str | None = typer.Option(
        None,
        "--extra",
        help="JSON object of extra CreateTableRecordInput keys.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Create a table record."""

    fields = _parse_fields_json(fields_json)
    extra = parse_json_object(extra_json, "--extra") or {}
    payload = fields if fields is not None else {}
    merged: dict[str, Any] = {**extra}
    if title is not None:
        merged["title"] = title

    async def factory(client: PipefyClient):
        return await client.create_table_record(table_id, payload, **merged)

    run_cli_command(ctx, json_out, factory, exit_code_2_on_value_error=True)


@record_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def record_update(
    ctx: typer.Context,
    record_id: str,
    fields_json: str | None = typer.Option(
        None,
        "--fields",
        help="JSON object: title, due_date, status_id or statusId (update_table_record).",
    ),
    field_id: str | None = typer.Option(
        None,
        "--field-id",
        help="When set with --value, calls set_table_record_field_value instead.",
    ),
    value_json: str | None = typer.Option(
        None,
        "--value",
        help="JSON value for --field-id (string, number, array, or object).",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Update record core fields or one custom field."""

    if field_id is not None:
        if not field_id.strip():
            raise typer.BadParameter("--field-id must be non-empty when provided.")
        if value_json is None:
            raise typer.BadParameter("Provide --value JSON when using --field-id.")
        parsed_val = parse_json_value(value_json, "--value")

        async def factory_set(client: PipefyClient):
            return await client.set_table_record_field_value(
                record_id, field_id.strip(), parsed_val
            )

        run_cli_command(ctx, json_out, factory_set, exit_code_2_on_value_error=True)
        return

    fields = parse_json_object(fields_json, "--fields")
    if not fields:
        raise typer.BadParameter(
            "Provide --fields for title/due_date/status or --field-id and --value."
        )
    if not any(
        key in UPDATE_TABLE_RECORD_ALLOWED_FIELD_KEYS and value is not None
        for key, value in fields.items()
    ):
        typer.echo(UPDATE_TABLE_RECORD_FIELDS_ERROR_MESSAGE, err=True)
        raise typer.Exit(2)

    async def factory(client: PipefyClient):
        return await client.update_table_record(record_id, fields)

    run_cli_command(ctx, json_out, factory, exit_code_2_on_value_error=True)


@record_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def record_delete(
    ctx: typer.Context,
    record_id: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete a table record permanently."""

    confirm_destructive(yes=yes, description=f"table record {record_id}")

    async def factory(client: PipefyClient):
        return await client.delete_table_record(record_id)

    run_cli_command(ctx, json_out, factory, exit_code_2_on_value_error=True)
