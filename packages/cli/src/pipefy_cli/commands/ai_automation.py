"""AI Automations (generate_with_ai) via Internal API."""

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
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    parse_json_object,
    parse_json_value,
    resource_id_argument,
    run_cli_command,
)

ai_automation_app = typer.Typer(
    help="AI Automations (generate_with_ai).",
    no_args_is_help=True,
)


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


def _extract_existing_prompt_and_field_ids(
    row: dict[str, Any],
) -> tuple[str | None, list[str] | None]:
    """Return ``(prompt, field_ids)`` from a ``generate_with_ai`` automation row.

    Returns ``(None, None)`` for non-AI rows or rows missing the ``aiParams`` block;
    callers must surface that as a clear user error.

    The row comes from ``get_automation``, whose query selects ``action_params`` (snake)
    with a nested ``aiParams`` / ``fieldIds`` (camel) block — one canonical key style.
    """
    action_params = row.get("action_params") or {}
    ai_params = action_params.get("aiParams") or {}
    prompt = ai_params.get("value")
    field_ids = ai_params.get("fieldIds")
    if not isinstance(prompt, str):
        prompt = None
    if isinstance(field_ids, list) and all(isinstance(x, str) for x in field_ids):
        return prompt, list(field_ids)
    return prompt, None


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


@ai_automation_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def ai_automation_get(
    ctx: typer.Context,
    automation_id: str = resource_id_argument(help="Automation rule id."),
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


@ai_automation_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def ai_automation_update(
    ctx: typer.Context,
    automation_id: str = resource_id_argument(help="Automation rule id."),
    pipe: str = typer.Option(
        ...,
        "--pipe",
        help="Pipe id for validate-prompt pre-flight.",
    ),
    prompt: str | None = typer.Option(
        None,
        "--prompt",
        help="New prompt; omit to keep the current value (re-used in pre-flight).",
    ),
    field_ids: str | None = typer.Option(
        None,
        "--field-ids",
        help=(
            "JSON array of output field ids; omit to keep the current values "
            "(re-used in pre-flight)."
        ),
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
    """Update an AI automation (``update_ai_automation``).

    ``--prompt`` and ``--field-ids`` are optional: when omitted the CLI reads
    the current values from the existing automation and re-uses them for the
    ``validate_ai_automation_prompt`` pre-flight. Only fields you pass
    explicitly are sent in the patch.
    """
    fids: list[str] | None = _parse_field_ids(field_ids) if field_ids else None
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
        row = await client.get_automation(automation_id)
        if row is None:
            return {"success": False, "message": "Automation not found."}
        existing_prompt, existing_fids = _extract_existing_prompt_and_field_ids(row)
        effective_prompt = prompt if prompt is not None else existing_prompt
        effective_fids = fids if fids is not None else existing_fids
        if not effective_prompt or not effective_fids:
            raise typer.BadParameter(
                "Could not infer current prompt / field_ids from the existing automation. "
                "Pass --prompt and --field-ids explicitly."
            )
        ev = str(row.get("event_id") or "")
        pre = await validate_ai_automation_prompt_sdk(
            client,
            pipe.strip(),
            effective_prompt,
            effective_fids,
            ev or None,
        )
        _raise_if_prompt_preflight_blocks(pre)
        try:
            kwargs_u: dict[str, Any] = {
                "automation_id": str(automation_id).strip(),
                "name": name.strip() if name else None,
                "active": patch_active,
                "skills_ids": skills,
            }
            if prompt is not None:
                kwargs_u["prompt"] = prompt
            if fids is not None:
                kwargs_u["field_ids"] = fids
            if ep is not None:
                kwargs_u["event_params"] = ep
            if cond is not None:
                kwargs_u["condition"] = cond
            inp = UpdateAiAutomationInput(**kwargs_u)
        except ValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc
        return await client.update_ai_automation(inp)

    run_cli_command(ctx, json_out, factory)


@ai_automation_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def ai_automation_delete(
    ctx: typer.Context,
    automation_id: str = resource_id_argument(help="Automation rule id."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip interactive confirmation."
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete an AI automation (``delete_ai_automation`` / ``delete_automation``)."""
    confirm_destructive(
        yes=yes, description=f"AI automation {automation_id}", verb="delete"
    )

    async def factory(client: PipefyClient):
        return await client.delete_automation(automation_id)

    run_cli_command(ctx, json_out, factory)
