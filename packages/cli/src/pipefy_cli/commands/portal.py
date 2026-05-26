"""Portal subcommands."""

from __future__ import annotations

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    parse_json_object,
    parse_json_value,
    resource_id_argument,
    run_cli_command,
)

portal_app = typer.Typer(help="Portal operations.", no_args_is_help=True)
page_app = typer.Typer(help="Portal page operations.", no_args_is_help=True)
layout_app = typer.Typer(help="Portal page layout.", no_args_is_help=True)


def _require_non_empty_portal_uuid(portal_uuid: str) -> str:
    """Reject blank portal UUIDs before SDK calls."""
    if not portal_uuid.strip():
        raise typer.BadParameter("Portal UUID must be non-empty.")
    return portal_uuid.strip()


def _reject_blank_optional_string(value: str | None, flag: str) -> None:
    """Reject whitespace-only optional string flags on update."""
    if value is not None and not value.strip():
        raise typer.BadParameter(f"{flag}, when provided, must be non-empty.")


def _validate_sort_page_id_item(value: object) -> str:
    """Validate one page UUID from ``--page-ids`` or ``--ids-json`` before a sort write."""
    if isinstance(value, bool) or value is None:
        raise typer.BadParameter(
            "Each page UUID must be a non-empty string or positive integer."
        )
    if isinstance(value, (dict, list)):
        raise typer.BadParameter(
            "Each page UUID must be a non-empty string or positive integer."
        )
    if not isinstance(value, (str, int)):
        raise typer.BadParameter(
            "Each page UUID must be a non-empty string or positive integer."
        )
    cleaned = str(value).strip() if isinstance(value, int) else value.strip()
    if not cleaned:
        raise typer.BadParameter(
            "Each page UUID must be a non-empty string or positive integer."
        )
    if cleaned.startswith("-") and cleaned[1:].isdigit():
        raise typer.BadParameter("Each page UUID must be a positive integer.")
    if cleaned.isdigit() and int(cleaned) <= 0:
        raise typer.BadParameter("Each page UUID must be a positive integer.")
    return cleaned


def _reject_duplicate_sort_page_ids(page_ids: list[str]) -> None:
    """Reject duplicate page identifiers before ``sortPages``."""
    if len(set(page_ids)) != len(page_ids):
        raise typer.BadParameter("Page UUID list must not contain duplicates.")


def _parse_page_ids_for_sort(
    page_ids_csv: str | None,
    ids_json: str | None,
) -> list[str]:
    """Resolve ordered page UUIDs from ``--page-ids`` or ``--ids-json``."""
    if page_ids_csv is not None and page_ids_csv.strip():
        parts = [p.strip() for p in page_ids_csv.split(",") if p.strip()]
        if not parts:
            raise typer.BadParameter("--page-ids must list at least one page UUID.")
        ordered = [_validate_sort_page_id_item(part) for part in parts]
        _reject_duplicate_sort_page_ids(ordered)
        return ordered
    if ids_json is not None and ids_json.strip():
        parsed = parse_json_value(ids_json, "--ids-json")
        if not isinstance(parsed, list):
            raise typer.BadParameter("--ids-json must be a JSON array of page UUIDs.")
        if not parsed:
            raise typer.BadParameter("--ids-json must list at least one page UUID.")
        ordered = [_validate_sort_page_id_item(item) for item in parsed]
        _reject_duplicate_sort_page_ids(ordered)
        return ordered
    raise typer.BadParameter(
        "Provide --page-ids or --ids-json with at least one page UUID."
    )


@portal_app.command("list")
def portal_list(
    ctx: typer.Context,
    organization_uuid: str = typer.Option(
        ...,
        "--organization-uuid",
        help="Organization UUID, or numeric organization id (string).",
    ),
    search_term: str | None = typer.Option(
        None,
        "--search-term",
        help="Optional portal name filter.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """List portals for an organization."""

    async def factory(client: PipefyClient):
        return await client.list_portals(organization_uuid, search_term=search_term)

    run_cli_command(ctx, json_out, factory)


@portal_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def portal_get(
    ctx: typer.Context,
    portal_uuid: str = resource_id_argument(help="Portal UUID."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Fetch a portal by UUID."""

    portal_uuid = _require_non_empty_portal_uuid(portal_uuid)

    async def factory(client: PipefyClient):
        return await client.get_portal(portal_uuid)

    run_cli_command(ctx, json_out, factory)


@portal_app.command("create")
def portal_create(
    ctx: typer.Context,
    organization_uuid: str = typer.Option(
        ...,
        "--organization-uuid",
        help="Organization UUID, or numeric organization id (string).",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Create or fetch the organization's main portal (idempotent)."""

    async def factory(client: PipefyClient):
        return await client.create_portal(organization_uuid)

    run_cli_command(ctx, json_out, factory)


@portal_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def portal_update(
    ctx: typer.Context,
    portal_uuid: str = resource_id_argument(help="Portal UUID."),
    name: str | None = typer.Option(None, "--name", help="Portal display name."),
    visibility: str | None = typer.Option(
        None,
        "--visibility",
        help="Portal visibility: internal, private, or public.",
    ),
    color: str | None = typer.Option(None, "--color", help="Theme color."),
    icon: str | None = typer.Option(None, "--icon", help="Icon identifier."),
    display_pipefy_header: bool | None = typer.Option(
        None,
        "--display-pipefy-header/--no-display-pipefy-header",
        help="Show or hide the Pipefy header.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Update portal metadata (pass at least one attribute)."""

    portal_uuid = _require_non_empty_portal_uuid(portal_uuid)

    if all(x is None for x in (name, visibility, color, icon, display_pipefy_header)):
        raise typer.BadParameter(
            "Provide at least one of: --name, --visibility, --color, --icon, "
            "--display-pipefy-header / --no-display-pipefy-header."
        )

    _reject_blank_optional_string(name, "--name")
    _reject_blank_optional_string(color, "--color")
    _reject_blank_optional_string(icon, "--icon")

    async def factory(client: PipefyClient):
        update_kwargs: dict[str, str | bool] = {}
        if name is not None:
            update_kwargs["name"] = name.strip()
        if visibility is not None:
            update_kwargs["visibility"] = visibility
        if color is not None:
            update_kwargs["color"] = color.strip()
        if icon is not None:
            update_kwargs["icon"] = icon.strip()
        if display_pipefy_header is not None:
            update_kwargs["display_pipefy_header"] = display_pipefy_header
        return await client.update_portal(portal_uuid, **update_kwargs)

    run_cli_command(ctx, json_out, factory)


@portal_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def portal_delete(
    ctx: typer.Context,
    portal_uuid: str = resource_id_argument(help="Portal UUID."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip interactive confirmation.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Delete a portal permanently."""

    portal_uuid = _require_non_empty_portal_uuid(portal_uuid)
    confirm_destructive(yes=yes, description=f"portal {portal_uuid}")

    async def factory(client: PipefyClient):
        return await client.delete_portal(portal_uuid)

    run_cli_command(ctx, json_out, factory)


@page_app.command("create")
def portal_page_create(
    ctx: typer.Context,
    portal_uuid: str = typer.Option(
        ...,
        "--portal-uuid",
        help="Parent portal interface UUID.",
    ),
    title: str = typer.Option(..., "--title", help="Page title."),
    description: str | None = typer.Option(
        None,
        "--description",
        help="Optional page description.",
    ),
    index: int | None = typer.Option(
        None,
        "--index",
        min=0,
        help="Optional sort index (non-negative).",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Create a portal page (bootstrap template when elements omitted on the API)."""

    portal_uuid = _require_non_empty_portal_uuid(portal_uuid)
    _reject_blank_optional_string(title, "--title")
    _reject_blank_optional_string(description, "--description")

    async def factory(client: PipefyClient):
        return await client.create_portal_page(
            portal_uuid,
            title.strip(),
            description=description.strip() if description is not None else None,
            index=index,
        )

    run_cli_command(ctx, json_out, factory)


@page_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def portal_page_update(
    ctx: typer.Context,
    portal_uuid: str = resource_id_argument(help="Parent portal interface UUID."),
    page_uuid: str = resource_id_argument(help="Page UUID."),
    title: str | None = typer.Option(None, "--title", help="New page title."),
    description: str | None = typer.Option(
        None,
        "--description",
        help="New page description.",
    ),
    index: int | None = typer.Option(
        None,
        "--index",
        min=0,
        help="New sort index (non-negative).",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Update portal page metadata (pass at least one attribute)."""

    portal_uuid = _require_non_empty_portal_uuid(portal_uuid)
    page_uuid = _require_non_empty_portal_uuid(page_uuid)

    if all(x is None for x in (title, description, index)):
        raise typer.BadParameter(
            "Provide at least one of: --title, --description, --index."
        )

    _reject_blank_optional_string(title, "--title")
    _reject_blank_optional_string(description, "--description")

    async def factory(client: PipefyClient):
        update_kwargs: dict[str, str | int] = {}
        if title is not None:
            update_kwargs["title"] = title.strip()
        if description is not None:
            update_kwargs["description"] = description.strip()
        if index is not None:
            update_kwargs["index"] = index
        return await client.update_portal_page(
            portal_uuid,
            page_uuid,
            **update_kwargs,
        )

    run_cli_command(ctx, json_out, factory)


@page_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def portal_page_delete(
    ctx: typer.Context,
    portal_uuid: str = resource_id_argument(help="Parent portal interface UUID."),
    page_uuid: str = resource_id_argument(help="Page UUID."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip interactive confirmation.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Delete a portal page permanently."""

    portal_uuid = _require_non_empty_portal_uuid(portal_uuid)
    page_uuid = _require_non_empty_portal_uuid(page_uuid)
    confirm_destructive(
        yes=yes,
        description=f"page {page_uuid} on portal {portal_uuid}",
    )

    async def factory(client: PipefyClient):
        return await client.delete_portal_page(portal_uuid, page_uuid)

    run_cli_command(ctx, json_out, factory)


@page_app.command("sort")
def portal_page_sort(
    ctx: typer.Context,
    portal_uuid: str = typer.Option(
        ...,
        "--portal-uuid",
        help="Parent portal interface UUID.",
    ),
    page_ids: str | None = typer.Option(
        None,
        "--page-ids",
        help="Comma-separated ordered page UUIDs.",
    ),
    ids_json: str | None = typer.Option(
        None,
        "--ids-json",
        help="JSON array of ordered page UUIDs.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Reorder portal pages."""

    portal_uuid = _require_non_empty_portal_uuid(portal_uuid)
    ordered_page_ids = _parse_page_ids_for_sort(page_ids, ids_json)

    async def factory(client: PipefyClient):
        return await client.sort_portal_pages(portal_uuid, ordered_page_ids)

    run_cli_command(ctx, json_out, factory)


@layout_app.command("update")
def portal_page_layout_update(
    ctx: typer.Context,
    page_id: str = typer.Option(..., "--page-id", help="Page UUID."),
    layout: str = typer.Option(
        ...,
        "--layout",
        help="Layout JSON for updatePageLayout.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Update a portal page grid layout."""

    page_id = _require_non_empty_portal_uuid(page_id)
    layout_obj = parse_json_object(layout, "--layout")
    if layout_obj is None:
        raise typer.BadParameter("--layout must be a JSON object.")

    async def factory(client: PipefyClient):
        return await client.update_portal_page_layout(page_id, layout_obj)

    run_cli_command(ctx, json_out, factory)


page_app.add_typer(layout_app, name="layout")
portal_app.add_typer(page_app, name="page")
