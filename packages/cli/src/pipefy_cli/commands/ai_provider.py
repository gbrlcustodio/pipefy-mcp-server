"""LLM providers (organization-scoped): discovery reads and custom-provider writes.

Provider configuration is secret-bearing and is supplied only via a local JSON
file (``--config-file``), never inline, so secrets never land in shell history or
argument logs. Create/update are gated on the read-access probe (treated as clean
only when it is ``ok`` **and** carries no ``problem``); delete requires a
confirmation. Writes require the ``manage_ai_providers`` organization permission
and an eligible plan — a stronger entitlement than the probe proves.
"""

from __future__ import annotations

from pathlib import Path

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import (
    confirm_destructive,
    probe_gate,
    run_cli_command,
)

ai_provider_app = typer.Typer(
    help="LLM providers (organization-scoped: discovery reads and provider writes).",
    no_args_is_help=True,
)
default_app = typer.Typer(
    help="Organization default LLM provider (get / set / reset).",
    no_args_is_help=True,
)
ai_provider_app.add_typer(default_app, name="default")

_ORG_UUID_HELP = "Organization UUID (not the numeric ID; `pipefy org get` shows both)."
_ORG_ID_HELP = "Numeric organization ID (not the UUID; `pipefy org get` shows both)."
_CONFIG_FILE_HELP = (
    "Local JSON file with the provider configuration object (secrets stay in the "
    "file; never passed inline). Supports ~ expansion."
)


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


@ai_provider_app.command("create")
def ai_provider_create(
    ctx: typer.Context,
    org_uuid: str = typer.Option(..., "--org-uuid", help=_ORG_UUID_HELP),
    name: str = typer.Option(..., "--name", help="Display name (required)."),
    config_file: Path = typer.Option(
        ..., "--config-file", "-f", help=_CONFIG_FILE_HELP
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Create a custom (BYOM) LLM provider (``create_llm_provider``).

    Configuration is read from the local JSON file, never inline; the created
    provider is returned without its configuration. The ``provider`` key in the
    file selects the vendor. Gated on the read-access probe. Requires the
    ``manage_ai_providers`` organization permission and an eligible plan.
    """

    async def factory(client: PipefyClient):
        gate = probe_gate(await client.validate_llm_provider_access(org_uuid))
        if gate is not None:
            return gate
        provider = await client.create_llm_provider(
            org_uuid, name=name, configuration_file_path=config_file
        )
        return {"success": True, "provider": provider}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@ai_provider_app.command("update")
def ai_provider_update(
    ctx: typer.Context,
    provider_id: str = typer.Option(
        ..., "--id", help="Provider ID to update (from `pipefy ai-provider list`)."
    ),
    org_uuid: str = typer.Option(..., "--org-uuid", help=_ORG_UUID_HELP),
    config_file: Path = typer.Option(
        ..., "--config-file", "-f", help=_CONFIG_FILE_HELP
    ),
    name: str | None = typer.Option(None, "--name", help="New name (non-blank)."),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Update a custom (BYOM) LLM provider (``update_llm_provider``).

    Full configuration replacement: the file must hold the complete configuration
    object. To keep an existing secret without re-supplying it, leave the
    redaction placeholder that ``pipefy ai-provider list`` returned in place — the
    backend preserves the stored secret for any value left as the placeholder. To
    rotate a secret, put its new real value in the file. Gated on the read-access
    probe.
    """

    async def factory(client: PipefyClient):
        gate = probe_gate(await client.validate_llm_provider_access(org_uuid))
        if gate is not None:
            return gate
        provider = await client.update_llm_provider(
            provider_id, org_uuid, configuration_file_path=config_file, name=name
        )
        return {"success": True, "provider": provider}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@ai_provider_app.command("delete")
def ai_provider_delete(
    ctx: typer.Context,
    provider_id: str = typer.Option(..., "--id", help="Provider ID to delete."),
    org_uuid: str = typer.Option(..., "--org-uuid", help=_ORG_UUID_HELP),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Delete a custom (BYOM) LLM provider permanently (``delete_llm_provider``).

    Check `pipefy ai-provider dependencies` first — owners that still reference
    the provider are blockers.
    """
    confirm_destructive(yes=yes, description=f"LLM provider {provider_id}")

    async def factory(client: PipefyClient):
        return await client.delete_llm_provider(provider_id, org_uuid)

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@ai_provider_app.command("set-active-status")
def ai_provider_set_active_status(
    ctx: typer.Context,
    provider_id: str = typer.Option(
        ..., "--id", help="Provider ID whose active status to set."
    ),
    active: bool = typer.Option(
        ...,
        "--active/--inactive",
        help="Activate (--active) or deactivate (--inactive) the provider.",
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Activate or deactivate a custom (BYOM) LLM provider (``set_llm_provider_active_status``).

    The provider's organization is resolved from the credential's own organization
    context, so no organization argument is needed — which means this needs a
    service-account credential bound to that organization (a bare personal token is
    denied). Deactivating a provider owners depend on can break them — check
    `pipefy ai-provider dependencies` first.
    """

    async def factory(client: PipefyClient):
        result = await client.set_llm_provider_active_status(provider_id, active=active)
        return {
            "success": bool(result.get("success")),
            "provider_id": provider_id,
            "active": active,
        }

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@default_app.command("set")
def ai_provider_default_set(
    ctx: typer.Context,
    org_id: str = typer.Option(..., "--org-id", help=_ORG_ID_HELP),
    provider_id: str | None = typer.Option(
        None, "--provider-id", help="Custom (BYOM) provider ID to make the default."
    ),
    system_provider_id: str | None = typer.Option(
        None, "--system-provider-id", help="System provider ID to make the default."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Set the organization's default LLM provider (``set_default_llm_provider``).

    Provide exactly one of --provider-id or --system-provider-id. Authorizes
    against the credential's own organization, so it needs a service-account
    credential bound to that organization (a bare personal token is denied); pass
    that same organization's numeric id as --org-id.
    """

    async def factory(client: PipefyClient):
        result = await client.set_default_llm_provider(
            org_id, provider_id=provider_id, system_provider_id=system_provider_id
        )
        return {"success": True, "active_provider": result}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@default_app.command("reset")
def ai_provider_default_reset(
    ctx: typer.Context,
    org_id: str = typer.Option(..., "--org-id", help=_ORG_ID_HELP),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Reset (clear) the organization's default LLM provider (``reset_default_llm_provider``).

    Reversible via `pipefy ai-provider default set`. Like that command, it
    authorizes against the credential's own organization, so it needs a
    service-account credential bound to that organization (a bare personal token
    is denied).
    """

    async def factory(client: PipefyClient):
        result = await client.reset_default_llm_provider(org_id)
        return {"success": bool(result.get("success")), "organization_id": org_id}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)
