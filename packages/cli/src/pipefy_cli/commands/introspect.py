"""GraphQL schema introspection (types, root fields, search)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import typer
from pipefy_sdk import PipefyClient
from pipefy_sdk.exceptions import PipefyError

from pipefy_cli.auth import get_authenticated_client
from pipefy_cli.commands._common import settings_and_token
from pipefy_cli.output import render_json, render_rich

introspect_app = typer.Typer(
    help="Discover GraphQL types and operations (JSON default).",
    no_args_is_help=True,
)
schema_app = typer.Typer(help="Schema-wide search.", no_args_is_help=True)


def _emit_introspection(data: object, *, rich: bool) -> None:
    """Print introspection payload (JSON default, optional Rich)."""
    if rich:
        render_rich(data)
    else:
        render_json(data)


def _run_introspect(
    ctx: typer.Context,
    factory: Callable[[PipefyClient], Awaitable[Any]],
) -> Any:
    """Execute an async introspection call with shared auth and error mapping."""
    pipefy_settings, token = settings_and_token(ctx)

    async def _run() -> object:
        client = get_authenticated_client(pipefy_settings, bearer_token=token)
        return await factory(client)

    try:
        return asyncio.run(_run())
    except PipefyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@introspect_app.command("type")
def introspect_type_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="GraphQL type name (e.g. Card)."),
    max_depth: int = typer.Option(
        1, "--max-depth", help="Nested type resolution depth."
    ),
    rich: bool = typer.Option(
        False,
        "--rich",
        help="Pretty-print with Rich instead of JSON.",
    ),
) -> None:
    """Introspect a schema type (``introspect_type``)."""

    async def factory(client: PipefyClient):
        return await client.introspect_type(name, max_depth=max_depth)

    payload = _run_introspect(ctx, factory)
    _emit_introspection(payload, rich=rich)


@introspect_app.command("query")
def introspect_query_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Root query field name."),
    max_depth: int = typer.Option(
        1, "--max-depth", help="Nested type resolution depth."
    ),
    rich: bool = typer.Option(
        False, "--rich", help="Pretty-print with Rich instead of JSON."
    ),
) -> None:
    """Introspect a root query field (``introspect_query``)."""

    async def factory(client: PipefyClient):
        return await client.introspect_query(name, max_depth=max_depth)

    payload = _run_introspect(ctx, factory)
    _emit_introspection(payload, rich=rich)


@introspect_app.command("mutation")
def introspect_mutation_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Root mutation field name."),
    max_depth: int = typer.Option(
        1, "--max-depth", help="Nested type resolution depth."
    ),
    rich: bool = typer.Option(
        False, "--rich", help="Pretty-print with Rich instead of JSON."
    ),
) -> None:
    """Introspect a root mutation field (``introspect_mutation``)."""

    async def factory(client: PipefyClient):
        return await client.introspect_mutation(name, max_depth=max_depth)

    payload = _run_introspect(ctx, factory)
    _emit_introspection(payload, rich=rich)


@schema_app.command("search")
def introspect_schema_search(
    ctx: typer.Context,
    keyword: str = typer.Argument(..., help="Case-insensitive substring."),
    kind: str | None = typer.Option(
        None,
        "--kind",
        help="Optional GraphQL type kind (OBJECT, INPUT_OBJECT, ENUM, ...).",
    ),
    rich: bool = typer.Option(
        False, "--rich", help="Pretty-print with Rich instead of JSON."
    ),
) -> None:
    """Search schema types (``search_schema``)."""

    async def factory(client: PipefyClient):
        return await client.search_schema(keyword, kind=kind)

    payload = _run_introspect(ctx, factory)
    _emit_introspection(payload, rich=rich)


introspect_app.add_typer(schema_app, name="schema")
