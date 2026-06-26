"""Organization metadata (read-only)."""

from __future__ import annotations

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    run_cli_command,
    settings_and_token,
    validate_positional_id,
)

org_app = typer.Typer(help="Organization operations.", no_args_is_help=True)

_MISSING_ORG_ID = (
    "Missing organization id. Pass ORGANIZATION_ID as the first argument, set "
    "PIPEFY_ORG_ID in the environment, or obtain an id from "
    "`pipefy pipe list --json` (organizations[].id)."
)


def _optional_org_id(value: str | None) -> str | None:
    if value is None:
        return None
    return validate_positional_id(value)


@org_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def org_get(
    ctx: typer.Context,
    organization_id: str | None = typer.Argument(
        None,
        help=(
            "Numeric organization id. Omit when PIPEFY_ORG_ID is set "
            "(see docs/config.md)."
        ),
        callback=_optional_org_id,
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Fetch organization details (``get_organization``)."""

    client_settings, _token = settings_and_token(ctx)
    resolved = (organization_id or "").strip()
    if not resolved:
        env_default = client_settings.org_id
        resolved = env_default.strip() if env_default else ""

    if not resolved:
        typer.echo(_MISSING_ORG_ID, err=True)
        raise typer.Exit(2)

    oid = resolved

    async def factory(client: PipefyClient):
        return await client.get_organization(oid)

    run_cli_command(ctx, json_out, factory)
