"""Card subcommands."""

from __future__ import annotations

import asyncio

import typer
from pipefy_sdk.exceptions import PipefyError

from pipefy_cli.auth import get_authenticated_client
from pipefy_cli.output import render_json, render_rich

card_app = typer.Typer(help="Card operations.", no_args_is_help=True)


@card_app.command("get")
def card_get(
    ctx: typer.Context,
    card_id: str,
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Fetch a card by id."""
    root = ctx.find_root()
    obj = root.obj
    pipefy_settings = obj["pipefy_settings"]
    token: str | None = obj.get("token")

    async def _run():
        client = get_authenticated_client(pipefy_settings, bearer_token=token)
        return await client.get_card(card_id)

    try:
        data = asyncio.run(_run())
    except PipefyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    if json_out:
        render_json(data)
    else:
        render_rich(data)
