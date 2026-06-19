"""Traditional Pipefy automations (rules, logs, exports, usage)."""

from __future__ import annotations

import typer
from pipefy_sdk import CreateSendTaskAutomationInput, PipefyClient
from pydantic import ValidationError

from pipefy_cli.commands._common import (
    ID_POSITIONAL_CONTEXT_SETTINGS,
    confirm_destructive,
    parse_json_object,
    parse_json_value,
    resource_id_argument,
    run_cli_command,
)

automation_app = typer.Typer(
    help="Traditional automations and related exports.", no_args_is_help=True
)
export_app = typer.Typer(help="Automation jobs export (async).", no_args_is_help=True)
send_task_app = typer.Typer(help="Send-a-task automation helper.", no_args_is_help=True)
events_app = typer.Typer(help="Automation trigger catalog.", no_args_is_help=True)
actions_app = typer.Typer(help="Automation action catalog.", no_args_is_help=True)


def _automation_params_from_flags(
    *,
    to_phase: str | None,
    from_phase: str | None,
    in_phase: str | None,
    trigger_fields: str | None,
    email_template: str | None,
    url: str | None,
    http_method: str | None,
    request_body: str | None,
    headers: str | None,
) -> dict[str, dict[str, object]]:
    """Build the ``action_params``/``event_params`` envelopes from convenience flags.

    Each flag maps to the API's exact-cased nested key. Containers with no flags
    set are omitted so they never shadow an ``--extra`` payload.
    """
    action_params: dict[str, object] = {}
    if to_phase is not None:
        action_params["to_phase_id"] = to_phase
    if email_template is not None:
        action_params["email_template_id"] = email_template
    if url is not None:
        action_params["url"] = url
    if http_method is not None:
        action_params["httpMethod"] = http_method
    if request_body is not None:
        action_params["body"] = request_body
    if headers is not None:
        action_params["headers"] = headers

    event_params: dict[str, object] = {}
    if from_phase is not None:
        event_params["fromPhaseId"] = from_phase
    if in_phase is not None:
        event_params["inPhaseId"] = in_phase
    if trigger_fields is not None:
        event_params["triggerFieldIds"] = [
            token.strip() for token in trigger_fields.split(",") if token.strip()
        ]

    built: dict[str, dict[str, object]] = {}
    if action_params:
        built["action_params"] = action_params
    if event_params:
        built["event_params"] = event_params
    return built


@automation_app.command("list")
def automation_list(
    ctx: typer.Context,
    organization: str | None = typer.Option(
        None,
        "--organization",
        "--org",
        help="Optional organization id filter.",
    ),
    pipe: str | None = typer.Option(None, "--pipe", help="Optional pipe id filter."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """List automation rules (``get_automations``)."""

    async def factory(client: PipefyClient):
        return await client.get_automations(
            organization_id=organization,
            pipe_id=pipe,
        )

    run_cli_command(ctx, json_out, factory)


@automation_app.command("get", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def automation_get(
    ctx: typer.Context,
    automation_id: str = resource_id_argument(help="Automation rule id."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Load one automation (``get_automation``)."""

    async def factory(client: PipefyClient):
        row = await client.get_automation(automation_id)
        if row is None:
            return {
                "success": False,
                "message": "No automation found for the given ID.",
            }
        return {"success": True, "message": "Automation retrieved.", "data": row}

    run_cli_command(ctx, json_out, factory)


@automation_app.command("create")
def automation_create(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Source pipe id (trigger context)."),
    name: str = typer.Option(..., "--name", "-n", help="Rule name."),
    trigger_id: str = typer.Option(
        ...,
        "--event-id",
        "--trigger-id",
        help="Trigger event id from ``automation events list`` (``--trigger-id`` retained as alias).",
    ),
    action_id: str = typer.Option(
        ...,
        "--action-id",
        help="Action id from ``automation actions list``.",
    ),
    active: bool = typer.Option(
        True, "--active/--no-active", help="Create enabled or disabled."
    ),
    action_repo: str | None = typer.Option(
        None,
        "--action-repo",
        help="Destination pipe id for cross-pipe actions (defaults to --pipe).",
    ),
    to_phase: str | None = typer.Option(
        None,
        "--to-phase",
        help="Move actions: destination phase id (action_params.to_phase_id).",
    ),
    from_phase: str | None = typer.Option(
        None,
        "--from-phase",
        help="card_moved/card_left_phase trigger: origin phase id (event_params.fromPhaseId).",
    ),
    in_phase: str | None = typer.Option(
        None,
        "--in-phase",
        help="Trigger filter: current phase id (event_params.inPhaseId).",
    ),
    trigger_fields: str | None = typer.Option(
        None,
        "--trigger-fields",
        help="field_updated trigger: comma-separated field ids (event_params.triggerFieldIds).",
    ),
    email_template: str | None = typer.Option(
        None,
        "--email-template",
        help="send_email_template action: template id (action_params.email_template_id).",
    ),
    url: str | None = typer.Option(
        None,
        "--url",
        help="send_http_request action: request URL (action_params.url).",
    ),
    http_method: str | None = typer.Option(
        None,
        "--http-method",
        help="send_http_request action: HTTP method, e.g. POST (action_params.httpMethod).",
    ),
    request_body: str | None = typer.Option(
        None,
        "--request-body",
        help="send_http_request action: request body (action_params.body).",
    ),
    headers: str | None = typer.Option(
        None,
        "--headers",
        help="send_http_request action: request headers (action_params.headers).",
    ),
    extra: str | None = typer.Option(
        None,
        "--extra",
        help=(
            "Optional JSON object of extra CreateAutomationInput fields, "
            "snake_case API names (e.g. action_params, event_params); "
            "camelCase keys are also accepted."
        ),
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Create an automation rule (``create_automation``)."""
    extra_obj = parse_json_object(extra, "--extra") or {}
    flag_params = _automation_params_from_flags(
        to_phase=to_phase,
        from_phase=from_phase,
        in_phase=in_phase,
        trigger_fields=trigger_fields,
        email_template=email_template,
        url=url,
        http_method=http_method,
        request_body=request_body,
        headers=headers,
    )
    if "action_params" in flag_params and (
        "action_params" in extra_obj or "actionParams" in extra_obj
    ):
        raise typer.BadParameter(
            "Action-param flags (--to-phase, --email-template, --url, ...) "
            "conflict with action_params in --extra; use one or the other."
        )
    if "event_params" in flag_params and (
        "event_params" in extra_obj or "eventParams" in extra_obj
    ):
        raise typer.BadParameter(
            "Event-param flags (--from-phase, --in-phase, --trigger-fields) "
            "conflict with event_params in --extra; use one or the other."
        )
    extra_input = {**extra_obj, **flag_params} or None

    async def factory(client: PipefyClient):
        return await client.create_automation(
            pipe,
            name.strip(),
            trigger_id,
            action_id,
            active=active,
            action_repo_id=action_repo,
            extra_input=extra_input,
        )

    run_cli_command(ctx, json_out, factory)


@automation_app.command("update", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def automation_update(
    ctx: typer.Context,
    automation_id: str = resource_id_argument(help="Automation rule id."),
    extra: str = typer.Option(
        ...,
        "--extra",
        help=(
            "JSON object of fields to patch (UpdateAutomationInput), "
            "snake_case API names; camelCase keys are also accepted."
        ),
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Update an automation (``update_automation``)."""
    extra_obj = parse_json_value(extra, "--extra")
    if not isinstance(extra_obj, dict):
        raise typer.BadParameter("--extra must be a JSON object")

    async def factory(client: PipefyClient):
        return await client.update_automation(automation_id, extra_input=extra_obj)

    run_cli_command(ctx, json_out, factory)


@automation_app.command("delete", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def automation_delete(
    ctx: typer.Context,
    automation_id: str = resource_id_argument(help="Automation rule id."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip interactive confirmation."
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Delete an automation rule (``delete_automation``)."""
    confirm_destructive(
        yes=yes, description=f"automation {automation_id}", verb="delete"
    )

    async def factory(client: PipefyClient):
        return await client.delete_automation(automation_id)

    run_cli_command(ctx, json_out, factory)


@automation_app.command("simulate")
def automation_simulate(
    ctx: typer.Context,
    pipe: str = typer.Option(
        ..., "--pipe", help="Pipe id (event/action repo defaults)."
    ),
    action_id: str = typer.Option(
        ..., "--action-id", help="Simulation action id (e.g. generate_with_ai)."
    ),
    sample_card: str = typer.Option(
        ..., "--sample-card", help="Card id for the dry-run."
    ),
    event_id: str | None = typer.Option(
        None, "--event-id", help="Optional trigger event id."
    ),
    event_params: str | None = typer.Option(
        None, "--event-params", help="Optional JSON object."
    ),
    action_params: str | None = typer.Option(
        None, "--action-params", help="Optional JSON object."
    ),
    condition: str | None = typer.Option(
        None, "--condition", help="Optional JSON object."
    ),
    name: str | None = typer.Option(None, "--name", help="Optional simulation name."),
    extra: str | None = typer.Option(
        None,
        "--extra",
        help="Optional JSON object merged into simulation input.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Dry-run an automation against a card (``simulate_automation``)."""
    ep = parse_json_object(event_params, "--event-params")
    ap = parse_json_object(action_params, "--action-params")
    cond = parse_json_object(condition, "--condition")
    ex = parse_json_object(extra, "--extra")

    async def factory(client: PipefyClient):
        return await client.simulate_automation(
            pipe_id=pipe,
            action_id=action_id,
            sample_card_id=sample_card,
            event_id=event_id,
            event_params=ep,
            action_params=ap,
            condition=cond,
            name=name,
            extra_input=ex,
        )

    run_cli_command(ctx, json_out, factory)


@send_task_app.command("create")
def automation_send_task_create(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Pipe id."),
    name: str = typer.Option(..., "--name", "-n", help="Rule name."),
    event_id: str = typer.Option(..., "--event-id", help="Trigger event id."),
    task_title: str = typer.Option(..., "--task-title", help="Task title."),
    recipients: str = typer.Option(
        ...,
        "--recipients",
        help="Recipient emails (comma-separated).",
    ),
    active: bool = typer.Option(
        True, "--active/--no-active", help="Create enabled or disabled."
    ),
    event_params: str | None = typer.Option(
        None, "--event-params", help="Optional JSON object."
    ),
    condition: str | None = typer.Option(
        None, "--condition", help="Optional JSON object."
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Create a send-a-task automation (``create_send_task_automation``)."""
    ep = parse_json_object(event_params, "--event-params")
    cond = parse_json_object(condition, "--condition")
    try:
        validated = CreateSendTaskAutomationInput(
            pipe_id=pipe,
            name=name,
            event_id=event_id,
            task_title=task_title,
            recipients=recipients,
            event_params=ep,
            condition=cond,
        )
    except ValidationError as exc:
        raise typer.BadParameter(str(exc)) from exc

    async def factory(client: PipefyClient):
        return await client.create_send_task_automation(
            validated.pipe_id,
            validated.name,
            validated.event_id,
            validated.task_title,
            validated.recipients,
            active=active,
            event_params=validated.event_params,
            condition=validated.condition,
        )

    run_cli_command(ctx, json_out, factory)


@automation_app.command("logs")
def automation_logs(
    ctx: typer.Context,
    automation: str | None = typer.Option(
        None,
        "--automation",
        help="Automation id (use this or --repo, not both).",
    ),
    repo: str | None = typer.Option(
        None,
        "--repo",
        help="Pipe id: list logs for all automations in the repo (``get_automation_logs_by_repo``).",
    ),
    first: int = typer.Option(30, "--first", help="Page size."),
    after: str | None = typer.Option(None, "--after", help="Pagination cursor."),
    status: str | None = typer.Option(None, "--status", help="Log status filter."),
    search: str | None = typer.Option(None, "--search", help="Free-text search."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """List automation execution logs (``get_automation_logs`` or ``get_automation_logs_by_repo``)."""
    if (automation is None) == (repo is None):
        raise typer.BadParameter("Provide exactly one of --automation or --repo.")

    async def factory(client: PipefyClient):
        if automation is not None:
            return await client.get_automation_logs(
                automation,
                first=first,
                after=after,
                status=status,
                search_term=search,
            )
        return await client.get_automation_logs_by_repo(
            repo or "",
            first=first,
            after=after,
            status=status,
            search_term=search,
        )

    run_cli_command(ctx, json_out, factory)


@events_app.command("list")
def automation_events_list(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Pipe id (context for catalog)."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """List trigger events (``get_automation_events``)."""

    async def factory(client: PipefyClient):
        return await client.get_automation_events(pipe)

    run_cli_command(ctx, json_out, factory)


@automation_app.command("event-attributes")
def automation_event_attributes(
    ctx: typer.Context,
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """List official event-attribute tokens (``get_automation_event_attributes``)."""

    async def factory(client: PipefyClient):
        return await client.get_automation_event_attributes()

    run_cli_command(ctx, json_out, factory)


@actions_app.command("list")
def automation_actions_list(
    ctx: typer.Context,
    pipe: str = typer.Option(..., "--pipe", help="Pipe id."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """List action types for a pipe (``get_automation_actions``)."""

    async def factory(client: PipefyClient):
        return await client.get_automation_actions(pipe)

    run_cli_command(ctx, json_out, factory)


@automation_app.command("usage")
def automation_usage(
    ctx: typer.Context,
    organization: str = typer.Option(
        ...,
        "--organization",
        "--org",
        help="Organization UUID or numeric id (resolved like MCP).",
    ),
    date_from: str = typer.Option(
        ...,
        "--from",
        help="Range start (ISO8601), maps to filter_date.from.",
    ),
    date_to: str = typer.Option(
        ...,
        "--to",
        help="Range end (ISO8601), maps to filter_date.to.",
    ),
    filters: str | None = typer.Option(
        None, "--filters", help="Optional JSON object (FilterParams)."
    ),
    search: str | None = typer.Option(
        None, "--search", help="Optional free-text search."
    ),
    sort: str | None = typer.Option(
        None, "--sort", help="Optional JSON object (SortCriteria)."
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Automation usage for an org in a date range (``get_automations_usage``)."""
    filter_date = {"from": date_from, "to": date_to}
    filters_obj = parse_json_object(filters, "--filters")
    sort_obj = parse_json_object(sort, "--sort")

    async def factory(client: PipefyClient):
        return await client.get_automations_usage(
            organization,
            filter_date,
            filters=filters_obj,
            search=search,
            sort=sort_obj,
        )

    run_cli_command(ctx, json_out, factory)


@export_app.command("jobs")
def automation_export_jobs(
    ctx: typer.Context,
    organization: str = typer.Option(
        ...,
        "--organization",
        "--org",
        help="Organization id.",
    ),
    period: str = typer.Option(
        ...,
        "--period",
        help="Period filter: current_month, last_month, or last_3_months.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Start automation jobs export (``export_automation_jobs``)."""

    async def factory(client: PipefyClient):
        return await client.export_automation_jobs(organization, period)

    run_cli_command(ctx, json_out, factory)


@export_app.command("status", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def automation_export_status(
    ctx: typer.Context,
    export_id: str = resource_id_argument(help="Export id from ``export jobs``."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Poll export status / signed URL (``get_automation_jobs_export``)."""

    async def factory(client: PipefyClient):
        return await client.get_automation_jobs_export(export_id)

    run_cli_command(ctx, json_out, factory)


@export_app.command("csv", context_settings=ID_POSITIONAL_CONTEXT_SETTINGS)
def automation_export_csv(
    ctx: typer.Context,
    export_id: str = resource_id_argument(help="Finished export id."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Download finished export as CSV text (``get_automation_jobs_export_csv``)."""

    async def factory(client: PipefyClient):
        return await client.get_automation_jobs_export_csv(export_id)

    run_cli_command(ctx, json_out, factory)


automation_app.add_typer(send_task_app, name="send-task")
automation_app.add_typer(export_app, name="export")
automation_app.add_typer(events_app, name="events")
automation_app.add_typer(actions_app, name="actions")
