"""AI Automations (generate_with_ai) via internal API."""

from __future__ import annotations

from typing import Any

import typer
from pipefy_sdk import (
    CreateAiAutomationInput,
    PipefyClient,
    UpdateAiAutomationInput,
)
from pipefy_sdk.ai_preflight import (
    filter_ai_automation_summaries,
    validate_ai_automation_prompt_sdk,
)
from pydantic import ValidationError

from pipefy_cli.commands._common import (
    confirm_destructive,
    parse_json_object,
    parse_json_value,
    run_cli_command,
)

ai_automation_app = typer.Typer(
    help="AI Automations (generate_with_ai; requires OAuth).",
    no_args_is_help=True,
)


def _require_ai_automation(client: PipefyClient) -> None:
    if not client.ai_automation_available:
        typer.echo(
            "AI Automation requires OAuth credentials "
            "(PIPEFY_OAUTH_CLIENT, PIPEFY_OAUTH_SECRET, PIPEFY_OAUTH_URL). "
            "Bearer --token mode does not attach the internal API client.",
            err=True,
        )
        raise typer.Exit(2)


def _raise_if_prompt_preflight_blocks(payload: dict[str, Any]) -> None:
    if not payload.get("success"):
        raise typer.BadParameter(str(payload.get("error") or "validate-prompt failed"))
    if not payload.get("valid"):
        problems = payload.get("problems") or []
        text = "\n".join(f"  - {p}" for p in problems) if problems else "(no details)"
        raise typer.BadParameter(f"validate-prompt failed:\n{text}")


def _parse_field_ids(raw: str) -> list[str]:
    parsed = parse_json_value(raw, "--field-ids")
    if not isinstance(parsed, list) or not all(isinstance(x, str) for x in parsed):
        raise typer.BadParameter("--field-ids must be a JSON array of strings")
    return list(parsed)


@ai_automation_app.command("list")
def ai_automation_list(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Pipe id."),
    organization: str | None = typer.Option(
        None, "--organization", "--org", help="Optional organization id."
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List AI automations for a pipe (``get_ai_automations`` / filtered ``get_automations``)."""

    async def factory(client: PipefyClient):
        rows = await client.get_automations(
            organization_id=organization,
            pipe_id=pipe,
        )
        filtered = filter_ai_automation_summaries(rows or [])
        return {"success": True, "data": filtered, "message": "AI automations listed."}

    run_cli_command(ctx, json_out, factory)


@ai_automation_app.command("get")
def ai_automation_get(
    ctx: typer.Context,
    automation_id: str = typer.Argument(..., help="Automation rule id."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Load one automation row (``get_ai_automation`` / ``get_automation``)."""

    async def factory(client: PipefyClient):
        row = await client.get_automation(automation_id)
        if row is None:
            return {
                "success": False,
                "message": "No automation found for the given ID.",
            }
        return {"success": True, "message": "AI automation retrieved.", "data": row}

    run_cli_command(ctx, json_out, factory)


@ai_automation_app.command("validate-prompt")
def ai_automation_validate_prompt(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Pipe id."),
    prompt: str = typer.Option(
        ..., "--prompt", help="Prompt with %{internal_id} tokens."
    ),
    field_ids: str = typer.Option(
        ..., "--field-ids", help="JSON array of output field internal ids."
    ),
    event_id: str | None = typer.Option(
        None,
        "--event-id",
        help="Optional trigger id to validate against the pipe catalog.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Pre-flight prompt validation (``validate_ai_automation_prompt``)."""
    fids = _parse_field_ids(field_ids)

    async def factory(client: PipefyClient):
        return await validate_ai_automation_prompt_sdk(
            client, pipe.strip(), prompt, fids, event_id
        )

    run_cli_command(ctx, json_out, factory)


@ai_automation_app.command("create")
def ai_automation_create(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Pipe id."),
    name: str = typer.Option(..., "--name", "-n", help="Automation name."),
    event_id: str = typer.Option(..., "--event-id", help="Trigger event id."),
    prompt: str = typer.Option(
        ..., "--prompt", help="AI prompt with %{internal_id} refs."
    ),
    field_ids: str = typer.Option(
        ..., "--field-ids", help="JSON array of output field ids."
    ),
    action_repo: str | None = typer.Option(
        None, "--action-repo", help="Optional action repo id (defaults to --pipe)."
    ),
    skills_ids: str | None = typer.Option(
        None, "--skills-ids", help="Optional JSON array of skill id strings."
    ),
    event_params: str | None = typer.Option(
        None, "--event-params", help="Optional JSON object."
    ),
    condition: str | None = typer.Option(
        None, "--condition", help="Optional JSON object (omit for default placeholder)."
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Create an AI automation (``create_ai_automation``)."""
    fids = _parse_field_ids(field_ids)
    ep = parse_json_object(event_params, "--event-params")
    cond = parse_json_object(condition, "--condition")
    skills_raw = parse_json_value(skills_ids, "--skills-ids") if skills_ids else None
    skills: list[str] = []
    if skills_raw is not None:
        if not isinstance(skills_raw, list) or not all(
            isinstance(x, str) for x in skills_raw
        ):
            raise typer.BadParameter("--skills-ids must be a JSON array of strings")
        skills = list(skills_raw)

    async def factory(client: PipefyClient):
        _require_ai_automation(client)
        pre = await validate_ai_automation_prompt_sdk(
            client, pipe.strip(), prompt, fids, event_id
        )
        _raise_if_prompt_preflight_blocks(pre)
        try:
            kwargs: dict[str, Any] = {
                "name": name.strip(),
                "event_id": event_id.strip(),
                "pipe_id": pipe.strip(),
                "action_repo_id": action_repo.strip() if action_repo else None,
                "prompt": prompt,
                "field_ids": fids,
                "skills_ids": skills,
            }
            if ep is not None:
                kwargs["event_params"] = ep
            if cond is not None:
                kwargs["condition"] = cond
            inp = CreateAiAutomationInput(**kwargs)
        except ValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        return await client.create_ai_automation(inp)

    run_cli_command(ctx, json_out, factory)


@ai_automation_app.command("update")
def ai_automation_update(
    ctx: typer.Context,
    automation_id: str = typer.Argument(..., help="Automation rule id."),
    pipe: str = typer.Option(
        ...,
        "--pipe",
        help="Pipe id for validate-prompt pre-flight.",
    ),
    prompt: str | None = typer.Option(
        None, "--prompt", help="New prompt (for pre-flight + patch)."
    ),
    field_ids: str | None = typer.Option(
        None,
        "--field-ids",
        help="JSON array of output field ids (for pre-flight + patch).",
    ),
    name: str | None = typer.Option(None, "--name", "-n"),
    patch_active: bool | None = typer.Option(
        None,
        "--patch-active/--no-patch-active",
        help="Toggle the enabled flag; omit both flags to leave unchanged.",
    ),
    skills_ids: str | None = typer.Option(None, "--skills-ids"),
    event_params: str | None = typer.Option(None, "--event-params"),
    condition: str | None = typer.Option(None, "--condition"),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Update an AI automation (``update_ai_automation``)."""
    if prompt is None or field_ids is None:
        raise typer.BadParameter(
            "update requires --prompt and --field-ids for validate-prompt pre-flight "
            "(pass current values if unchanged)."
        )
    fids = _parse_field_ids(field_ids)
    ep = parse_json_object(event_params, "--event-params")
    cond = parse_json_object(condition, "--condition")
    skills_raw = parse_json_value(skills_ids, "--skills-ids") if skills_ids else None
    skills: list[str] | None = None
    if skills_raw is not None:
        if not isinstance(skills_raw, list) or not all(
            isinstance(x, str) for x in skills_raw
        ):
            raise typer.BadParameter("--skills-ids must be a JSON array of strings")
        skills = list(skills_raw)

    async def factory(client: PipefyClient):
        _require_ai_automation(client)
        row = await client.get_automation(automation_id)
        if row is None:
            return {"success": False, "message": "Automation not found."}
        ev = str(row.get("event_id") or row.get("eventId") or "")
        pre = await validate_ai_automation_prompt_sdk(
            client,
            pipe.strip(),
            prompt,
            fids,
            ev or None,
        )
        _raise_if_prompt_preflight_blocks(pre)
        try:
            kwargs_u: dict[str, Any] = {
                "automation_id": str(automation_id).strip(),
                "name": name.strip() if name else None,
                "active": patch_active,
                "prompt": prompt,
                "field_ids": fids,
                "skills_ids": skills,
            }
            if ep is not None:
                kwargs_u["event_params"] = ep
            if cond is not None:
                kwargs_u["condition"] = cond
            inp = UpdateAiAutomationInput(**kwargs_u)
        except ValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        return await client.update_ai_automation(inp)

    run_cli_command(ctx, json_out, factory)


@ai_automation_app.command("delete")
def ai_automation_delete(
    ctx: typer.Context,
    automation_id: str = typer.Argument(..., help="Automation rule id."),
    yes: bool = typer.Option(False, "--yes", help="Skip interactive confirmation."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete an AI automation (``delete_ai_automation`` / ``delete_automation``)."""
    confirm_destructive(
        yes=yes, description=f"AI automation {automation_id}", verb="delete"
    )

    async def factory(client: PipefyClient):
        return await client.delete_automation(automation_id)

    run_cli_command(ctx, json_out, factory)
