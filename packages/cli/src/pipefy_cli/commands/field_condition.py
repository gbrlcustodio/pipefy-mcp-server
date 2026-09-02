"""Field condition rules on phases."""

from __future__ import annotations

from typing import Any

import typer
from pipefy_sdk import PipefyClient
from pipefy_sdk.graphql_inputs import (
    CreateFieldConditionInput,
    UpdateFieldConditionInput,
)
from pipefy_sdk.utils import normalize_field_condition_fields

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    graphql_input_or_bad_parameter,
    parse_json_object,
    parse_json_value,
    reject_reserved_extra_keys,
    resource_id_argument,
    run_cli_command,
)

# Keys a dedicated argument already sets, so `--extra` may not also carry them.
# The same policy the MCP tools apply through their own reserved sets.
_CREATE_FIELD_CONDITION_RESERVED = frozenset(
    {"phaseId", "phase_id", "condition", "actions", "name"}
)
_UPDATE_FIELD_CONDITION_RESERVED = frozenset({"id"})

field_condition_app = typer.Typer(
    help="Field conditions (dynamic form rules on phases).",
    no_args_is_help=True,
)


@field_condition_app.command("list")
def field_condition_list(
    ctx: typer.Context,
    phase_id: str = typer.Option(
        ..., "--phase", help="Phase id that owns the conditions."
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """List field conditions on a phase (``get_field_conditions``)."""

    async def factory(client: PipefyClient) -> dict[str, Any]:
        raw = await client.get_field_conditions(phase_id)
        phase = raw.get("phase")
        if phase is None:
            return {"success": False, "error": "Phase not found or access denied."}
        rows = phase.get("fieldConditions") or []
        return {
            "success": True,
            "message": "Field conditions loaded.",
            "field_conditions": rows,
        }

    run_cli_command(ctx, json_out, factory)


@field_condition_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def field_condition_get(
    ctx: typer.Context,
    condition_id: str = resource_id_argument(help="Field condition id."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Load one field condition by id (``get_field_condition``)."""

    async def factory(client: PipefyClient) -> dict[str, Any]:
        raw = await client.get_field_condition(condition_id)
        fc = raw.get("fieldCondition")
        if fc is None:
            return {
                "success": False,
                "error": "Field condition not found or access denied.",
            }
        return {
            "success": True,
            "message": "Field condition loaded.",
            "field_condition": fc,
        }

    run_cli_command(ctx, json_out, factory)


@field_condition_app.command("create")
def field_condition_create(
    ctx: typer.Context,
    phase_id: str = typer.Option(..., "--phase", help="Phase id."),
    name: str = typer.Option(..., "--name", "-n", help="Rule name (required by API)."),
    condition: str = typer.Option(
        ...,
        "--condition",
        help=(
            "JSON object: ConditionInput. Example: "
            '\'{"expressions":[{"structure_id":0,"field_address":"<internal_id>",'
            '"operation":"equals","value":"X"}],"expressions_structure":[[0]]}\'. '
            "structure_id / expressions_structure entries are coerced to int by the SDK."
        ),
    ),
    actions: str = typer.Option(
        ...,
        "--actions",
        help=(
            "JSON array: action objects. Each item needs phaseFieldId (use the field's "
            "internal_id from get_phase_fields) + actionId (hide|show). Example: "
            '\'[{"phaseFieldId":"<internal_id>","actionId":"hide"}]\'.'
        ),
    ),
    extra: str | None = typer.Option(
        None,
        "--extra",
        help="Optional JSON object merged into create input (camelCase keys).",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Create a field condition (``create_field_condition``)."""
    cond_obj = parse_json_value(condition, "--condition")
    if not isinstance(cond_obj, dict):
        raise typer.BadParameter("--condition must be a JSON object")
    act_parsed = parse_json_value(actions, "--actions")
    if not isinstance(act_parsed, list):
        raise typer.BadParameter("--actions must be a JSON array")
    actions_list: list[dict[str, Any]] = []
    for i, item in enumerate(act_parsed):
        if not isinstance(item, dict):
            raise typer.BadParameter(f"--actions[{i}] must be a JSON object")
        actions_list.append(item)
    extra_obj = reject_reserved_extra_keys(
        parse_json_object(extra, "--extra"),
        reserved=_CREATE_FIELD_CONDITION_RESERVED,
    )

    create_input = graphql_input_or_bad_parameter(
        CreateFieldConditionInput,
        normalize_field_condition_fields(
            {
                **extra_obj,
                "phaseId": phase_id,
                "condition": cond_obj,
                "actions": actions_list,
                "name": name,
            }
        ),
    )

    async def factory(client: PipefyClient):
        return await client.create_field_condition(create_input)

    run_cli_command(ctx, json_out, factory)


@field_condition_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def field_condition_update(
    ctx: typer.Context,
    condition_id: str = resource_id_argument(help="Field condition id."),
    extra: str = typer.Option(
        ...,
        "--extra",
        help="JSON object: fields to patch (camelCase keys for UpdateFieldConditionInput).",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Update a field condition (``update_field_condition``)."""
    extra_obj = parse_json_value(extra, "--extra")
    if not isinstance(extra_obj, dict):
        raise typer.BadParameter("--extra must be a JSON object")
    extra_obj = reject_reserved_extra_keys(
        extra_obj, reserved=_UPDATE_FIELD_CONDITION_RESERVED
    )

    update_input = graphql_input_or_bad_parameter(
        UpdateFieldConditionInput,
        normalize_field_condition_fields({**extra_obj, "id": condition_id}),
    )

    async def factory(client: PipefyClient):
        return await client.update_field_condition(update_input)

    run_cli_command(ctx, json_out, factory)


@field_condition_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def field_condition_delete(
    ctx: typer.Context,
    condition_id: str = resource_id_argument(help="Field condition id."),
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
    """Delete a field condition permanently (``delete_field_condition``)."""
    confirm_destructive(
        yes=yes,
        description=f"field condition {condition_id}",
        verb="delete",
    )

    async def factory(client: PipefyClient):
        return await client.delete_field_condition(condition_id)

    run_cli_command(ctx, json_out, factory)
