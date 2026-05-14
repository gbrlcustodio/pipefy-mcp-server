"""Automation job exports (MCP parity names)."""

from __future__ import annotations

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import run_cli_command

export_app = typer.Typer(
    help="Bulk exports (automation jobs).",
    no_args_is_help=True,
)


@export_app.command("automation-jobs")
def export_automation_jobs_cmd(
    ctx: typer.Context,
    organization: str = typer.Option(
        ..., "--organization", "--org", help="Organization id."
    ),
    period: str = typer.Option(
        ...,
        "--period",
        help="current_month | last_month | last_3_months",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Queue automation jobs export (``export_automation_jobs``)."""

    async def factory(client: PipefyClient):
        return await client.export_automation_jobs(organization, period)

    run_cli_command(ctx, json_out, factory)


@export_app.command("automation-jobs-csv")
def export_automation_jobs_csv_cmd(
    ctx: typer.Context,
    export_id: str = typer.Argument(..., help="Export id after status is finished."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="When set, print JSON envelope with csv text; default is Rich/JSON of payload.",
    ),
) -> None:
    """Download finished export as CSV text (``get_automation_jobs_export_csv``)."""

    async def factory(client: PipefyClient):
        return await client.get_automation_jobs_export_csv(export_id)

    run_cli_command(ctx, json_out, factory)
