"""LLM provider discovery (organization-scoped, read-only)."""

from __future__ import annotations

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import run_cli_command

ai_provider_app = typer.Typer(
    help="LLM providers (discovery reads; organization-scoped).",
    no_args_is_help=True,
)
default_app = typer.Typer(help="Default LLM provider.", no_args_is_help=True)
ai_provider_app.add_typer(default_app, name="default")

_ORG_UUID_HELP = "Organization UUID (not the numeric ID; `pipefy org get` shows both)."


@ai_provider_app.command("list")
def ai_provider_list(
    ctx: typer.Context,
    org_uuid: str = typer.Option(..., "--org-uuid", help=_ORG_UUID_HELP),
    only_active: bool = typer.Option(
        False,
        "--only-active",
        help="Only return active custom providers (system providers unaffected).",
    ),
    first: int = typer.Option(50, "--first", help="Page size."),
    after: str | None = typer.Option(
        None, "--after", help="Cursor from the previous page's page_info.endCursor."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """List custom (BYOM) and Pipefy-managed system LLM providers (``get_llm_providers``).

    Each provider carries ``type`` (``byom`` or ``system``); ``configuration``
    comes back with secret values redacted server-side. An empty system list
    can mean system models are not enabled for the organization.
    """

    async def factory(client: PipefyClient):
        result = await client.get_llm_providers(
            org_uuid, only_active=only_active, first=first, after=after
        )
        return {"success": True, **result}

    run_cli_command(ctx, json_out, factory)


@ai_provider_app.command("models")
def ai_provider_models(
    ctx: typer.Context,
    provider_name: str = typer.Option(
        ...,
        "--provider-name",
        help=(
            "Provider vendor: openai, azure_openai, amazon_bedrock, custom, "
            "google_vertex_ai, oracle_oci, or anthropic."
        ),
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """List the model names a provider vendor exposes (``get_available_ai_models``)."""

    async def factory(client: PipefyClient):
        models = await client.get_available_ai_models(provider_name)
        return {"success": True, "models": models}

    run_cli_command(ctx, json_out, factory)


@default_app.command("get")
def ai_provider_default_get(
    ctx: typer.Context,
    owner_id: str = typer.Option(
        ...,
        "--owner-id",
        help=(
            "Owner identifier. For --owner-type organization pass the numeric "
            "organization ID (not the UUID)."
        ),
    ),
    owner_type: str = typer.Option(
        "organization",
        "--owner-type",
        help="One of: organization (default), assistant, behavior.",
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Resolve the default LLM provider for an owner (``get_default_llm_provider``)."""

    async def factory(client: PipefyClient):
        provider = await client.get_default_llm_provider(
            owner_id, owner_type=owner_type
        )
        return {"success": True, "provider": provider}

    run_cli_command(ctx, json_out, factory)


@ai_provider_app.command("dependencies")
def ai_provider_dependencies(
    ctx: typer.Context,
    provider_id: str = typer.Option(
        ..., "--provider-id", help="Provider ID (from `pipefy ai-provider list`)."
    ),
    org_uuid: str = typer.Option(..., "--org-uuid", help=_ORG_UUID_HELP),
    first: int = typer.Option(50, "--first", help="Page size."),
    after: str | None = typer.Option(
        None, "--after", help="Cursor from the previous page's page_info.endCursor."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """List owners that depend on a provider (``get_llm_provider_dependencies``)."""

    async def factory(client: PipefyClient):
        result = await client.get_llm_provider_dependencies(
            provider_id, org_uuid, first=first, after=after
        )
        return {"success": True, **result}

    run_cli_command(ctx, json_out, factory)


@ai_provider_app.command("validate-access")
def ai_provider_validate_access(
    ctx: typer.Context,
    org_uuid: str = typer.Option(..., "--org-uuid", help=_ORG_UUID_HELP),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Probe LLM provider read access (``validate_llm_provider_access``).

    A green probe proves read access only, never write entitlement. Exits 1
    when the probe classifies a failure (permission denied / not found / other),
    after rendering the structured problem.
    """

    async def factory(client: PipefyClient):
        probe = await client.validate_llm_provider_access(org_uuid)
        return {"success": bool(probe.get("ok")), **probe}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)
