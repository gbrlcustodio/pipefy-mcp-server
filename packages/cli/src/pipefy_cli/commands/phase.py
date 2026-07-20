"""Phase subcommands."""

from __future__ import annotations

from typing import Any

import typer
from pipefy_sdk import PipefyClient
from pipefy_sdk.phase_inventory import (
    get_phase_not_found_message,
    is_get_phase_not_found_error,
)

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    parse_json_object,
    resource_id_argument,
    run_cli_command,
    validate_cards_page_size,
)

phase_app = typer.Typer(help="Pipe phase operations.", no_args_is_help=True)


@phase_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def phase_get(
    ctx: typer.Context,
    phase_id: str = resource_id_argument(help="Phase id."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
    required_only: bool = typer.Option(
        False,
        "--required-only",
        help="Return only required fields (same query as MCP get_phase_fields).",
    ),
) -> None:
    """Load phase metadata and fields by id (via ``get_phase_fields``)."""

    async def factory(client: PipefyClient):
        return await client.get_phase_fields(phase_id, required_only=required_only)

    run_cli_command(ctx, json_out, factory)


@phase_app.command(
    "targets",
    context_settings=ID_POSITIONAL_CONTEXT_SETTINGS,
)
def phase_targets(
    ctx: typer.Context,
    phase_id: str = resource_id_argument(
        help="Source phase id (card's current phase)."
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """List phases a card may move to from this phase (UI transition rules)."""

    async def factory(client: PipefyClient):
        return await client.get_phase_allowed_move_targets(phase_id)

    run_cli_command(ctx, json_out, factory)


@phase_app.command(
    "count",
    context_settings=ID_POSITIONAL_CONTEXT_SETTINGS,
)
def phase_count(
    ctx: typer.Context,
    phase_id: str = resource_id_argument(help="Phase id."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Return native ``Phase.cards_count`` for a phase (fast inventory).

    On the start-form phase, ``cards_count`` may be 0 while cards still exist;
    use ``pipefy phase cards`` to list cards when the count looks wrong.
    """

    async def factory(client: PipefyClient):
        try:
            return await client.get_phase(phase_id)
        except ValueError as exc:
            if is_get_phase_not_found_error(exc):
                raise ValueError(get_phase_not_found_message(phase_id)) from exc
            raise

    run_cli_command(ctx, json_out, factory)


@phase_app.command("cards", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def phase_cards(
    ctx: typer.Context,
    phase_id: str = resource_id_argument(help="Phase id."),
    first: int = typer.Option(
        50,
        "--first",
        help="Max cards per page (1-500).",
    ),
    after: str | None = typer.Option(
        None,
        "--after",
        help="Cursor from pageInfo.endCursor of a previous call.",
    ),
    include_fields: bool = typer.Option(
        False,
        "--include-fields",
        help="Include each card's custom fields in the response.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """List cards in a phase (``Phase.cards`` pagination)."""

    first = validate_cards_page_size(first)

    async def factory(client: PipefyClient):
        return await client.get_phase_cards(
            phase_id,
            first=first,
            after=after,
            include_fields=include_fields,
        )

    run_cli_command(ctx, json_out, factory)


@phase_app.command("create")
def phase_create(
    ctx: typer.Context,
    pipe_id: str = typer.Option(
        ..., "--pipe", help="Pipe id that will contain the phase."
    ),
    name: str = typer.Option(..., "--name", "-n", help="Phase display name."),
    done: bool = typer.Option(False, "--done", help="Mark as a final/done phase."),
    index: float | None = typer.Option(
        None,
        "--index",
        help=(
            "1-based insert among workflow phases; omit to append. "
            "Does not set Connections (UI-only)."
        ),
    ),
    description: str | None = typer.Option(None, "--description", "-d"),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Create a phase in a pipe."""

    stripped = name.strip()
    if not stripped:
        typer.echo("Phase name must be non-empty.", err=True)
        raise typer.Exit(2)

    async def factory(client: PipefyClient):
        return await client.create_phase(
            pipe_id,
            stripped,
            done=done,
            index=index,
            description=description,
        )

    run_cli_command(ctx, json_out, factory)


@phase_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def phase_update(
    ctx: typer.Context,
    phase_id: str = resource_id_argument(help="Phase id."),
    name: str | None = typer.Option(None, "--name", "-n"),
    description: str | None = typer.Option(None, "--description", "-d"),
    done: bool | None = typer.Option(
        None,
        "--done/--no-done",
        help="Set or clear the final-phase flag.",
    ),
    color: str | None = typer.Option(None, "--color"),
    lateness_time: int | None = typer.Option(None, "--lateness-time"),
    can_receive_from_draft: bool | None = typer.Option(
        None,
        "--can-receive-from-draft/--no-can-receive-from-draft",
    ),
    extra_json: str | None = typer.Option(
        None,
        "--extra",
        help="JSON object merged into UpdatePhaseInput (snake_case keys).",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Update a phase (Pipefy ``UpdatePhaseInput``). Resolves current name when omitted."""

    extra = parse_json_object(extra_json, "--extra")
    update_attrs: dict[str, Any] = {}
    if name is not None:
        update_attrs["name"] = name
    if description is not None:
        update_attrs["description"] = description
    if done is not None:
        update_attrs["done"] = done
    if color is not None:
        update_attrs["color"] = color
    if lateness_time is not None:
        update_attrs["lateness_time"] = lateness_time
    if can_receive_from_draft is not None:
        update_attrs["can_receive_card_directly_from_draft"] = can_receive_from_draft
    if extra:
        update_attrs.update(extra)
    if not update_attrs:
        typer.echo(
            "Provide at least one of: --name, --description, --done, --color, "
            "--lateness-time, --can-receive-from-draft, --extra.",
            err=True,
        )
        raise typer.Exit(2)

    async def factory(client: PipefyClient):
        if "name" not in update_attrs:
            phase_info = await client.get_phase_fields(phase_id)
            current = phase_info.get("phase_name")
            if not current:
                raise typer.BadParameter(
                    f"Phase {phase_id} not found or has no name; pass --name explicitly."
                )
            update_attrs["name"] = current
        return await client.update_phase(phase_id, **update_attrs)

    run_cli_command(ctx, json_out, factory)


@phase_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def phase_delete(
    ctx: typer.Context,
    phase_id: str = resource_id_argument(help="Phase id."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete a phase permanently."""

    confirm_destructive(yes=yes, description=f"phase {phase_id}")

    async def factory(client: PipefyClient):
        return await client.delete_phase(phase_id)

    run_cli_command(ctx, json_out, factory)
