"""Card subcommands."""

from __future__ import annotations

from typing import Any

import typer
from pipefy_sdk import (
    CardSearch,
    CommentInput,
    DeleteCommentInput,
    PipefyClient,
    UpdateCommentInput,
    copy_card_search,
    filter_editable_field_definitions,
    filter_fields_by_definitions,
    skipped_field_ids,
)
from pydantic import ValidationError

from pipefy_cli.commands._common import (
    _CARDS_PAGE_SIZE_MAX,
    _CARDS_PAGE_SIZE_MIN,
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    format_card_get_transport_query_error,
    parse_json_object,
    parse_json_value,
    resource_id_argument,
    run_cli_command,
    validate_cards_page_size,
    validate_optional_resource_id,
)

card_app = typer.Typer(help="Card operations.", no_args_is_help=True)
comment_app = typer.Typer(help="Card comments.", no_args_is_help=True)


def _parse_card_search_json(raw: str | None) -> CardSearch | None:
    """Parse ``--search`` into a ``CardSearch`` (unknown keys dropped, MCP-aligned)."""
    if raw is None or raw.strip() == "":
        return None
    parsed = parse_json_value(raw, "--search")
    if not isinstance(parsed, dict):
        raise typer.BadParameter("--search must be a JSON object")
    return copy_card_search(parsed)


def _parse_fields_json(raw: str | None) -> dict[str, Any] | list[dict[str, Any]] | None:
    if raw is None or raw.strip() == "":
        return None
    parsed = parse_json_value(raw, "--fields")
    if isinstance(parsed, dict | list):
        return parsed
    raise typer.BadParameter("--fields must be a JSON object or array")


def _apply_create_card_title_warning(
    result: dict[str, Any], *, requested_title: str | None
) -> dict[str, Any]:
    if not requested_title:
        return result
    card_node = (result.get("createCard") or {}).get("card")
    if not isinstance(card_node, dict):
        return result
    if card_node.get("title") == requested_title:
        return result
    warned = dict(result)
    warned["title_warning"] = (
        "Card created but title was not applied as expected "
        f"(response title={card_node.get('title')!r}, requested={requested_title!r})."
    )
    return warned


def _parse_field_updates_json(raw: str | None) -> list[dict[str, Any]] | None:
    if raw is None or raw.strip() == "":
        return None
    parsed = parse_json_value(raw, "--field-updates")
    if not isinstance(parsed, list):
        raise typer.BadParameter("--field-updates must be a JSON array")
    return parsed


def _split_csv_ids(raw: str | None) -> list[str | int] | None:
    if raw is None or not raw.strip():
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return None
    out: list[str | int] = []
    for p in parts:
        if p.isdigit():
            out.append(int(p))
        else:
            out.append(p)
    return out


@card_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def card_get(
    ctx: typer.Context,
    card_id: str = resource_id_argument(help="Card id."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
    include_fields: bool = typer.Option(
        False,
        "--include-fields",
        help="Include custom field name/value pairs on the card.",
    ),
) -> None:
    """Fetch a card by id."""

    async def factory(client: PipefyClient):
        return await client.get_card(card_id, include_fields=include_fields)

    run_cli_command(
        ctx,
        json_out,
        factory,
        format_transport_query_error=format_card_get_transport_query_error,
    )


@card_app.command("list")
def card_list(
    ctx: typer.Context,
    pipe_id: str = typer.Option(..., "--pipe", help="Pipe id whose cards to load."),
    title: str | None = typer.Option(
        None,
        "--title",
        "-t",
        help="Filter by title substring (merged into search; same shortcut as MCP get_cards).",
    ),
    search_json: str | None = typer.Option(
        None,
        "--search",
        help="Optional JSON object: CardSearch keys (title, assignee_ids, label_ids, ignore_ids, include_done, inbox_emails_read). Unknown keys are ignored.",
    ),
    include_fields: bool = typer.Option(
        False,
        "--include-fields",
        help="Include each card's custom fields (name, value).",
    ),
    first: int | None = typer.Option(
        None,
        "--first",
        help=f"Max cards per page ({_CARDS_PAGE_SIZE_MIN}-{_CARDS_PAGE_SIZE_MAX}).",
    ),
    after: str | None = typer.Option(
        None,
        "--after",
        help="Pagination cursor (pageInfo.endCursor from a previous page).",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """List cards in a pipe (get_cards): browse, filter, and paginate.

    Use ``card find`` when matching a single custom field value (find_cards).
    """

    search_from_json = _parse_card_search_json(search_json)
    merged: CardSearch = dict(search_from_json) if search_from_json is not None else {}
    if title is not None and title.strip():
        merged["title"] = title.strip()
    effective_search: CardSearch | None = merged if merged else None
    first_validated = validate_cards_page_size(first)

    async def factory(client: PipefyClient):
        return await client.get_cards(
            pipe_id,
            effective_search,
            include_fields=include_fields,
            first=first_validated,
            after=after,
        )

    run_cli_command(ctx, json_out, factory)


@card_app.command("find")
def card_find(
    ctx: typer.Context,
    pipe_id: str = typer.Option(..., "--pipe", help="Pipe id to search in."),
    field_id: str = typer.Option(
        ...,
        "--field",
        help="Field id (slug) from start form or phase fields.",
    ),
    field_value: str = typer.Option(
        ...,
        "--value",
        help="Value to match for that field.",
    ),
    include_fields: bool = typer.Option(
        False,
        "--include-fields",
        help="Include each card's custom fields.",
    ),
    first: int | None = typer.Option(
        None,
        "--first",
        help="Max cards per page.",
    ),
    after: str | None = typer.Option(
        None,
        "--after",
        help="Pagination cursor (pageInfo.endCursor).",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Find cards in a pipe where a custom field equals a value."""

    async def factory(client: PipefyClient):
        return await client.find_cards(
            pipe_id,
            field_id,
            field_value,
            include_fields=include_fields,
            first=first,
            after=after,
        )

    run_cli_command(ctx, json_out, factory)


@card_app.command("create", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def card_create(
    ctx: typer.Context,
    pipe_id: str = resource_id_argument(help="Pipe id."),
    title: str | None = typer.Option(
        None,
        "--title",
        "-t",
        help="Optional title (sent on CreateCardInput when set).",
    ),
    phase_id: str | None = typer.Option(
        None,
        "--phase-id",
        help=(
            "Target phase id (CreateCardInput.phase_id). "
            "Creates the card in that phase instead of the start form."
        ),
    ),
    fields_json: str | None = typer.Option(
        None,
        "--fields",
        help="JSON object or array: field values for createCard.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Create a card in a pipe (start-form or phase fields via --fields JSON when required)."""

    fields = _parse_fields_json(fields_json)
    phase_id = validate_optional_resource_id(phase_id, "phase_id")

    async def factory(client: PipefyClient):
        payload = fields if fields is not None else {}
        create_kwargs: dict[str, Any] = {}
        if phase_id is not None:
            create_kwargs["phase_id"] = phase_id
        if title:
            create_kwargs["title"] = title
        result = await client.create_card(pipe_id, payload, **create_kwargs)
        return _apply_create_card_title_warning(result, requested_title=title)

    run_cli_command(ctx, json_out, factory)


@card_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def card_update(
    ctx: typer.Context,
    card_id: str = resource_id_argument(help="Card id."),
    title: str | None = typer.Option(None, "--title", "-t"),
    due_date: str | None = typer.Option(None, "--due-date"),
    assignee_ids: str | None = typer.Option(
        None,
        "--assignee-ids",
        help="Comma-separated assignee user ids.",
    ),
    label_ids: str | None = typer.Option(
        None,
        "--label-ids",
        help="Comma-separated label ids.",
    ),
    field_updates_json: str | None = typer.Option(
        None,
        "--field-updates",
        help=(
            "JSON array of field update objects for updateFieldsValues. "
            'Each object: {"field_id" (or "fieldId"): "<slug>", "value": <v>, '
            '"operation": "ADD"|"REMOVE"|"REPLACE" (optional, default REPLACE)}. '
            "For connector/connection fields, prefer ADD/REMOVE with related card ids."
        ),
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Update a card (title, assignees, labels, due date, and/or field updates)."""

    field_updates = _parse_field_updates_json(field_updates_json)

    async def factory(client: PipefyClient):
        return await client.update_card(
            card_id,
            title=title,
            assignee_ids=_split_csv_ids(assignee_ids),
            label_ids=_split_csv_ids(label_ids),
            due_date=due_date,
            field_updates=field_updates,
        )

    run_cli_command(ctx, json_out, factory)


@card_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def card_delete(
    ctx: typer.Context,
    card_id: str = resource_id_argument(help="Card id."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete a card permanently."""

    confirm_destructive(yes=yes, description=f"card {card_id}")

    async def factory(client: PipefyClient):
        return await client.delete_card(card_id)

    run_cli_command(ctx, json_out, factory)


@card_app.command("move", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def card_move(
    ctx: typer.Context,
    card_id: str = resource_id_argument(help="Card id."),
    phase_id: str = typer.Option(
        ...,
        "--phase",
        help="Destination phase id.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Move a card to another phase."""

    async def factory(client: PipefyClient):
        return await client.move_card_to_phase(card_id, phase_id)

    run_cli_command(ctx, json_out, factory)


@card_app.command("fill", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def card_fill(
    ctx: typer.Context,
    card_id: str = resource_id_argument(help="Card id."),
    phase_id: str = typer.Option(
        ...,
        "--phase",
        help="Phase id whose fields to fill.",
    ),
    fields_json: str = typer.Option(
        ...,
        "--fields",
        help=(
            'JSON object of field id to value, e.g. \'{"campo":"v"}\'. '
            "For ad-hoc updates without phase discovery, use "
            "`card update --field-updates` (JSON array)."
        ),
    ),
    required_only: bool = typer.Option(
        False,
        "--required-only",
        help="Only load required phase fields when resolving editable field ids.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Fill phase fields on a card (non-interactive).

    Filters ``--fields`` to editable phase field IDs before ``update_card``.
    Stricter than MCP ``fill_card_phase_fields`` when the phase reports no
    editable fields (CLI no-ops; MCP may pass values through unfiltered).
    """

    fields = parse_json_object(fields_json, "--fields") or {}

    async def factory(client: PipefyClient):
        if not fields:
            return {"success": True, "message": "No fields to update."}

        phase_fields_result = await client.get_phase_fields(phase_id, required_only)
        expected_fields = filter_editable_field_definitions(
            phase_fields_result.get("fields", [])
        )
        field_data = filter_fields_by_definitions(fields, expected_fields)
        dropped = skipped_field_ids(fields, field_data)
        if not field_data:
            result: dict[str, Any] = {
                "success": True,
                "message": "No fields to update.",
            }
            if dropped:
                result["skipped_field_ids"] = dropped
            return result
        field_updates = [
            {"field_id": field_id, "value": value}
            for field_id, value in field_data.items()
        ]
        api_response = await client.update_card(card_id, field_updates=field_updates)
        if dropped:
            return {**api_response, "skipped_field_ids": dropped}
        return api_response

    run_cli_command(ctx, json_out, factory)


@comment_app.command("add", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def card_comment_add(
    ctx: typer.Context,
    card_id: str = resource_id_argument(help="Card id."),
    text: str = typer.Argument(..., help="Comment body (1-1000 characters)."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Add a text comment to a card."""

    try:
        validated = CommentInput(card_id=card_id, text=text)
    except ValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc

    async def factory(client: PipefyClient):
        return await client.add_card_comment(validated.card_id, validated.text)

    run_cli_command(ctx, json_out, factory)


@comment_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def card_comment_update(
    ctx: typer.Context,
    comment_id: str = resource_id_argument(help="Comment id."),
    text: str = typer.Argument(..., help="New comment text."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Update an existing comment by id."""

    try:
        validated = UpdateCommentInput(comment_id=comment_id, text=text)
    except ValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc

    async def factory(client: PipefyClient):
        return await client.update_comment(validated.comment_id, validated.text)

    run_cli_command(ctx, json_out, factory)


@comment_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def card_comment_delete(
    ctx: typer.Context,
    comment_id: str = resource_id_argument(help="Comment id."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete a comment by id."""

    try:
        validated = DeleteCommentInput(comment_id=comment_id)
    except ValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc

    confirm_destructive(yes=yes, description=f"comment {validated.comment_id}")

    async def factory(client: PipefyClient):
        return await client.delete_comment(validated.comment_id)

    run_cli_command(ctx, json_out, factory)


card_app.add_typer(comment_app, name="comment")
