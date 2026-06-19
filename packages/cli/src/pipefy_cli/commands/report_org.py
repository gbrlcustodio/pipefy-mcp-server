"""Organization-level reports."""

from __future__ import annotations

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    parse_json_object,
    parse_json_value,
    prepare_report_cards_filter_cli,
    resource_id_argument,
    run_cli_command,
    run_pipefy_client_coroutine,
    write_export_csv_to_stdout,
)

report_org_app = typer.Typer(help="Organization reports.", no_args_is_help=True)


@report_org_app.command("list")
def report_org_list(
    ctx: typer.Context,
    organization: str = typer.Option(..., "--organization", "--org"),
    first: int = typer.Option(30, "--first", help="Page size."),
    after: str | None = typer.Option(None, "--after", help="Pagination cursor."),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """List organization reports (``get_organization_reports``)."""

    async def factory(client: PipefyClient):
        return await client.get_organization_reports(
            organization, first=first, after=after
        )

    run_cli_command(ctx, json_out, factory)


@report_org_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def report_org_get(
    ctx: typer.Context,
    report_id: str = resource_id_argument(help="Organization report id."),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Fetch one organization report (``get_organization_report``)."""

    async def factory(client: PipefyClient):
        return await client.get_organization_report(report_id)

    run_cli_command(ctx, json_out, factory)


@report_org_app.command("create")
def report_org_create(
    ctx: typer.Context,
    organization: str = typer.Option(..., "--organization", "--org"),
    name: str = typer.Option(..., "--name", "-n"),
    pipe_ids: str = typer.Option(
        ..., "--pipe-ids", help="JSON array of pipe id strings."
    ),
    fields: str | None = typer.Option(None, "--fields"),
    filter_json: str | None = typer.Option(None, "--filter"),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Create an organization report (``create_organization_report``)."""
    pids = parse_json_value(pipe_ids, "--pipe-ids")
    if not isinstance(pids, list) or not pids:
        raise typer.BadParameter("--pipe-ids must be a non-empty JSON array")
    pipe_list = [str(x) for x in pids]
    fields_list = parse_json_value(fields, "--fields") if fields else None
    if fields_list is not None and not isinstance(fields_list, list):
        raise typer.BadParameter("--fields must be a JSON array")
    filt = prepare_report_cards_filter_cli(parse_json_object(filter_json, "--filter"))

    async def factory(client: PipefyClient):
        return await client.create_organization_report(
            organization,
            name.strip(),
            pipe_list,
            fields=fields_list,
            filter=filt,
        )

    run_cli_command(ctx, json_out, factory)


@report_org_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def report_org_update(
    ctx: typer.Context,
    report_id: str = resource_id_argument(help="Organization report id."),
    name: str | None = typer.Option(None, "--name", "-n"),
    color: str | None = typer.Option(None, "--color"),
    fields: str | None = typer.Option(None, "--fields"),
    filter_json: str | None = typer.Option(None, "--filter"),
    pipe_ids: str | None = typer.Option(
        None, "--pipe-ids", help="JSON array of pipe ids."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Update an organization report (``update_organization_report``)."""
    fields_list = parse_json_value(fields, "--fields") if fields else None
    if fields_list is not None and not isinstance(fields_list, list):
        raise typer.BadParameter("--fields must be a JSON array")
    filt = prepare_report_cards_filter_cli(parse_json_object(filter_json, "--filter"))
    pids = parse_json_value(pipe_ids, "--pipe-ids") if pipe_ids else None
    if pids is not None:
        if not isinstance(pids, list):
            raise typer.BadParameter("--pipe-ids must be a JSON array")
        pids = [str(x) for x in pids]

    async def factory(client: PipefyClient):
        return await client.update_organization_report(
            report_id,
            name=name.strip() if name else None,
            color=color,
            fields=fields_list,
            filter=filt,
            pipe_ids=pids,
        )

    run_cli_command(ctx, json_out, factory)


@report_org_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def report_org_delete(
    ctx: typer.Context,
    report_id: str = resource_id_argument(help="Organization report id."),
    yes: bool = typer.Option(False, "--yes", "-y"),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Delete an organization report (``delete_organization_report``)."""
    confirm_destructive(
        yes=yes, description=f"organization report {report_id}", verb="delete"
    )

    async def factory(client: PipefyClient):
        return await client.delete_organization_report(report_id)

    run_cli_command(ctx, json_out, factory)


@report_org_app.command("export")
def report_org_export(
    ctx: typer.Context,
    organization: str = typer.Option(..., "--organization", "--org"),
    format_: str = typer.Option(
        "json",
        "--format",
        help="json: return export mutation payload; csv: poll and stream download.",
    ),
    organization_report_id: str | None = typer.Option(
        None, "--organization-report-id", help="Optional report id to export."
    ),
    pipe_ids: str | None = typer.Option(
        None, "--pipe-ids", help="Optional JSON array of pipe ids."
    ),
    sort_by: str | None = typer.Option(None, "--sort-by"),
    filter_json: str | None = typer.Option(None, "--filter"),
    columns: str | None = typer.Option(None, "--columns"),
    poll_timeout: float = typer.Option(
        90.0,
        "--poll-timeout",
        help="Seconds to poll export status before failing (CSV only).",
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Export an organization report (``export_organization_report``)."""
    fmt = format_.strip().lower()
    if fmt not in ("json", "csv"):
        raise typer.BadParameter("--format must be json or csv")
    if fmt == "csv" and json_out:
        raise typer.BadParameter(
            "--json is mutually exclusive with --format csv (CSV is written as raw bytes to stdout)."
        )
    sort_obj = parse_json_object(sort_by, "--sort-by")
    filt = prepare_report_cards_filter_cli(parse_json_object(filter_json, "--filter"))
    cols = parse_json_value(columns, "--columns") if columns else None
    if cols is not None and not isinstance(cols, list):
        raise typer.BadParameter("--columns must be a JSON array")
    pids = parse_json_value(pipe_ids, "--pipe-ids") if pipe_ids else None
    if pids is not None:
        if not isinstance(pids, list):
            raise typer.BadParameter("--pipe-ids must be a JSON array")
        pids = [str(x) for x in pids]

    if fmt == "json":

        async def factory(client: PipefyClient):
            return await client.export_organization_report(
                organization,
                organization_report_id=organization_report_id,
                pipe_ids=pids,
                sort_by=sort_obj,
                filter=filt,
                columns=cols,
            )

        run_cli_command(ctx, json_out, factory)
        return

    async def csv_factory(client: PipefyClient) -> None:
        start = await client.export_organization_report(
            organization,
            organization_report_id=organization_report_id,
            pipe_ids=pids,
            sort_by=sort_obj,
            filter=filt,
            columns=cols,
        )
        exp = (start.get("exportOrganizationReport") or {}).get(
            "organizationReportExport"
        ) or {}
        export_id = exp.get("id")
        if not export_id:
            typer.echo(
                "Could not read export id from exportOrganizationReport response.",
                err=True,
            )
            raise typer.Exit(1)
        await write_export_csv_to_stdout(
            export_id=str(export_id),
            poll_fetch=client.get_organization_report_export,
            unwrap_status=lambda raw: (raw or {}).get("organizationReportExport") or {},
            poll_timeout_seconds=poll_timeout,
        )

    run_pipefy_client_coroutine(ctx, csv_factory, value_error_exit_code=1)
