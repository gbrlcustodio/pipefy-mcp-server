"""Typer entry point for the ``pipefy`` CLI."""

from __future__ import annotations

import os

import typer

from pipefy_cli import __version__ as _cli_version
from pipefy_cli.commands.agent import agent_app
from pipefy_cli.commands.ai_automation import ai_automation_app
from pipefy_cli.commands.attachment import attachment_app
from pipefy_cli.commands.audit import audit_app
from pipefy_cli.commands.auth import auth_app
from pipefy_cli.commands.automation import automation_app
from pipefy_cli.commands.card import card_app
from pipefy_cli.commands.email import email_app
from pipefy_cli.commands.export import export_app
from pipefy_cli.commands.field import field_app
from pipefy_cli.commands.field_condition import field_condition_app
from pipefy_cli.commands.graphql import graphql_app
from pipefy_cli.commands.introspect import introspect_app
from pipefy_cli.commands.label import label_app
from pipefy_cli.commands.member import member_app
from pipefy_cli.commands.org import org_app
from pipefy_cli.commands.phase import phase_app
from pipefy_cli.commands.pipe import pipe_app
from pipefy_cli.commands.record import record_app
from pipefy_cli.commands.relation import relation_app
from pipefy_cli.commands.report_org import report_org_app
from pipefy_cli.commands.report_pipe import report_pipe_app
from pipefy_cli.commands.skills import skills_app
from pipefy_cli.commands.table import table_app
from pipefy_cli.commands.usage import usage_app
from pipefy_cli.commands.webhook import webhook_app
from pipefy_cli.config import resolve_pipefy_settings

app = typer.Typer(
    name="pipefy",
    help="Pipefy CLI (GraphQL via pipefy-sdk).",
    no_args_is_help=True,
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(_cli_version)
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    graphql_url: str | None = typer.Option(
        None,
        "--graphql-url",
        help="Override PIPEFY_GRAPHQL_URL.",
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        help="Bearer token for GraphQL (skips OAuth). Overrides PIPEFY_TOKEN if both are set.",
    ),
    allow_insecure_urls: bool = typer.Option(
        False,
        "--allow-insecure-urls",
        help="Allow http:// and private hosts (overrides env for this process).",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_print_version,
        is_eager=True,
        help="Print the pipefy-cli version and exit.",
    ),
) -> None:
    """Global options apply to all subcommands."""
    ctx.ensure_object(dict)
    try:
        pipefy_settings = resolve_pipefy_settings(
            graphql_url_flag=graphql_url,
            allow_insecure_urls_flag=True if allow_insecure_urls else None,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    ctx.obj["pipefy_settings"] = pipefy_settings
    from_env = os.environ.get("PIPEFY_TOKEN")
    cli_token = token.strip() if token else None
    env_token = from_env.strip() if from_env else None
    ctx.obj["token"] = cli_token or env_token


app.add_typer(agent_app, name="agent")
app.add_typer(ai_automation_app, name="ai-automation")
app.add_typer(attachment_app, name="attachment")
app.add_typer(audit_app, name="audit")
app.add_typer(auth_app, name="auth")
app.add_typer(automation_app, name="automation")
app.add_typer(card_app, name="card")
app.add_typer(email_app, name="email")
app.add_typer(field_condition_app, name="field-condition")
app.add_typer(pipe_app, name="pipe")
app.add_typer(phase_app, name="phase")
app.add_typer(field_app, name="field")
app.add_typer(table_app, name="table")
app.add_typer(record_app, name="record")
app.add_typer(label_app, name="label")
app.add_typer(webhook_app, name="webhook")
app.add_typer(relation_app, name="relation")
app.add_typer(member_app, name="member")
app.add_typer(skills_app, name="skills")
app.add_typer(graphql_app, name="graphql")
app.add_typer(introspect_app, name="introspect")
app.add_typer(export_app, name="export")
app.add_typer(org_app, name="org")
app.add_typer(report_org_app, name="report-org")
app.add_typer(report_pipe_app, name="report-pipe")
app.add_typer(usage_app, name="usage")
