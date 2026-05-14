"""Pipe audit log export (async job)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, TextIO

import typer
from pipefy_sdk.exceptions import PipefyError

from pipefy_cli.auth import get_authenticated_client
from pipefy_cli.commands._common import settings_and_token
from pipefy_cli.output import render_json, render_rich

audit_app = typer.Typer(help="Pipe audit log exports.", no_args_is_help=True)


def _open_output(path: Path) -> TextIO:
    """Open a UTF-8 text file for writing (parent dirs created)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("w", encoding="utf-8")


@audit_app.command("export")
def audit_export(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Pipe UUID for the audit export."),
    search: str | None = typer.Option(
        None,
        "--search",
        help="Optional search term filter passed to the API.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write JSON response to this path instead of stdout.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="When using stdout, print JSON instead of Rich (file output is always JSON).",
    ),
) -> None:
    """Queue a pipe audit log export (``export_pipe_audit_logs``).

    The GraphQL API returns only ``success``; Pipefy delivers the export outside this mutation
    (no CSV stream in the SDK response).
    """
    pipefy_settings, token = settings_and_token(ctx)

    async def _run() -> dict[str, Any]:
        client = get_authenticated_client(pipefy_settings, bearer_token=token)
        return await client.export_pipe_audit_logs(pipe, search_term=search)

    try:
        payload = asyncio.run(_run())
    except PipefyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    if output is not None:
        with _open_output(output) as fh:
            print(json.dumps(payload, indent=2), file=fh, flush=True)
        return

    if json_out:
        render_json(payload)
    else:
        render_rich(payload)
