"""AI usage dashboards (agents, automations, credits)."""

from __future__ import annotations

import typer
from pipefy_sdk import AUTOMATION_EXECUTION_METRICS_PERIODS, PipefyClient

from pipefy_cli.commands._common import parse_json_object, run_cli_command

usage_app = typer.Typer(help="AI and automation usage metrics.", no_args_is_help=True)

_EXECUTION_METRICS_PERIOD_HELP = " | ".join(AUTOMATION_EXECUTION_METRICS_PERIODS)


def _parse_date_range(from_iso: str, to_iso: str) -> dict[str, str]:
    return {"from": from_iso.strip(), "to": to_iso.strip()}


@usage_app.command("agents")
def usage_agents(
    ctx: typer.Context,
    organization: str = typer.Option(
        ...,
        "--organization",
        "--org",
        help="Organization UUID (or numeric id resolvable by SDK).",
    ),
    date_from: str = typer.Option(
        ..., "--from", help="ISO8601 start (filter_date.from)."
    ),
    date_to: str = typer.Option(..., "--to", help="ISO8601 end (filter_date.to)."),
    filters: str | None = typer.Option(
        None, "--filters", help="Optional JSON object (FilterParams shape)."
    ),
    search: str | None = typer.Option(
        None, "--search", help="Optional free-text search."
    ),
    sort: str | None = typer.Option(
        None, "--sort", help="Optional JSON sort criteria object."
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """AI agent usage for an org (``get_agents_usage``)."""
    filt = parse_json_object(filters, "--filters")
    sort_obj = parse_json_object(sort, "--sort")

    async def factory(client: PipefyClient):
        return await client.get_agents_usage(
            organization,
            _parse_date_range(date_from, date_to),
            filters=filt,
            search=search,
            sort=sort_obj,
        )

    run_cli_command(ctx, json_out, factory)


@usage_app.command("automations")
def usage_automations(
    ctx: typer.Context,
    organization: str = typer.Option(..., "--organization", "--org"),
    date_from: str = typer.Option(..., "--from"),
    date_to: str = typer.Option(..., "--to"),
    filters: str | None = typer.Option(None, "--filters"),
    search: str | None = typer.Option(None, "--search"),
    sort: str | None = typer.Option(None, "--sort"),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Automation usage for an org (``get_automations_usage``)."""
    filt = parse_json_object(filters, "--filters")
    sort_obj = parse_json_object(sort, "--sort")

    async def factory(client: PipefyClient):
        return await client.get_automations_usage(
            organization,
            _parse_date_range(date_from, date_to),
            filters=filt,
            search=search,
            sort=sort_obj,
        )

    run_cli_command(ctx, json_out, factory)


@usage_app.command("execution-metrics")
def usage_execution_metrics(
    ctx: typer.Context,
    organization: str = typer.Option(
        ...,
        "--organization",
        "--org",
        help="Organization ID (numeric org id, same as in the Pipefy URL).",
    ),
    automation_ids: list[str] = typer.Option(
        [],
        "--automation",
        "-a",
        help="Automation ID to fetch metrics for (repeat for multiple; omit to fetch all automations in the organization).",
    ),
    repo: str | None = typer.Option(
        None, "--repo", help="Optional pipe/repo ID to scope the query."
    ),
    period: str = typer.Option(
        "SIXTY_MINUTES",
        "--period",
        help=_EXECUTION_METRICS_PERIOD_HELP,
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Automation execution metrics (``get_automation_execution_metrics``).

    Returns metrics for the automations the token may read plus a ``partial_errors``
    list naming any that were denied.
    """

    async def factory(client: PipefyClient):
        return await client.get_automation_execution_metrics(
            organization, automation_ids or None, repo_id=repo, period=period
        )

    run_cli_command(ctx, json_out, factory)


@usage_app.command("credits")
def usage_credits(
    ctx: typer.Context,
    organization: str = typer.Option(..., "--organization", "--org"),
    period: str = typer.Option(
        "current_month",
        "--period",
        help="current_month | last_month | last_3_months",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """AI credit usage dashboard (``get_ai_credit_usage``)."""

    async def factory(client: PipefyClient):
        return await client.get_ai_credit_usage(organization, period)

    run_cli_command(ctx, json_out, factory)
