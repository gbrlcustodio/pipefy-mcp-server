"""AI Agent operations (list, CRUD, logs, behavior validation)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import typer
from pipefy_sdk import (
    CreateAiAgentInput,
    PipefyClient,
    UpdateAiAgentInput,
)
from pipefy_sdk.ai_preflight import validate_ai_agent_behaviors_sdk
from pipefy_sdk.behavior_placeholders import (
    expand_behaviors_placeholders,
    normalize_pipefy_ai_instruction_tokens,
)
from pydantic import ValidationError

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    parse_json_value,
    resource_id_argument,
    run_cli_command,
)

agent_app = typer.Typer(help="AI Agents (repo-scoped).", no_args_is_help=True)
logs_app = typer.Typer(help="AI Agent execution logs.", no_args_is_help=True)
agent_app.add_typer(logs_app, name="logs")


def _parse_behaviors_json(raw: str) -> list[dict[str, Any]]:
    parsed = parse_json_value(raw, "--behaviors")
    if not isinstance(parsed, list):
        raise typer.BadParameter("--behaviors must be a JSON array")
    out = [b for b in parsed if isinstance(b, dict)]
    if not out:
        raise typer.BadParameter("--behaviors must contain at least one object")
    return out


def _raise_if_preflight_blocks(payload: dict[str, Any]) -> None:
    if not payload.get("success"):
        msg = payload.get("error") or payload.get("message") or "Validation failed"
        raise typer.BadParameter(str(msg))
    if not payload.get("valid"):
        problems = payload.get("problems") or []
        text = "\n".join(f"  - {p}" for p in problems) if problems else "(no details)"
        raise typer.BadParameter(f"validate-behaviors failed:\n{text}")


@agent_app.command("list")
def agent_list(
    ctx: typer.Context,
    repo: str = typer.Option(..., "--repo", help="Pipe UUID (repoUuid)."),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """List AI agents for a pipe (``get_ai_agents``)."""

    async def factory(client: PipefyClient):
        agents = await client.get_ai_agents(repo)
        return {"success": True, "agents": agents}

    run_cli_command(ctx, json_out, factory)


@agent_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def agent_get(
    ctx: typer.Context,
    uuid: str = resource_id_argument(help="Agent UUID."),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Fetch one AI agent (``get_ai_agent``)."""

    async def factory(client: PipefyClient):
        agent = await client.get_ai_agent(uuid)
        return {"success": True, "agent": agent}

    run_cli_command(ctx, json_out, factory)


@agent_app.command("create")
def agent_create(
    ctx: typer.Context,
    repo_uuid: str = typer.Option(..., "--repo-uuid", help="Pipe UUID."),
    name: str = typer.Option(..., "--name", "-n", help="Agent display name."),
    instruction: str = typer.Option(
        ...,
        "--instruction",
        help="Agent-level instruction (token-normalized).",
    ),
    behaviors: str = typer.Option(
        ...,
        "--behaviors",
        help="JSON array of behavior objects.",
    ),
    pipe: str = typer.Option(
        ...,
        "--pipe",
        help="Numeric pipe id for validate-behaviors pre-flight.",
    ),
    data_sources: str | None = typer.Option(
        None,
        "--data-sources",
        help="Optional JSON array of knowledge-source id strings.",
    ),
    active: bool = typer.Option(
        True,
        "--active/--inactive",
        help=(
            "Create enabled (default) or inactive. --inactive sets disabled_at on "
            "create and the chained update so the second step does not revive."
        ),
    ),
    strict_unknown: bool = typer.Option(
        True,
        "--strict/--no-strict",
        help=(
            "Pre-flight strictness: when --strict (default), unknown actionType values "
            "block; with --no-strict they become warnings only."
        ),
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Create and configure an AI agent (``create_ai_agent`` + ``update_ai_agent`` chain).

    Agents are active by default. Pass ``--inactive`` to start disabled. Confirm
    status from the response ``disabled_at`` / ``active`` fields. To change status
    later, use ``pipefy agent toggle`` (routine update preserves disabled state).
    """
    behavior_list = _parse_behaviors_json(behaviors)
    ds_raw = parse_json_value(data_sources, "--data-sources") if data_sources else None
    data_source_ids: list[str] = []
    if ds_raw is not None:
        if not isinstance(ds_raw, list) or not all(isinstance(x, str) for x in ds_raw):
            raise typer.BadParameter("--data-sources must be a JSON array of strings")
        data_source_ids = list(ds_raw)

    inst = normalize_pipefy_ai_instruction_tokens(instruction.strip())
    disabled_at = None if active else datetime.now(timezone.utc).isoformat()
    try:
        expanded = expand_behaviors_placeholders(behavior_list)
        validated = CreateAiAgentInput(
            name=name.strip(),
            repo_uuid=repo_uuid.strip(),
            instruction=inst,
            behaviors=expanded,
            data_source_ids=data_source_ids,
            disabled_at=disabled_at,
        )
    except ValidationError as exc:
        raise typer.BadParameter(str(exc)) from exc

    async def factory(client: PipefyClient):
        pre = await validate_ai_agent_behaviors_sdk(
            client,
            pipe.strip(),
            [b.model_dump(by_alias=True) for b in validated.behaviors],
            strict_unknown_action_types=strict_unknown,
        )
        _raise_if_preflight_blocks(pre)
        create_result = await client.create_ai_agent(validated)
        agent_uuid = create_result["agent_uuid"]
        update_input = UpdateAiAgentInput(
            uuid=agent_uuid,
            name=validated.name,
            repo_uuid=validated.repo_uuid,
            instruction=validated.instruction,
            behaviors=validated.behaviors,
            data_source_ids=validated.data_source_ids,
            disabled_at=validated.disabled_at,
            preserve_disabled_at=not active,
        )
        update_result = await client.update_ai_agent(update_input)
        result_disabled_at = update_result.get("disabled_at")
        out: dict[str, Any] = {
            "success": True,
            "agent_uuid": agent_uuid,
            "message": f"Created agent {agent_uuid}",
            "disabled_at": result_disabled_at,
            "active": update_result.get("active", result_disabled_at is None),
        }
        if pre.get("warnings"):
            out["preflight"] = pre
        return out

    run_cli_command(ctx, json_out, factory)


@agent_app.command("update")
def agent_update(
    ctx: typer.Context,
    uuid: str = typer.Option(..., "--uuid", help="Agent UUID."),
    name: str = typer.Option(..., "--name", "-n", help="Agent display name."),
    repo_uuid: str = typer.Option(..., "--repo-uuid", help="Pipe UUID."),
    instruction: str = typer.Option(
        ..., "--instruction", help="Agent-level instruction."
    ),
    behaviors: str = typer.Option(
        ..., "--behaviors", help="JSON array of behavior objects."
    ),
    pipe: str = typer.Option(
        ...,
        "--pipe",
        help="Numeric pipe id for validate-behaviors pre-flight.",
    ),
    data_sources: str | None = typer.Option(
        None,
        "--data-sources",
        help="Optional JSON array of knowledge-source id strings.",
    ),
    strict_unknown: bool = typer.Option(
        True,
        "--strict/--no-strict",
        help=(
            "Pre-flight strictness: --strict (default) blocks on unknown actionType "
            "values; --no-strict converts them to warnings."
        ),
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Replace AI agent configuration (``update_ai_agent``).

    Full-replace of behaviors; does not reactivate a disabled agent. Use
    ``pipefy agent toggle`` to change active status. Confirm status from the
    response ``disabled_at`` / ``active`` fields. To re-read via ``agent get``,
    use agent ``disabledAt`` (null means active).
    """
    behavior_list = _parse_behaviors_json(behaviors)
    ds_raw = parse_json_value(data_sources, "--data-sources") if data_sources else None
    data_source_ids: list[str] = []
    if ds_raw is not None:
        if not isinstance(ds_raw, list) or not all(isinstance(x, str) for x in ds_raw):
            raise typer.BadParameter("--data-sources must be a JSON array of strings")
        data_source_ids = list(ds_raw)

    inst = normalize_pipefy_ai_instruction_tokens(instruction.strip())
    try:
        expanded = expand_behaviors_placeholders(behavior_list)
        validated = UpdateAiAgentInput(
            uuid=uuid.strip(),
            name=name.strip(),
            repo_uuid=repo_uuid.strip(),
            instruction=inst,
            behaviors=expanded,
            data_source_ids=data_source_ids,
        )
    except ValidationError as exc:
        raise typer.BadParameter(str(exc)) from exc

    async def factory(client: PipefyClient):
        pre = await validate_ai_agent_behaviors_sdk(
            client,
            pipe.strip(),
            [b.model_dump(by_alias=True) for b in validated.behaviors],
            strict_unknown_action_types=strict_unknown,
        )
        _raise_if_preflight_blocks(pre)
        result = await client.update_ai_agent(validated)
        if pre.get("warnings"):
            return {**result, "preflight": pre}
        return result

    run_cli_command(ctx, json_out, factory)


@agent_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def agent_delete(
    ctx: typer.Context,
    uuid: str = resource_id_argument(help="Agent UUID."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip interactive confirmation."
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Delete an AI agent (``delete_ai_agent``)."""
    confirm_destructive(yes=yes, description=f"AI agent (UUID: {uuid})", verb="delete")

    async def factory(client: PipefyClient):
        return await client.delete_ai_agent(uuid)

    run_cli_command(ctx, json_out, factory)


@agent_app.command("toggle", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def agent_toggle(
    ctx: typer.Context,
    uuid: str = resource_id_argument(help="Agent UUID."),
    active: bool = typer.Option(
        True,
        "--active/--inactive",
        help="Enable or disable the agent.",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation when disabling."
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Enable or disable an AI agent (``toggle_ai_agent_status``)."""
    if not active:
        confirm_destructive(
            yes=yes,
            description=f"AI agent (UUID: {uuid})",
            verb="disable",
        )

    async def factory(client: PipefyClient):
        return await client.toggle_ai_agent_status(uuid, active=active)

    run_cli_command(ctx, json_out, factory)


@logs_app.command("list")
def agent_logs_list(
    ctx: typer.Context,
    repo: str = typer.Option(..., "--repo", help="Pipe UUID."),
    first: int = typer.Option(30, "--first", help="Page size."),
    after: str | None = typer.Option(None, "--after", help="Pagination cursor."),
    status: str | None = typer.Option(
        None, "--status", help="processing|failed|success"
    ),
    search: str | None = typer.Option(None, "--search", help="Free-text search."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List AI agent execution logs (``get_ai_agent_logs``)."""

    async def factory(client: PipefyClient):
        return await client.get_ai_agent_logs(
            repo, first=first, after=after, status=status, search_term=search
        )

    run_cli_command(ctx, json_out, factory)


@logs_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def agent_logs_get(
    ctx: typer.Context,
    log_id: str = resource_id_argument(help="Log UUID."),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Fetch one AI agent log entry (``get_ai_agent_log_details``)."""

    async def factory(client: PipefyClient):
        return await client.get_ai_agent_log_details(log_id)

    run_cli_command(ctx, json_out, factory)


@agent_app.command("validate-behaviors")
def agent_validate_behaviors(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Numeric pipe id."),
    behaviors: str = typer.Option(
        ..., "--behaviors", help="JSON array of behavior objects."
    ),
    strict_unknown: bool = typer.Option(
        True,
        "--strict/--no-strict",
        help=(
            "Pre-flight strictness: --strict (default) reports unknown actionType "
            "values as problems; --no-strict reports them as warnings only."
        ),
    ),
    data_source_id: list[str] = typer.Option(
        [],
        "--data-source-id",
        help=(
            "Agent-level knowledge base ID to attach (repeatable). Unioned with "
            "behavior-level dataSourceIds and checked against the pipe's knowledge "
            "bases; unknown IDs are warnings only."
        ),
    ),
    json_out: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Dry-run behavior validation (``validate_ai_agent_behaviors``)."""
    behavior_list = _parse_behaviors_json(behaviors)

    async def factory(client: PipefyClient):
        return await validate_ai_agent_behaviors_sdk(
            client,
            pipe.strip(),
            behavior_list,
            strict_unknown_action_types=strict_unknown,
            data_source_ids=data_source_id or None,
        )

    run_cli_command(ctx, json_out, factory)
