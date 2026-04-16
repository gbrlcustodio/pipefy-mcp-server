"""MCP tools for AI Agent operations (create, read, update, delete)."""

from __future__ import annotations

import asyncio

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from pipefy_mcp.models.ai_agent import CreateAiAgentInput, UpdateAiAgentInput
from pipefy_mcp.models.validators import PipefyId
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.ai_tool_helpers import (
    build_ai_tool_error,
    build_create_agent_partial_failure,
    build_create_agent_success,
    build_delete_agent_success,
    build_get_agent_success,
    build_get_agents_success,
    build_toggle_agent_status_success,
    build_update_agent_success,
    collect_pipe_ids_from_behaviors,
    enrich_behavior_error,
    fetch_pipe_validation_context,
    resolve_field_slugs_to_numeric,
    validate_behaviors_against_pipe,
)
from pipefy_mcp.tools.behavior_placeholder_interpolation import (
    expand_behaviors_placeholders,
)
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.graphql_error_helpers import (
    enrich_permission_denied_error,
    extract_error_strings,
)
from pipefy_mcp.tools.phase_transition_helpers import (
    collect_ai_behavior_move_transition_problems,
)

VALIDATE_FETCH_TIMEOUT_SECONDS = 30
MEMBERSHIP_CHECK_TIMEOUT_SECONDS = 5


_RECORD_NOT_SAVED_PATTERN = "RECORD_NOT_SAVED"

_PAYLOAD_OK_SUFFIX = (
    "\n\nNote: All behaviors passed structural validation "
    "(fields, phases, relations, actionTypes are correct). "
    "The API rejection is likely a pipe-specific restriction "
    "(orchestration pipe, feature flags, or plan limitation). "
    "Try the same behaviors on a different pipe to confirm. "
    "Do NOT retry with modified payload — the issue is the pipe, not the behaviors."
)


def _extract_pipe_id_from_behaviors(behaviors: list[dict]) -> str | None:
    """Best-effort extraction of a numeric pipe ID from behavior metadata.

    Looks for ``metadata.pipeId`` in the first action that has one.
    Returns ``None`` when no pipe ID can be found.
    """
    for b in behaviors:
        if not isinstance(b, dict):
            continue
        ap = b.get("actionParams") or b.get("action_params") or {}
        if not isinstance(ap, dict):
            continue
        abp = ap.get("aiBehaviorParams") or ap.get("ai_behavior_params") or {}
        if not isinstance(abp, dict):
            continue
        for a in abp.get("actionsAttributes") or abp.get("actions_attributes") or []:
            if not isinstance(a, dict):
                continue
            pid = (a.get("metadata") or {}).get("pipeId")
            if pid:
                return str(pid)
    return None


def _behavior_input_validation_problems(exc: ValidationError) -> list[str]:
    """Turn ``BehaviorInput`` validation errors into short, actionable strings."""

    def _targets_name_field(err: dict) -> bool:
        loc = err.get("loc") or ()
        return bool(loc) and loc[-1] == "name"

    raw_errors = exc.errors()
    problems: list[str] = []

    if any(_targets_name_field(e) for e in raw_errors):
        problems.append(
            "Each behavior must include `name` (non-blank display name). "
            "Match create_ai_agent: `event_id` or `eventId`, plus `actionParams` with "
            "`aiBehaviorParams.instruction` and at least one entry in `actionsAttributes`."
        )

    for e in raw_errors:
        if _targets_name_field(e):
            continue
        loc = e.get("loc") or ()
        path = " -> ".join(str(p) for p in loc) if loc else "behavior"
        problems.append(f"{path}: {e.get('msg', 'validation error')}")

    return problems if problems else [str(exc)]


class AiAgentTools:
    """Declares MCP tools for AI Agent CRUD and status."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        """Register AI Agent tools on the MCP server."""

        def error_payload_from_exception(exc: BaseException) -> dict:
            msgs = extract_error_strings(exc)
            text = "; ".join(msgs) if msgs else str(exc)
            return build_ai_tool_error(text)

        async def _enrich_with_validation(
            exc: BaseException, behaviors: list[dict]
        ) -> str:
            """Enrich an error with validation context for RECORD_NOT_SAVED.

            When the error matches RECORD_NOT_SAVED, runs
            ``validate_behaviors_against_pipe`` to distinguish payload problems
            from pipe-specific restrictions. Falls back to standard enrichment
            when validation cannot run or for non-RECORD_NOT_SAVED errors.
            """
            enriched = enrich_behavior_error(exc, behaviors)

            if _RECORD_NOT_SAVED_PATTERN not in str(exc):
                return enriched

            pipe_id = _extract_pipe_id_from_behaviors(behaviors)
            if not pipe_id:
                return enriched

            try:
                (
                    field_ids,
                    phase_ids,
                    related_pipe_ids,
                ) = await fetch_pipe_validation_context(
                    client,
                    pipe_id,
                    timeout=VALIDATE_FETCH_TIMEOUT_SECONDS,
                )

                problems, _ = validate_behaviors_against_pipe(
                    behaviors,
                    pipe_id=pipe_id,
                    pipe_field_ids=field_ids,
                    pipe_phase_ids=phase_ids,
                    related_pipe_ids=related_pipe_ids,
                    unknown_action_types="error",
                )
                transition_problems = (
                    await collect_ai_behavior_move_transition_problems(
                        client, behaviors
                    )
                )
                all_problems = [*problems, *transition_problems]

                if not all_problems:
                    return enriched + _PAYLOAD_OK_SUFFIX
                return (
                    enriched
                    + "\n\nValidation found problems:\n"
                    + "\n".join(f"  - {p}" for p in all_problems)
                )
            except Exception:  # noqa: BLE001
                return enriched

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_ai_agent(
            ctx: Context,
            name: str,
            repo_uuid: str,
            instruction: str,
            behaviors: list[dict],
            data_source_ids: list[str] | None = None,
        ) -> dict:
            """Create an AI Agent and configure it in one call (GraphQL create + update).

            Requires a non-empty instruction and 1–5 behaviors. Instruction maps to the agent's
            Description field in the Pipefy UI (agent-level purpose). Each behavior's prompt/instruction
            lives in ``actionParams.aiBehaviorParams.instruction`` when sent to the API.

            Each behavior must also include ``actionParams.aiBehaviorParams.actionsAttributes`` with
            at least one action; otherwise the API rejects the update.

            Discovery workflow (call these tools first):
              1. ``get_pipe(pipe_id)`` → obtain ``uuid`` (use as ``repo_uuid``) and phase IDs.
              2. ``get_automation_events(pipe_id)`` → pick a valid ``event_id`` for the behavior
                 (e.g. ``card_created``, ``card_moved``, ``field_updated``).
              3. ``get_automation_actions(pipe_id)`` → find available ``actionType`` values.

            Behavior dict example::

              {
                "name": "When card is created: move to Doing",
                "event_id": "card_created",
                "actionParams": {
                  "aiBehaviorParams": {
                    "instruction": "Analyze the card and summarize key points.",
                    "actionsAttributes": [
                      {
                        "name": "Move to Doing",
                        "actionType": "move_card",
                        "metadata": {"destinationPhaseId": "<phase_id from get_pipe>"}
                      }
                    ]
                  }
                }
              }

            Known ``actionType`` values and their required ``metadata``:
              - ``move_card`` → ``{"destinationPhaseId": "<phase_id>"}``
              - ``update_card`` → ``{"pipeId": "<pipe_id>", "fieldsAttributes": [{"fieldId": "...", "inputMode": "fill_with_ai", "value": ""}]}``
              - ``create_card`` → ``{"pipeId": "<pipe_id>", "fieldsAttributes": [...]}``
              - ``create_connected_card`` → ``{"pipeId": "<pipe_id>", "fieldsAttributes": [...]}``
                Requires a pipe relation between source and destination pipes
                (verify with ``get_pipe_relations``).
              - ``create_table_record`` → ``{"tableId": "<table_id>", "fieldsAttributes": [{"fieldId": "...", "inputMode": "...", ...}, ...]}``
                (``pipeId`` not required; field IDs belong to the table.)
              - ``send_email_template`` → ``{"emailTemplateId": "<template_id>"}``;
                optional ``allowTemplateModifications`` (boolean).

            Optional ``actionParams.aiBehaviorParams.capabilitiesAttributes`` (list of strings), e.g.
            ``advanced_ocr``, ``web_search`` — pass-through; the API validates capability types.

            Optional ``eventParams`` per behavior (filters when the trigger fires):
              - ``field_updated`` event → ``{"triggerFieldIds": ["<field_id>"]}`` to fire only on specific fields.
              - ``card_moved`` event → ``{"to_phase_id": "<phase_id>"}`` to fire only when moving to a specific phase.

            Behavior keys accept both ``snake_case`` (``event_id``, ``event_params``,
            ``action_params``) and ``camelCase`` (``eventId``, ``eventParams``, ``actionParams``).
            The canonical wire format is camelCase.

            Important constraints:
              - **All-or-nothing save**: the API replaces the entire behaviors list on every call.
                Always send the complete set (1–5). Omitting a behavior deletes it.
              - **``update_card`` vs ``update_card_field``**: use ``update_card``; the API does
                not accept ``update_card_field`` as an actionType for AI behaviors.
              - **``metadata: {}`` is never valid** for known action types — it causes
                ``RECORD_NOT_SAVED``. Always include the required keys.
              - Behavior ``instruction``: use ``%{field:<internal_id>}``; slugs are rewritten to ids
                when an action supplies ``pipeId``. ``%{action:<uuid>}`` lines are appended per action;
                do not set ``referenceId`` manually. Bare ``{field:…}`` / ``{action:uuid}`` get a ``%``
                prefix before the API call.
            - **Template params:** per behavior you may pass ``template_params`` (or ``placeholders``)
                with string values and use ``{{name}}`` in any string (instruction, metadata IDs, etc.).
                Optionally set ``instruction_template`` instead of ``actionParams.aiBehaviorParams.instruction``
                — the tool interpolates and writes the final instruction before calling the API.

            Args:
                name: Agent display name.
                repo_uuid: UUID of the pipe (from ``get_pipe``), not the numeric pipe ID.
                instruction: Agent-level purpose (Pipefy UI "Description"; API ``instruction``).
                behaviors: 1–5 behavior dicts. Each requires ``name``, ``event_id``, and
                    ``actionParams.aiBehaviorParams`` with a non-empty ``actionsAttributes`` list.
                    Optional: ``eventParams`` to filter event triggers (e.g. ``triggerFieldIds``, ``to_phase_id``).
                    Optional: ``template_params`` / ``placeholders``, ``instruction_template``.
                    See example above for the full shape.
                data_source_ids: Optional knowledge-source IDs (same as ``update_ai_agent``).
            """
            await ctx.debug(
                f"create_ai_agent: name={name}, repo_uuid={repo_uuid}, "
                f"instruction_len={len(instruction)}, behaviors_count={len(behaviors)}, "
                f"data_source_ids={data_source_ids!r}"
            )
            if not name or not name.strip():
                return build_ai_tool_error("name must not be blank")
            if not repo_uuid or not repo_uuid.strip():
                return build_ai_tool_error("repo_uuid must not be blank")
            if not instruction or not instruction.strip():
                return build_ai_tool_error("instruction must not be blank")
            try:
                behaviors_expanded = expand_behaviors_placeholders(behaviors)
            except ValueError as exc:
                return build_ai_tool_error(str(exc))
            try:
                validated = CreateAiAgentInput(
                    name=name,
                    repo_uuid=repo_uuid,
                    instruction=instruction,
                    behaviors=behaviors_expanded,
                    data_source_ids=data_source_ids or [],
                )
            except ValidationError as exc:
                return build_ai_tool_error(str(exc))

            try:
                create_result = await client.create_ai_agent(validated)
            except Exception as exc:  # noqa: BLE001
                pipe_ids = collect_pipe_ids_from_behaviors(behaviors_expanded)
                perm_msg = await enrich_permission_denied_error(exc, pipe_ids, client)
                error_text = enrich_behavior_error(exc, behaviors_expanded)
                if perm_msg:
                    error_text = f"{perm_msg}\n{error_text}"
                return build_ai_tool_error(error_text)

            agent_uuid = create_result["agent_uuid"]

            resolved_behaviors = await resolve_field_slugs_to_numeric(
                client,
                [b.model_dump(by_alias=True) for b in validated.behaviors],
            )
            update_input = UpdateAiAgentInput(
                uuid=agent_uuid,
                name=validated.name,
                repo_uuid=validated.repo_uuid,
                instruction=validated.instruction,
                behaviors=resolved_behaviors,
                data_source_ids=validated.data_source_ids,
            )
            try:
                await client.update_ai_agent(update_input)
            except Exception as exc:  # noqa: BLE001
                pipe_ids = collect_pipe_ids_from_behaviors(behaviors_expanded)
                perm_msg = await enrich_permission_denied_error(exc, pipe_ids, client)
                error_text = await _enrich_with_validation(exc, behaviors_expanded)
                if perm_msg:
                    error_text = f"{perm_msg}\n{error_text}"
                return build_create_agent_partial_failure(
                    agent_uuid=agent_uuid,
                    error=error_text,
                )

            msg = f"AI Agent created and configured successfully. UUID: {agent_uuid}"
            return build_create_agent_success(agent_uuid=agent_uuid, message=msg)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_ai_agent(
            ctx: Context,
            uuid: str,
            name: str,
            repo_uuid: str,
            instruction: str,
            behaviors: list[dict],
            data_source_ids: list[str] | None = None,
        ) -> dict:
            """Update an AI Agent — replaces the entire config (all-or-nothing save).

            Always send the **complete** behaviors list (1–5). Omitting a behavior deletes it.
            Each behavior must include ``actionParams.aiBehaviorParams.actionsAttributes`` with at least
            one action (same constraint and shape as ``create_ai_agent`` — see its docstring for the
            full behavior dict example, discovery workflow, and constraints).

            To modify an existing agent: call ``get_ai_agent`` first, edit the returned config,
            and send the full payload back. The server replaces ``referenceId`` and appends
            ``%{action:<uuid>}`` lines to the instruction on each update (same as create flow).

            Known ``actionType`` values and their required ``metadata`` (same as ``create_ai_agent``):
              - ``move_card`` → ``{"destinationPhaseId": "<phase_id>"}``
              - ``update_card`` → ``{"pipeId": "<pipe_id>", "fieldsAttributes": [{"fieldId": "...", "inputMode": "fill_with_ai", "value": ""}]}``
              - ``create_card`` → ``{"pipeId": "<pipe_id>", "fieldsAttributes": [...]}``
              - ``create_connected_card`` → ``{"pipeId": "<pipe_id>", "fieldsAttributes": [...]}``
                (requires a pipe relation — verify with ``get_pipe_relations``).
              - ``create_table_record`` → ``{"tableId": "<table_id>", "fieldsAttributes": [...]}``
                (``pipeId`` not required; field IDs belong to the table.)
              - ``send_email_template`` → ``{"emailTemplateId": "<template_id>"}``;
                optional ``allowTemplateModifications`` (boolean).

            Optional ``actionParams.aiBehaviorParams.capabilitiesAttributes`` (list of strings), e.g.
            ``advanced_ocr``, ``web_search`` — pass-through; the API validates capability types.

            Args:
                uuid: UUID of the agent to update.
                name: Agent display name.
                repo_uuid: UUID of the pipe (from ``get_pipe``).
                instruction: Agent-level purpose (Pipefy UI "Description"; API ``instruction``).
                behaviors: 1–5 behavior dicts. Same shape as ``create_ai_agent``: each needs ``name``,
                    ``event_id``, and ``actionParams.aiBehaviorParams.actionsAttributes``.
                    Accepts both ``snake_case`` and ``camelCase`` keys.
                    Optional: ``template_params`` / ``placeholders`` and ``instruction_template``
                    (same interpolation as ``create_ai_agent``).
                data_source_ids: Optional list of data source IDs.
            """
            await ctx.debug(
                f"update_ai_agent: uuid={uuid}, behaviors_count={len(behaviors)}"
            )
            if not uuid or not uuid.strip():
                return build_ai_tool_error("uuid must not be blank")
            if not name or not name.strip():
                return build_ai_tool_error("name must not be blank")
            if not repo_uuid or not repo_uuid.strip():
                return build_ai_tool_error("repo_uuid must not be blank")
            try:
                behaviors_expanded = expand_behaviors_placeholders(behaviors)
            except ValueError as exc:
                return build_ai_tool_error(str(exc))
            resolved_behaviors = await resolve_field_slugs_to_numeric(
                client, behaviors_expanded
            )
            try:
                validated = UpdateAiAgentInput(
                    uuid=uuid,
                    name=name,
                    repo_uuid=repo_uuid,
                    instruction=instruction,
                    behaviors=resolved_behaviors,
                    data_source_ids=data_source_ids or [],
                )
            except ValidationError as exc:
                return build_ai_tool_error(str(exc))

            try:
                result = await client.update_ai_agent(validated)
            except Exception as exc:  # noqa: BLE001
                pipe_ids = collect_pipe_ids_from_behaviors(resolved_behaviors)
                perm_msg = await enrich_permission_denied_error(exc, pipe_ids, client)
                error_text = await _enrich_with_validation(exc, resolved_behaviors)
                if perm_msg:
                    error_text = f"{perm_msg}\n{error_text}"
                return build_ai_tool_error(error_text)

            return build_update_agent_success(
                agent_uuid=result["agent_uuid"],
                message=result["message"],
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def toggle_ai_agent_status(
            ctx: Context,
            uuid: str,
            active: bool,
        ) -> dict:
            """Enable or disable an AI Agent.

            Set active=true to activate or active=false to deactivate.
            Does not require resending the agent configuration.

            Args:
                uuid: UUID of the agent to enable/disable.
                active: True to activate, False to deactivate.
            """
            await ctx.debug(f"toggle_ai_agent_status: uuid={uuid}, active={active}")
            agent_uuid = uuid.strip()
            if not agent_uuid:
                return build_ai_tool_error("uuid must not be blank")

            try:
                result = await client.toggle_ai_agent_status(
                    agent_uuid=agent_uuid, active=active
                )
            except Exception as exc:  # noqa: BLE001
                return error_payload_from_exception(exc)

            return build_toggle_agent_status_success(message=result["message"])

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_ai_agent(ctx: Context, uuid: str) -> dict:
            """Get an AI Agent by UUID with full behavior configuration.

            Returns the complete agent config including, per behavior: ``eventParams``
            (trigger filters like ``to_phase_id``, ``triggerFieldIds``),
            ``actionParams.aiBehaviorParams`` with ``instruction``, ``actionsAttributes``
            (each with ``actionType``, ``metadata``, ``referenceId``), ``referencedFieldIds``,
            and ``dataSourceIds``.

            The response is complete enough to re-send via ``update_ai_agent`` (clone/modify
            workflow). Use ``get_pipe`` to find the pipe's ``uuid`` field, then ``get_ai_agents``
            to list agents and obtain UUIDs.

            Args:
                uuid: Agent UUID.
            """
            agent_uuid = uuid.strip()
            await ctx.debug(f"get_ai_agent: uuid={agent_uuid}")
            if not agent_uuid:
                return build_ai_tool_error("uuid must not be blank")
            try:
                agent = await client.get_ai_agent(agent_uuid)
            except Exception as exc:  # noqa: BLE001
                return error_payload_from_exception(exc)
            if not agent:
                return build_ai_tool_error(f"AI Agent not found: {agent_uuid}")
            return build_get_agent_success(agent)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_ai_agents(ctx: Context, repo_uuid: str) -> dict:
            """List all AI Agents for a pipe. Use before creating an agent to avoid duplicates.

            Args:
                repo_uuid: UUID of the pipe.
            """
            pipe_uuid = repo_uuid.strip()
            await ctx.debug(f"get_ai_agents: repo_uuid={pipe_uuid}")
            if not pipe_uuid:
                return build_ai_tool_error("repo_uuid must not be blank")
            try:
                agents = await client.get_ai_agents(pipe_uuid)
            except Exception as exc:  # noqa: BLE001
                return error_payload_from_exception(exc)
            return build_get_agents_success(agents)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
        )
        async def delete_ai_agent(
            ctx: Context, uuid: str, confirm: bool = False
        ) -> dict:
            """Delete an AI Agent permanently. This action is irreversible.

            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval. Elicitation does not authorize
            deletion (only ``confirm=True`` does).

            Args:
                uuid: Agent UUID.
                confirm: Must be ``True`` to run the delete mutation.
            """
            agent_uuid = uuid.strip()
            await ctx.debug(f"delete_ai_agent: uuid={agent_uuid}")
            if not agent_uuid:
                return build_ai_tool_error("uuid must not be blank")

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"AI agent (UUID: {agent_uuid})",
            )
            if guard is not None:
                return guard

            try:
                result = await client.delete_ai_agent(agent_uuid)
            except Exception as exc:  # noqa: BLE001
                return error_payload_from_exception(exc)
            if not result.get("success"):
                return build_ai_tool_error(
                    "delete_ai_agent failed: API returned success=false"
                )
            return build_delete_agent_success(
                message=f"AI Agent deleted successfully. UUID: {agent_uuid}",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        async def validate_ai_agent_behaviors(
            ctx: Context,
            pipe_id: PipefyId,
            behaviors: list[dict],
            strict_unknown_action_types: bool = True,
        ) -> dict:
            """Dry-run validation of AI Agent behaviors against a pipe's fields, phases, and relations.

            Call **before** ``create_ai_agent`` / ``update_ai_agent`` to catch problems early
            (invalid fieldIds, missing phase IDs, absent pipe relations for ``create_connected_card``).

            Known ``actionType`` values for pipe-context checks are:
            ``move_card``, ``update_card``, ``create_card``, ``create_connected_card``,
            ``create_table_record``, and ``send_email_template``.
            For ``move_card`` with trigger ``card_moved`` and ``eventParams.to_phase_id``/``toPhaseId``,
            the tool also checks that ``destinationPhaseId`` is allowed from that phase
            (``cards_can_be_moved_to_phases``).
            For ``create_table_record``, ``fieldsAttributes`` hold **table** field IDs — they are not
            validated against the source pipe; the tool adds a **warning** to verify IDs with
            ``get_table`` / ``get_table_record`` instead. ``send_email_template`` does not run
            pipe field-ID checks on its metadata.

            Runs Pydantic model validation (same as the mutation tools) plus cross-references
            against live pipe data. Does not persist anything.

            Response fields:
              - ``success``: the tool finished without an unexpected failure (same idea as other
                read tools); ``False`` only when returning a generic tool error (e.g. blank
                ``pipe_id``, or pipe fetch failed).
              - ``valid``: ``True`` only when ``problems`` is empty (no blocking issues).
              - ``warnings``: non-blocking notices (e.g. unknown ``actionType`` when
                ``strict_unknown_action_types`` is ``False``, or relations could not be loaded).
              - ``problems``, ``message``: blocking issues and a short summary.

            Example shapes::

              {"success": true, "valid": true, "problems": [], "warnings": [], "message": "..."}
              {"success": true, "valid": false, "problems": ["..."], "warnings": [], "message": "..."}
              {"success": true, "valid": true, "problems": [], "warnings": ["..."], "message": "..."}

            Args:
                pipe_id: Numeric pipe ID (used to fetch fields, phases, and relations).
                behaviors: 1–5 behavior dicts (same shape as ``create_ai_agent``). Each must
                    include ``name``, ``event_id`` (or ``eventId``), and ``actionParams`` with
                    ``aiBehaviorParams`` (``instruction`` + ``actionsAttributes``).
                strict_unknown_action_types: When ``True`` (default), unknown ``actionType`` values
                    are reported in ``problems``. When ``False``, they appear in ``warnings`` only.
            """
            pid = str(pipe_id).strip()
            if not pid:
                return build_ai_tool_error("pipe_id must not be blank")

            try:
                behaviors_expanded = expand_behaviors_placeholders(behaviors)
            except ValueError as exc:
                return {
                    "success": True,
                    "valid": False,
                    "problems": [str(exc)],
                    "warnings": [],
                    "message": "Behavior placeholder expansion failed.",
                }

            # Pydantic structural validation
            try:
                from pipefy_mcp.models.ai_agent import BehaviorInput

                for b in behaviors_expanded:
                    BehaviorInput.model_validate(b)
            except ValidationError as exc:
                return {
                    "success": True,
                    "valid": False,
                    "problems": _behavior_input_validation_problems(exc),
                    "warnings": [],
                    "message": "Behavior dicts failed structural validation (BehaviorInput).",
                }

            behaviors = behaviors_expanded

            try:
                (
                    field_ids,
                    phase_ids,
                    related_pipe_ids,
                ) = await fetch_pipe_validation_context(
                    client, pid, timeout=VALIDATE_FETCH_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                return build_ai_tool_error(
                    f"Timed out fetching pipe {pid} after {VALIDATE_FETCH_TIMEOUT_SECONDS}s"
                )
            except Exception as exc:  # noqa: BLE001
                return build_ai_tool_error(f"Failed to fetch pipe {pid}: {exc}")

            tool_warnings: list[str] = []
            if related_pipe_ids is None:
                await ctx.debug(
                    "Could not fetch pipe relations; skipping relation checks"
                )
                tool_warnings.append(
                    "Could not load pipe relations; create_connected_card pipeId targets "
                    "were not verified against relations."
                )

            # Collect target pipe IDs from cross-pipe actions and fetch their fields.
            # Skip when relations failed to load — without relation data, cross-pipe
            # field checks produce unreliable results.
            cross_pipe_field_ids: dict[str, set[str]] = {}
            target_pipe_ids: set[str] = set()
            if related_pipe_ids is not None:
                for b in behaviors:
                    ap = b.get("actionParams") or b.get("action_params") or {}
                    abp = (
                        ap.get("aiBehaviorParams") or ap.get("ai_behavior_params") or {}
                    )
                    for a in (
                        abp.get("actionsAttributes")
                        or abp.get("actions_attributes")
                        or []
                    ):
                        if not isinstance(a, dict):
                            continue
                        meta_pipe = str((a.get("metadata") or {}).get("pipeId", ""))
                        if meta_pipe and meta_pipe != pid:
                            target_pipe_ids.add(meta_pipe)

            for target_pid in target_pipe_ids:
                try:
                    target_data = await asyncio.wait_for(
                        client.get_pipe(target_pid),
                        timeout=VALIDATE_FETCH_TIMEOUT_SECONDS,
                    )
                    target_info = target_data.get("pipe", {})
                    target_fields: set[str] = set()
                    for phase in target_info.get("phases") or []:
                        for field in phase.get("fields") or []:
                            fid = field.get("id") or field.get("internal_id")
                            if fid:
                                target_fields.add(str(fid))
                    for field in target_info.get("start_form_fields") or []:
                        fid = field.get("id") or field.get("internal_id")
                        if fid:
                            target_fields.add(str(fid))
                    cross_pipe_field_ids[target_pid] = target_fields
                except Exception:  # noqa: BLE001
                    await ctx.debug(
                        f"Could not fetch target pipe {target_pid}; skipping its field checks"
                    )
                    tool_warnings.append(
                        f"Could not load fields for target pipe {target_pid}; "
                        f"fieldIds targeting it were not verified."
                    )

            # Optional: verify service account membership on cross-pipe targets.
            membership_problems: list[str] = []
            sa_ids = settings.pipefy.service_account_ids
            target_pipe_list = list(target_pipe_ids)
            if sa_ids and target_pipe_list:
                sa_set = set(sa_ids)
                try:
                    member_results = await asyncio.wait_for(
                        asyncio.gather(
                            *(
                                client.get_pipe_members(tpid)
                                for tpid in target_pipe_list
                            ),
                            return_exceptions=True,
                        ),
                        timeout=MEMBERSHIP_CHECK_TIMEOUT_SECONDS,
                    )
                    for tpid, mresult in zip(target_pipe_list, member_results):
                        if isinstance(mresult, BaseException):
                            await ctx.debug(
                                f"Could not check membership for pipe {tpid}: {mresult}"
                            )
                            continue
                        members = mresult.get("pipe", {}).get("members") or []
                        member_ids = {
                            str(m.get("user", {}).get("id", ""))
                            for m in members
                            if isinstance(m, dict)
                        }
                        if not sa_set & member_ids:
                            membership_problems.append(
                                f"Service account is not a member of target pipe "
                                f"{tpid}. Use invite_members to add it before "
                                f"creating the agent."
                            )
                except (TimeoutError, asyncio.TimeoutError):
                    await ctx.debug(
                        "Membership check timed out; skipping SA verification"
                    )

            unknown_action_types = "error" if strict_unknown_action_types else "warning"
            problems, helper_warnings = validate_behaviors_against_pipe(
                behaviors,
                pipe_id=pid,
                pipe_field_ids=field_ids,
                pipe_phase_ids=phase_ids,
                related_pipe_ids=related_pipe_ids,
                cross_pipe_field_ids=cross_pipe_field_ids or None,
                unknown_action_types=unknown_action_types,
            )
            transition_problems = await collect_ai_behavior_move_transition_problems(
                client, behaviors
            )
            problems = [*problems, *transition_problems, *membership_problems]
            warnings = [*tool_warnings, *helper_warnings]

            if problems:
                msg = f"Found {len(problems)} problem(s) in behaviors."
            elif warnings:
                msg = f"Validation passed with {len(warnings)} warning(s)."
            else:
                msg = "All behaviors passed validation."

            return {
                "success": True,
                "valid": len(problems) == 0,
                "problems": problems,
                "warnings": warnings,
                "message": msg,
            }
