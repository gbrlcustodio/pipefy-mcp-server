"""Pipe-level reports (CRUD, columns, export)."""

from __future__ import annotations

from typing import Any

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    parse_json_object,
    parse_json_value,
    resource_id_argument,
    run_cli_command,
    run_pipefy_client_coroutine,
    validate_report_filter_cli,
    write_export_csv_to_stdout,
)

report_pipe_app = typer.Typer(help="Pipe reports.", no_args_is_help=True)


def _parse_order(raw: str | None) -> dict[str, Any] | None:
    if raw is None or not raw.strip():
        return None
    parsed = parse_json_value(raw, "--order")
    if not isinstance(parsed, dict):
        raise typer.BadParameter("--order must be a JSON object")
    return parsed


@report_pipe_app.command("list")
def report_pipe_list(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Pipe UUID."),
    first: int = typer.Option(30, "--first", help="Page size."),
    after: str | None = typer.Option(None, "--after", help="Pagination cursor."),
    search: str | None = typer.Option(None, "--search"),
    report_id: str | None = typer.Option(None, "--report-id"),
    order: str | None = typer.Option(None, "--order", help="JSON sort object."),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """List pipe reports (``get_pipe_reports``)."""
    order_obj = _parse_order(order)

    async def factory(client: PipefyClient):
        return await client.get_pipe_reports(
            pipe,
            first=first,
            after=after,
            search=search,
            report_id=report_id,
            order=order_obj,
        )

    run_cli_command(ctx, json_out, factory)


@report_pipe_app.command("get")
def report_pipe_get(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Pipe UUID."),
    report_id: str = typer.Option(..., "--report-id", help="Pipe report id."),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Fetch one pipe report (``get_pipe_report``)."""

    async def factory(client: PipefyClient):
        raw = await client.get_pipe_reports(pipe, first=1, report_id=report_id)
        edges = (raw.get("pipeReports") or {}).get("edges") or []
        node = edges[0].get("node") if edges and isinstance(edges[0], dict) else None
        if not node:
            return {
                "success": False,
                "message": f"Pipe report not found (id={report_id}).",
            }
        return {"success": True, "pipeReport": node}

    run_cli_command(ctx, json_out, factory)


@report_pipe_app.command("columns")
def report_pipe_columns(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Pipe UUID."),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """List report column definitions (``get_pipe_report_columns``)."""

    async def factory(client: PipefyClient):
        return await client.get_pipe_report_columns(pipe)

    run_cli_command(ctx, json_out, factory)


@report_pipe_app.command("filterable-fields")
def report_pipe_filterable_fields(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Pipe UUID."),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """List filterable fields for pipe reports (``get_pipe_report_filterable_fields``)."""

    async def factory(client: PipefyClient):
        return await client.get_pipe_report_filterable_fields(pipe)

    run_cli_command(ctx, json_out, factory)


@report_pipe_app.command("create")
def report_pipe_create(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Pipe id."),
    name: str = typer.Option(..., "--name", "-n"),
    fields: str | None = typer.Option(
        None, "--fields", help="Optional JSON array of column internal names."
    ),
    filter_json: str | None = typer.Option(
        None, "--filter", help="Optional JSON filter object."
    ),
    formulas: str | None = typer.Option(
        None, "--formulas", help="Optional JSON array of arrays."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Create a pipe report (``create_pipe_report``)."""
    fields_list = parse_json_value(fields, "--fields") if fields else None
    if fields_list is not None and not isinstance(fields_list, list):
        raise typer.BadParameter("--fields must be a JSON array")
    filt = validate_report_filter_cli(parse_json_object(filter_json, "--filter"))
    formulas_val = parse_json_value(formulas, "--formulas") if formulas else None
    if formulas_val is not None and not isinstance(formulas_val, list):
        raise typer.BadParameter("--formulas must be a JSON array")

    async def factory(client: PipefyClient):
        return await client.create_pipe_report(
            pipe,
            name.strip(),
            fields=fields_list,
            filter=filt,
            formulas=formulas_val,
        )

    run_cli_command(ctx, json_out, factory)


@report_pipe_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def report_pipe_update(
    ctx: typer.Context,
    report_id: str = resource_id_argument(help="Pipe report id."),
    name: str | None = typer.Option(None, "--name", "-n"),
    color: str | None = typer.Option(None, "--color"),
    fields: str | None = typer.Option(None, "--fields"),
    filter_json: str | None = typer.Option(None, "--filter"),
    formulas: str | None = typer.Option(None, "--formulas"),
    featured_field: str | None = typer.Option(None, "--featured-field"),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Update a pipe report (``update_pipe_report``)."""
    fields_list = parse_json_value(fields, "--fields") if fields else None
    if fields_list is not None and not isinstance(fields_list, list):
        raise typer.BadParameter("--fields must be a JSON array")
    filt = validate_report_filter_cli(parse_json_object(filter_json, "--filter"))
    formulas_val = parse_json_value(formulas, "--formulas") if formulas else None
    if formulas_val is not None and not isinstance(formulas_val, list):
        raise typer.BadParameter("--formulas must be a JSON array")

    async def factory(client: PipefyClient):
        return await client.update_pipe_report(
            report_id,
            name=name.strip() if name else None,
            color=color,
            fields=fields_list,
            filter=filt,
            formulas=formulas_val,
            featured_field=featured_field,
        )

    run_cli_command(ctx, json_out, factory)


@report_pipe_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def report_pipe_delete(
    ctx: typer.Context,
    report_id: str = resource_id_argument(help="Pipe report id."),
    yes: bool = typer.Option(False, "--yes", "-y"),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Delete a pipe report (``delete_pipe_report``)."""
    confirm_destructive(yes=yes, description=f"pipe report {report_id}", verb="delete")

    async def factory(client: PipefyClient):
        return await client.delete_pipe_report(report_id)

    run_cli_command(ctx, json_out, factory)


@report_pipe_app.command("export")
def report_pipe_export(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Pipe id."),
    report_id: str = typer.Option(..., "--report-id", help="Pipe report id."),
    format_: str = typer.Option(
        "json",
        "--format",
        help="json: print mutation + poll metadata; csv: wait for fileURL and stream bytes.",
    ),
    sort_by: str | None = typer.Option(
        None, "--sort-by", help="JSON ReportSortDirectionInput."
    ),
    filter_json: str | None = typer.Option(None, "--filter"),
    columns: str | None = typer.Option(
        None, "--columns", help="JSON array of column ids."
    ),
    poll_timeout: float = typer.Option(
        90.0,
        "--poll-timeout",
        help="Seconds to poll export status before failing (CSV only).",
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Start a pipe report export (``export_pipe_report``); csv waits and streams the file."""
    fmt = format_.strip().lower()
    if fmt not in ("json", "csv"):
        raise typer.BadParameter("--format must be json or csv")
    if fmt == "csv" and json_out:
        raise typer.BadParameter(
            "--json is mutually exclusive with --format csv (CSV is written as raw bytes to stdout)."
        )
    sort_obj = parse_json_object(sort_by, "--sort-by")
    filt = validate_report_filter_cli(parse_json_object(filter_json, "--filter"))
    cols = parse_json_value(columns, "--columns") if columns else None
    if cols is not None and not isinstance(cols, list):
        raise typer.BadParameter("--columns must be a JSON array")

    if fmt == "json":

        async def factory(client: PipefyClient):
            return await client.export_pipe_report(
                pipe,
                report_id,
                sort_by=sort_obj,
                filter=filt,
                columns=cols,
            )

        run_cli_command(ctx, json_out, factory)
        return

    async def csv_factory(client: PipefyClient) -> None:
        start = await client.export_pipe_report(
            pipe,
            report_id,
            sort_by=sort_obj,
            filter=filt,
            columns=cols,
        )
        exp = (start.get("exportPipeReport") or {}).get("pipeReportExport") or {}
        export_id = exp.get("id")
        if not export_id:
            typer.echo(
                "Could not read export id from exportPipeReport response.", err=True
            )
            raise typer.Exit(1)
        await write_export_csv_to_stdout(
            export_id=str(export_id),
            poll_fetch=client.get_pipe_report_export,
            unwrap_status=lambda raw: (raw or {}).get("pipeReportExport") or {},
            poll_timeout_seconds=poll_timeout,
        )

    run_pipefy_client_coroutine(ctx, csv_factory, value_error_exit_code=1)
