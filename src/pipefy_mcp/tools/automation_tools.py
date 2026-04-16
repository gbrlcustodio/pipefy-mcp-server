"""MCP tools for traditional Pipefy automations (trigger/action rules)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from pipefy_mcp.models.send_task_automation import CreateSendTaskAutomationInput
from pipefy_mcp.models.validators import PipefyId
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.automation_tool_helpers import (
    build_automation_error_payload,
    build_automation_mutation_success_payload,
    build_automation_read_success_payload,
    build_automation_simulation_success_payload,
    handle_automation_tool_graphql_error,
)
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.graphql_error_helpers import enrich_permission_denied_error
from pipefy_mcp.tools.phase_transition_helpers import (
    validate_traditional_automation_move_transition_or_none,
)
from pipefy_mcp.tools.validation_helpers import (
    mutation_error_if_not_optional_dict,
    validate_optional_tool_id,
    validate_tool_id,
)


def _normalize_simulation_action_id(value: str | int) -> str | None:
    """Normalize simulation ``action_id`` (enum string such as ``generate_with_ai``, or positive int)."""
    if isinstance(value, int):
        return str(value) if value > 0 else None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return None


class AutomationTools:
    """MCP tools for traditional (non-AI) pipe automations."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        async def get_automation(
            ctx: Context, automation_id: PipefyId
        ) -> dict[str, Any]:
            """Load one automation rule by ID, including trigger and action payloads.

            Use this to inspect or debug a specific rule, or before ``update_automation`` /
            ``delete_automation``. Returned ``event_params`` and ``action_params`` (e.g.
            ``aiParams`` with ``value`` / ``fieldIds`` / ``skillsIds``) align with
            ``simulate_automation`` and ``create_automation`` inputs. For new rules, discover
            ``event_id`` / ``action_id`` via ``get_automation_events`` and ``get_automation_actions``
            on the target pipe, then call ``create_automation``.

            Args:
                automation_id: Automation rule ID (non-empty string or positive integer).

            Returns:
                On success, ``success``, ``message``, and ``data`` with the automation row (or
                ``None`` when not found). On validation or GraphQL errors, ``success: False`` with
                ``error``.
            """
            aid, aid_err = validate_tool_id(automation_id, "automation_id")
            if aid_err is not None:
                return aid_err
            try:
                raw = await client.get_automation(aid)
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(exc, ctx, False)
            message = (
                "No automation found for the given ID."
                if not raw
                else "Automation retrieved."
            )
            return build_automation_read_success_payload(raw, message)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        async def get_automations(
            ctx: Context,
            organization_id: PipefyId | None = None,
            pipe_id: PipefyId | None = None,
        ) -> dict[str, Any]:
            """List traditional automation rules, optionally filtered by organization and/or pipe.

            Use this to discover automation IDs in a pipe or org before calling ``get_automation``
            for full payloads, or to plan ``create_automation`` / ``update_automation`` without
            listing unrelated rules.

            Combine with ``get_automation`` for full detail. When only ``pipe_id`` is set (no
            ``organization_id``), the server resolves the org from the pipe first, then lists
            automations — two sequential API calls vs. one when you pass ``organization_id``
            directly.

            Args:
                organization_id: When set, restrict to this organization; omit for no org filter.
                pipe_id: When set, restrict to this pipe; omit for no pipe filter.

            Returns:
                On success, ``success``, ``message``, and ``data`` with the list of automation
                summaries returned by the API. On validation or GraphQL errors, ``success: False``
                with ``error``.
            """
            ok_o, org, org_err = validate_optional_tool_id(
                organization_id, "organization_id"
            )
            if org_err is not None:
                return org_err
            ok_p, pipe, pipe_err = validate_optional_tool_id(pipe_id, "pipe_id")
            if pipe_err is not None:
                return pipe_err
            try:
                rows = await client.get_automations(
                    organization_id=org,
                    pipe_id=pipe,
                )
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(exc, ctx, False)
            return build_automation_read_success_payload(
                rows,
                "Automations listed.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        async def get_automation_actions(
            ctx: Context,
            pipe_id: PipefyId,
        ) -> dict[str, Any]:
            """List automation action types available on a pipe (labels, fields, IDs).

            Call this before ``create_automation`` or ``update_automation`` to choose valid
            ``action_id`` values and required ``actionFields`` for the Pipefy API payload.

            Args:
                pipe_id: Pipe ID.
            """
            pid, pid_err = validate_tool_id(pipe_id, "pipe_id")
            if pid_err is not None:
                return pid_err
            try:
                rows = await client.get_automation_actions(pid)
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(exc, ctx, False)
            return build_automation_read_success_payload(
                rows,
                "Automation actions catalog retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        async def get_automation_events(
            ctx: Context, pipe_id: PipefyId
        ) -> dict[str, Any]:
            """List automation trigger event definitions (IDs and metadata).

            Pipefy's schema exposes one global event catalog (no per-pipe GraphQL filter);
            ``pipe_id`` is kept so callers anchor to a workflow context. Use results with
            ``get_automation_actions`` on the same pipe before ``create_automation``.

            Args:
                pipe_id: Pipe ID (context for the agent; required by the tool).
            """
            pid, pid_err = validate_tool_id(pipe_id, "pipe_id")
            if pid_err is not None:
                return pid_err
            try:
                rows = await client.get_automation_events(pid)
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(exc, ctx, False)
            return build_automation_read_success_payload(
                rows,
                "Automation events catalog retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
        )
        async def simulate_automation(
            ctx: Context,
            pipe_id: PipefyId,
            action_id: PipefyId,
            sample_card_id: PipefyId,
            event_id: PipefyId | None = None,
            event_params: Any | None = None,
            action_params: Any | None = None,
            condition: Any | None = None,
            name: str | None = None,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Dry-run an **AI automation** (``generate_with_ai``) against a real card (safe simulation, no live side effects).

            The Pipefy ``createAutomationSimulation`` API currently **only** accepts
            ``action_id = "generate_with_ai"``; passing any other action (e.g.
            ``move_single_card``, ``send_a_task``) returns a validation error. Use this
            to preview AI-generated output on ``sample_card_id`` before enabling the rule.

            **Pipe context:** ``pipe_id`` is forwarded as ``event_repo_id`` and ``action_repo_id`` on the
            simulation input (Pipefy often returns ``INTERNAL_SERVER_ERROR`` if these are omitted). Override
            via ``extra_input`` for cross-pipe setups.

            Args:
                pipe_id: Pipe ID — default ``event_repo_id`` / ``action_repo_id`` for the simulation input.
                action_id: Simulation action id — currently only ``generate_with_ai`` is accepted by the API.
                sample_card_id: Card id the simulation executes against.
                event_id: Optional trigger event id when the scenario needs it.
                event_params: Optional JSON object (trigger parameters).
                action_params: Optional JSON object (action parameters).
                condition: Optional JSON object (condition payload).
                name: Optional simulation input name.
                extra_input: Optional map of extra ``CreateAutomationSimulationInput`` fields (merged last).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            pid, pid_err = validate_tool_id(pipe_id, "pipe_id")
            if pid_err is not None:
                return pid_err
            sid, sid_err = validate_tool_id(sample_card_id, "sample_card_id")
            if sid_err is not None:
                return sid_err
            aid = _normalize_simulation_action_id(action_id)
            if aid is None:
                return build_automation_error_payload(
                    message=(
                        "Invalid 'action_id': use a non-empty string or "
                        "positive integer."
                    ),
                )
            eid: str | None = None
            if event_id is not None:
                eid, eid_err = validate_tool_id(event_id, "event_id")
                if eid_err is not None:
                    return eid_err
            for arg_name, val in (
                ("event_params", event_params),
                ("action_params", action_params),
                ("condition", condition),
            ):
                bad = mutation_error_if_not_optional_dict(val, arg_name=arg_name)
                if bad is not None:
                    return bad
            bad = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad is not None:
                return bad
            if name is not None and (not isinstance(name, str) or not name.strip()):
                return build_automation_error_payload(
                    message="Invalid 'name': provide a non-empty string when supplied.",
                )
            try:
                result = await client.simulate_automation(
                    pipe_id=pid,
                    action_id=aid,
                    sample_card_id=sid,
                    event_id=eid,
                    event_params=event_params,
                    action_params=action_params,
                    condition=condition,
                    name=name.strip() if isinstance(name, str) else None,
                    extra_input=extra_input,
                )
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(exc, ctx, debug)
            sim_row = result["automation_simulation"]
            if not isinstance(sim_row, dict):
                sim_row = {}
            return build_automation_simulation_success_payload(
                result["simulation_id"],
                sim_row,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_automation(
            ctx: Context,
            pipe_id: PipefyId,
            name: str,
            trigger_id: PipefyId,
            action_id: PipefyId,
            active: bool = True,
            action_repo_id: PipefyId | None = None,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a traditional automation rule on a pipe (event + action).

            Use ``get_automation_events`` and ``get_automation_actions`` on ``pipe_id`` first to obtain
            valid ``trigger_id`` and ``action_id``. Optional ``extra_input`` merges API fields for
            ``CreateAutomationInput`` (camelCase keys). Use ``update_automation`` with ``active: false``
            to disable a rule after creation.

            For ``card_moved`` rules with action ``move_single_card``, when ``extra_input`` includes
            ``event_params.to_phase_id`` (or ``toPhaseId``) and ``action_params.to_phase_id`` (or
            ``phase.id``), the tool rejects impossible transitions before calling the API, using the
            same read-only transition data as ``move_card_to_phase``.

            **Cross-pipe actions** (e.g. ``create_connected_card``, ``move_card_to_pipe``):
            set ``action_repo_id`` to the **destination** pipe ID. When omitted it defaults to
            ``pipe_id`` (same-pipe automation). Cross-pipe actions typically require
            ``action_params`` inside ``extra_input`` — for example, ``create_connected_card`` needs
            ``{"action_params": {"pipeId": "<child_pipe_id>", "fieldsAttributes": [...]}}``.

            Args:
                pipe_id: Pipe ID where the trigger event fires (source pipe).
                name: Rule name.
                trigger_id: Event ID from ``get_automation_events``.
                action_id: Action type ID from ``get_automation_actions``.
                active: When True (default), the rule is created **enabled**. Set False to start disabled. If ``extra_input`` includes ``active``, that value wins.
                action_repo_id: Pipe ID where the action executes (destination pipe). Defaults to ``pipe_id``. Required for cross-pipe actions.
                extra_input: Optional extra fields for the mutation input (camelCase keys).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            pid, pid_err = validate_tool_id(pipe_id, "pipe_id")
            if pid_err is not None:
                return pid_err
            tid, tid_err = validate_tool_id(trigger_id, "trigger_id")
            if tid_err is not None:
                return tid_err
            aid, aid_err = validate_tool_id(action_id, "action_id")
            if aid_err is not None:
                return aid_err
            if not isinstance(name, str) or not name.strip():
                return build_automation_error_payload(
                    message="Invalid 'name': provide a non-empty string.",
                )
            _, arid, arid_err = validate_optional_tool_id(
                action_repo_id, "action_repo_id"
            )
            if arid_err is not None:
                return arid_err
            bad = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad is not None:
                return bad
            transition_msg = (
                await validate_traditional_automation_move_transition_or_none(
                    client, tid, aid, extra_input
                )
            )
            if transition_msg is not None:
                return build_automation_error_payload(transition_msg)
            try:
                raw = await client.create_automation(
                    pid,
                    name.strip(),
                    tid,
                    aid,
                    active=active,
                    action_repo_id=arid,
                    extra_input=extra_input,
                )
            except Exception as exc:  # noqa: BLE001
                if arid and arid != pid:
                    perm_msg = await enrich_permission_denied_error(
                        exc, [pid, arid], client
                    )
                    if perm_msg:
                        base = await handle_automation_tool_graphql_error(
                            exc, ctx, debug
                        )
                        base["error"] = f"{perm_msg}\n{base.get('error', '')}"
                        return base
                return await handle_automation_tool_graphql_error(exc, ctx, debug)
            block = raw.get("createAutomation") or {}
            automation = block.get("automation") or {}
            if not isinstance(automation, dict):
                automation = {}
            return build_automation_mutation_success_payload(automation, "created")

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
        )
        async def create_send_task_automation(
            ctx: Context,
            pipe_id: PipefyId,
            name: str,
            event_id: str,
            task_title: str,
            recipients: str,
            active: bool = True,
            event_params: dict[str, Any] | None = None,
            condition: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Create a traditional automation that sends a task to recipients when a trigger fires on a pipe.

            By default the rule is created **active** (``active=True``). Set ``active=False``
            to create the rule disabled — recommended when testing, so it does not fire
            until you explicitly enable it via ``update_automation``.

            **Compatible triggers** (examples): ``card_created``, ``card_moved``, ``field_updated``,
            ``card_inbox_received_email``, ``all_children_in_phase``, ``manually_triggered``,
            ``http_response_received``.

            **Incompatible / blocked**: ``scheduler`` is rejected by this tool before the API call.
            ``sla_based`` and ``card_left_phase`` are documented as incompatible with the send-a-task
            action in Pipefy; the API will reject them if used.

            **event_params**: optional dict of trigger-specific filters, for example ``{"to_phase_id": "..."}``
            for ``card_moved``, or ``{"triggerFieldIds": ["..."]}`` for ``field_updated``.

            Args:
                pipe_id: Pipe ID where the trigger event is evaluated.
                name: Automation rule display name.
                event_id: Trigger event ID (e.g. ``card_created``).
                task_title: Title of the task sent to recipients.
                recipients: One or more e-mail addresses separated by commas.
                active: When True (default), the rule is created enabled and will fire immediately. Set False to start disabled.
                event_params: Optional trigger filter payload (camelCase/snake_case as returned by catalog tools).
                condition: Optional condition expressions payload.
            """
            try:
                validated = CreateSendTaskAutomationInput(
                    pipe_id=pipe_id,
                    name=name,
                    event_id=event_id,
                    task_title=task_title,
                    recipients=recipients,
                    event_params=event_params,
                    condition=condition,
                )
            except ValidationError as exc:
                return build_automation_error_payload(str(exc))

            extra_input: dict[str, Any] = {
                "action_params": {
                    "taskParams": {
                        "title": validated.task_title,
                        "recipients": validated.recipients,
                    },
                },
            }
            if validated.event_params is not None:
                extra_input["event_params"] = validated.event_params
            if validated.condition is not None:
                extra_input["condition"] = validated.condition

            try:
                raw = await client.create_automation(
                    validated.pipe_id,
                    validated.name,
                    validated.event_id,
                    "send_a_task",
                    active=active,
                    action_repo_id=None,
                    extra_input=extra_input,
                )
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(exc, ctx, False)
            block = raw.get("createAutomation") or {}
            automation = block.get("automation") or {}
            if not isinstance(automation, dict):
                automation = {}
            return build_automation_mutation_success_payload(automation, "created")

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_automation(
            ctx: Context,
            automation_id: PipefyId,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update an existing traditional automation (partial ``UpdateAutomationInput``).

            Optional ``extra_input`` holds fields to change (camelCase keys). Discover current shape
            with ``get_automation`` when unsure.

            Args:
                automation_id: Automation rule ID.
                extra_input: Optional fields to patch on the rule.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            rid, rid_err = validate_tool_id(automation_id, "automation_id")
            if rid_err is not None:
                return rid_err
            bad = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad is not None:
                return bad
            try:
                raw = await client.update_automation(
                    rid,
                    extra_input=extra_input,
                )
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(exc, ctx, debug)
            block = raw.get("updateAutomation") or {}
            automation = block.get("automation") or {}
            if not isinstance(automation, dict):
                automation = {}
            return build_automation_mutation_success_payload(automation, "updated")

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
        )
        async def delete_automation(
            ctx: Context[ServerSession, None],
            automation_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete an automation rule permanently.

            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval. Elicitation does not authorize
            deletion (only ``confirm=True`` does).

            Args:
                automation_id: Automation rule ID to delete.
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            rid, rid_err = validate_tool_id(automation_id, "automation_id")
            if rid_err is not None:
                return rid_err

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"automation (ID: {automation_id})",
            )
            if guard is not None:
                return guard

            try:
                raw = await client.delete_automation(rid)
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(exc, ctx, debug)
            if not raw.get("success"):
                return build_automation_error_payload(
                    message="Delete automation did not succeed.",
                )
            return build_automation_mutation_success_payload({}, "deleted")
