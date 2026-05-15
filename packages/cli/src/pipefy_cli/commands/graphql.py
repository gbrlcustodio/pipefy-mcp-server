"""Raw GraphQL execution (escape hatch for agents)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import typer
from graphql import GraphQLSyntaxError, parse
from graphql.language.ast import OperationDefinitionNode, OperationType
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import run_pipefy_client_coroutine
from pipefy_cli.output import render_json, render_rich

graphql_app = typer.Typer(
    help="Execute arbitrary GraphQL (mutations require --yes). See docs/cli/self-healing.md.",
    no_args_is_help=True,
)


def _document_contains_mutation(document: str) -> bool:
    """Return True when the document defines at least one mutation operation."""
    try:
        doc = parse(document)
    except GraphQLSyntaxError:
        return False
    for defn in doc.definitions:
        if (
            isinstance(defn, OperationDefinitionNode)
            and defn.operation == OperationType.MUTATION
        ):
            return True
    return False


def _parse_vars_json(raw: str | None) -> dict[str, Any]:
    """Parse --vars JSON; default is empty object. Malformed JSON raises typer.Exit(2)."""
    if raw is None or raw.strip() == "":
        return {}
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON for --vars: {exc}", err=True)
        raise typer.Exit(2) from exc
    if not isinstance(parsed, dict):
        typer.echo("--vars must be a JSON object.", err=True)
        raise typer.Exit(2)
    return parsed


def _run_graphql(
    ctx: typer.Context,
    factory: Callable[[PipefyClient], Awaitable[Any]],
) -> Any:
    """Run an async GraphQL call with shared auth."""
    return run_pipefy_client_coroutine(ctx, factory)


@graphql_app.command("exec")
def graphql_exec(
    ctx: typer.Context,
    query: str = typer.Option(
        ...,
        "--query",
        "-q",
        help="GraphQL document string (query or mutation).",
    ),
    vars_json: str | None = typer.Option(
        None,
        "--vars",
        help='Variables JSON object (default "{}" ).',
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Acknowledge and run mutations (required when the document includes mutation).",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Emit JSON to stdout (default is Rich for objects).",
    ),
) -> None:
    """Execute GraphQL via the SDK (``execute_graphql``).

    Mutations are rejected unless ``--yes`` is set (exit code 2). Pair with
    ``pipefy introspect`` to discover operation shapes (see docs/cli/self-healing.md).
    """
    variables = _parse_vars_json(vars_json)
    if _document_contains_mutation(query) and not yes:
        typer.echo(
            "This document includes a mutation; re-run with --yes to confirm, "
            "or use read-only operations.",
            err=True,
        )
        raise typer.Exit(2)

    async def factory(client: PipefyClient):
        return await client.execute_graphql(query, variables)

    payload = _run_graphql(ctx, factory)
    if json_out:
        render_json(payload)
    else:
        render_rich(payload)
