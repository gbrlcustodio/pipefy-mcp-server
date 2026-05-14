"""Webhook subcommands."""

from __future__ import annotations

import json
from typing import Any

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    confirm_destructive,
    parse_json_object,
    run_cli_command,
)

webhook_app = typer.Typer(help="Pipe webhook operations.", no_args_is_help=True)


def _parse_actions_json(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON for --actions: {exc}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise typer.BadParameter("--actions must be a non-empty JSON array of strings.")
    out: list[str] = []
    for item in parsed:
        if not isinstance(item, str) or not item.strip():
            raise typer.BadParameter("Each action must be a non-empty string.")
        out.append(item.strip())
    return out


@webhook_app.command("list")
def webhook_list(
    ctx: typer.Context,
    pipe_id: str = typer.Option(..., "--pipe", help="Pipe id."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List webhooks on a pipe."""

    async def factory(client: PipefyClient):
        return await client.get_webhooks(pipe_id)

    run_cli_command(ctx, json_out, factory)


@webhook_app.command("create")
def webhook_create(
    ctx: typer.Context,
    pipe_id: str = typer.Option(..., "--pipe", help="Pipe id."),
    url: str = typer.Option(..., "--url", help="HTTPS callback URL."),
    actions_json: str = typer.Option(
        ...,
        "--actions",
        help='JSON array of event action strings, e.g. \'["card.create","card.move"]\'.',
    ),
    extra_json: str | None = typer.Option(
        None,
        "--extra",
        help="JSON object of extra CreateWebhookInput fields.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Create a webhook."""

    actions = _parse_actions_json(actions_json)
    extra = parse_json_object(extra_json, "--extra") or {}
    u = url.strip()
    if not u:
        typer.echo("--url must be non-empty.", err=True)
        raise typer.Exit(2)

    async def factory(client: PipefyClient):
        return await client.create_webhook(pipe_id, u, actions, **extra)

    run_cli_command(ctx, json_out, factory)


@webhook_app.command("update")
def webhook_update(
    ctx: typer.Context,
    webhook_id: str,
    name: str | None = typer.Option(None, "--name"),
    url: str | None = typer.Option(None, "--url"),
    actions_json: str | None = typer.Option(
        None,
        "--actions",
        help="JSON array of event action strings (non-empty when provided).",
    ),
    headers_json: str | None = typer.Option(
        None,
        "--headers",
        help="JSON object of custom HTTP headers.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Update a webhook (pass at least one attribute)."""

    kwargs: dict[str, Any] = {}
    if name is not None:
        if not name.strip():
            raise typer.BadParameter("--name, when provided, must be non-empty.")
        kwargs["name"] = name.strip()
    if url is not None:
        if not url.strip():
            raise typer.BadParameter("--url, when provided, must be non-empty.")
        kwargs["url"] = url.strip()
    if actions_json is not None:
        kwargs["actions"] = _parse_actions_json(actions_json)
    if headers_json is not None:
        kwargs["headers"] = parse_json_object(headers_json, "--headers") or {}
    if not kwargs:
        raise typer.BadParameter(
            "Provide at least one of: --name, --url, --actions, --headers."
        )

    async def factory(client: PipefyClient):
        return await client.update_webhook(webhook_id, **kwargs)

    run_cli_command(ctx, json_out, factory)


@webhook_app.command("delete")
def webhook_delete(
    ctx: typer.Context,
    webhook_id: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete a webhook permanently."""

    confirm_destructive(yes=yes, description=f"webhook {webhook_id}")

    async def factory(client: PipefyClient):
        return await client.delete_webhook(webhook_id)

    run_cli_command(ctx, json_out, factory)
