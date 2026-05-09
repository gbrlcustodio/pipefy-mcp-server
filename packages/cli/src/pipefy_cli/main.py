"""Typer entry point for the ``pipefy`` CLI."""

from __future__ import annotations

import os

import typer

from pipefy_cli.commands.card import card_app
from pipefy_cli.config import resolve_pipefy_settings

app = typer.Typer(
    name="pipefy",
    help="Pipefy CLI (GraphQL via pipefy-ai-sdk).",
    no_args_is_help=True,
)


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


app.add_typer(card_app, name="card")
