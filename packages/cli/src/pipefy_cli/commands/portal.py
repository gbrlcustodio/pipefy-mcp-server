"""Portal subcommands."""

from __future__ import annotations

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    resource_id_argument,
    run_cli_command,
)

portal_app = typer.Typer(help="Portal operations.", no_args_is_help=True)


def _require_non_empty_portal_uuid(portal_uuid: str) -> str:
    """Reject blank portal UUIDs before SDK calls."""
    if not portal_uuid.strip():
        raise typer.BadParameter("Portal UUID must be non-empty.")
    return portal_uuid.strip()


def _reject_blank_optional_string(value: str | None, flag: str) -> None:
    """Reject whitespace-only optional string flags on update."""
    if value is not None and not value.strip():
        raise typer.BadParameter(f"{flag}, when provided, must be non-empty.")


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
