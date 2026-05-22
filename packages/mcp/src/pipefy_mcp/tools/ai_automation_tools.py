"""MCP tools for AI Automation operations (create, update, read, delete, validate)."""

from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations
from pipefy_sdk import (
    CreateAiAutomationInput,
    PipefyClient,
    PipefyId,
    UpdateAiAutomationInput,
)
from pipefy_sdk.ai_preflight import (
    filter_ai_automation_summaries,
    validate_ai_automation_prompt_sdk,
)
from pydantic import ValidationError

from pipefy_mcp.tools.ai_tool_helpers import (
    build_ai_tool_error,
    build_create_automation_success,
    build_update_automation_success,
)
from pipefy_mcp.tools.automation_tool_helpers import (
    build_automation_error_payload,
    build_automation_mutation_success_payload,
    build_automation_read_success_payload,
    handle_automation_tool_graphql_error,
)
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.graphql_error_helpers import (
    extract_internal_api_bracket_codes,
    extract_internal_api_bracket_correlation_id,
    strip_internal_api_diagnostic_markers,
    with_debug_suffix,
)
from pipefy_mcp.tools.tool_error_envelope import tool_error_message
from pipefy_mcp.tools.validation_helpers import (
    validate_optional_tool_id,
    validate_tool_id,
)

AI_AUTOMATION_CREATE_FAILED = (
    "Could not create the AI automation. Verify pipe, fields, prompt, and that AI is "
    "enabled for the pipe."
)
AI_AUTOMATION_UPDATE_FAILED = (
    "Could not update the AI automation. Verify the automation ID and your changes."
)

AI_AUTOMATION_NOT_CONFIGURED = (
    "AI Automation requires service-account credentials "
    "(PIPEFY_SERVICE_ACCOUNT_URL, PIPEFY_SERVICE_ACCOUNT_CLIENT_ID, "
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET). "
    "Check .env.example for the required variables."
)


def _ai_automation_api_failure_payload(
    exc: BaseException, *, fallback: str, debug: bool = False
) -> dict:
    """Build a sanitized tool error for internal_api / service failures (default MCP).

    Args:
        exc: Exception from ``PipefyClient`` create/update AI automation.
        fallback: Stable message when the exception text is empty after stripping.
        debug: When True, append stripped bracket codes and correlation id to the message.
    """
    raw = str(exc).strip()
    cleaned = strip_internal_api_diagnostic_markers(raw) if raw else ""
    message = cleaned if cleaned else fallback
    if debug:
        codes = extract_internal_api_bracket_codes(raw)
        cid = extract_internal_api_bracket_correlation_id(raw)
        message = with_debug_suffix(
            message, debug=True, codes=codes, correlation_id=cid
        )
    return build_ai_tool_error(message)


class AiAutomationTools:
    """Declares MCP tools for AI Automation create and update."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        """Register AI Automation tools on the MCP server."""

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        async def validate_ai_automation_prompt(
            ctx: Context,
            pipe_id: PipefyId,
            prompt: str,
            field_ids: list[str],
            event_id: PipefyId | None = None,
        ) -> dict:
            """Pre-flight validation for AI automation prompts before calling ``create_ai_automation``.

            Checks that the prompt references valid pipe fields, output field IDs exist,
            the optional event ID is valid, AI is enabled on the pipe, and the
            org-level AI credit budget is usable. Catches common mistakes in a
            single read-only call instead of 2-3 failed mutation roundtrips.

            Credit-budget signals:
              - ``active: False`` or ``aiAutomation.enabled: False`` → **blocking problem**
                ("AI Automations are disabled on this organization…").
              - ``limit > 0 and usage >= limit and not hasAddon`` → **warning**
                ("AI credit budget exhausted…"). Rule creation still proceeds.
              - ``limit == 0`` → silent (common in sandbox/custom plans with
                uncapped billing).

            Args:
                pipe_id: Pipe where the AI automation will run.
                    Discover via: ``search_pipes`` or ``get_organization``.
                prompt: AI prompt text with ``%{internal_id}`` field references.
                    Discover via: ``get_phase_fields(phase_id)[].internal_id``.
                field_ids: Output field internal IDs where the AI writes results.
                    Discover via: ``get_phase_fields(phase_id)[].internal_id``.
                event_id: Optional trigger event ID to validate (e.g. ``card_created``).
                    Discover via: ``get_automation_events(pipe_id)``.

            Returns:
                ``valid`` is True when no problems found. ``problems`` lists blocking
                issues, ``warnings`` lists non-blocking notices, ``field_map`` maps
                referenced numeric IDs to field labels.
            """
            await ctx.debug(
                f"validate_ai_automation_prompt: pipe_id={pipe_id}, "
                f"field_ids={field_ids}, event_id={event_id}"
            )
            pid, pid_err = validate_tool_id(pipe_id, "pipe_id")
            if pid_err is not None:
                return build_ai_tool_error(tool_error_message(pid_err))

            eid: str | None = None
            if event_id is not None:
                ok_e, eid_validated, eid_err = validate_optional_tool_id(
                    event_id, "event_id"
                )
                if not ok_e:
                    # Mirror SDK shape: surface as a non-blocking problem rather
                    # than a hard tool error so callers can keep the structured
                    # ``problems`` list contract.
                    return {
                        "success": True,
                        "valid": False,
                        "problems": [tool_error_message(eid_err)],
                        "warnings": [],
                        "field_map": {},
                    }
                eid = eid_validated or None

            result = await validate_ai_automation_prompt_sdk(
                client,
                pid,
                prompt,
                [str(f) for f in field_ids],
                eid,
            )
            if not result.get("success"):
                return build_ai_tool_error(
                    str(result.get("error") or "Validation failed.")
                )
            return result

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        async def get_ai_automation(
            ctx: Context,
            automation_id: PipefyId,
            debug: bool = False,
        ) -> dict:
            """Load one automation by ID. For AI rules, ``action_id`` is ``generate_with_ai``.

            Delegates to the public GraphQL ``automation(id)`` query (same backend as
            ``get_automation``). Use after ``create_ai_automation`` or before
            ``update_ai_automation`` / ``delete_ai_automation`` to read ``name``, ``event_id``,
            ``action_params`` (including ``aiParams``), ``condition``, and ``active``.

            Does not require OAuth / internal API — only the standard Pipefy token.

            Args:
                automation_id: Automation rule ID (non-empty string or positive integer).
                debug: When True, append GraphQL error codes and correlation id on failures.

            Returns:
                On success, ``success``, ``message``, and ``data`` with the automation row (or
                empty when not found). On validation or GraphQL errors, ``success: False`` with
                ``error``.
            """
            await ctx.debug(f"get_ai_automation: automation_id={automation_id}")
            aid, err = validate_tool_id(automation_id, "automation_id")
            if err is not None:
                return build_automation_error_payload(message=tool_error_message(err))
            try:
                raw = await client.get_automation(aid)
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(
                    exc,
                    ctx,
                    debug,
                    resource_kind="ai_automation",
                    resource_id=aid,
                )
            message = (
                "No automation found for the given ID."
                if not raw
                else "AI automation retrieved."
            )
            return build_automation_read_success_payload(raw, message)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        async def get_ai_automations(
            ctx: Context,
            pipe_id: PipefyId,
            organization_id: PipefyId | None = None,
            debug: bool = False,
        ) -> dict:
            """List AI automations (``action_id`` = ``generate_with_ai``) for a pipe.

            Delegates to ``get_automations`` with this ``pipe_id`` and optional
            ``organization_id``. Results are filtered to AI prompt automations only.

            When ``organization_id`` is omitted, the server resolves the organization from the
            pipe first, then lists automations (**two** sequential API calls). When
            ``organization_id`` is provided, only **one** call is needed.

            Args:
                pipe_id: Pipe ID to list automations for (required).
                organization_id: Organization ID override; omit to resolve org from ``pipe_id``.
                debug: When True, append GraphQL error codes and correlation id on failures.

            Returns:
                On success, ``success``, ``message``, and ``data`` with the filtered list of
                automation summaries. On validation or GraphQL errors, ``success: False`` with
                ``error``.
            """
            await ctx.debug(
                f"get_ai_automations: pipe_id={pipe_id}, organization_id={organization_id}"
            )
            ok_o, org, org_err = validate_optional_tool_id(
                organization_id, "organization_id"
            )
            if not ok_o:
                return build_automation_error_payload(
                    message=tool_error_message(org_err)
                )
            pid, pid_err = validate_tool_id(pipe_id, "pipe_id")
            if pid_err is not None:
                return build_automation_error_payload(
                    message=tool_error_message(pid_err)
                )
            try:
                rows = await client.get_automations(
                    organization_id=org,
                    pipe_id=pid,
                )
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(
                    exc,
                    ctx,
                    debug,
                    resource_kind="pipe",
                    resource_id=pid,
                )
            filtered = filter_ai_automation_summaries(rows)
            return build_automation_read_success_payload(
                filtered,
                "AI automations listed.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
        )
        async def delete_ai_automation(
            ctx: Context[ServerSession, None],
            automation_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict:
            """Delete an AI automation rule permanently.

            Uses the same public GraphQL deletion as ``delete_automation``. Two-step flow:
            preview with ``confirm=False`` (default), then execute with ``confirm=True`` after
            explicit approval.

            Args:
                automation_id: Automation rule ID to delete.
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id on errors.

            Returns:
                On success, a mutation success payload. On validation or GraphQL errors,
                ``success: False`` with ``error``.
            """
            await ctx.debug(f"delete_ai_automation: automation_id={automation_id}")
            # No ai_automation_available check — deletion uses the public GraphQL
            # endpoint (AutomationService.delete_automation), not internal_api.
            # Only create/update require OAuth credentials.

            rid, rid_err = validate_tool_id(automation_id, "automation_id")
            if rid_err is not None:
                return build_automation_error_payload(
                    message=tool_error_message(rid_err)
                )

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"AI automation (ID: {automation_id})",
            )
            if guard is not None:
                return guard

            try:
                raw = await client.delete_automation(rid)
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(
                    exc,
                    ctx,
                    debug,
                    resource_kind="ai_automation",
                    resource_id=rid,
                )
            if not raw.get("success"):
                return build_automation_error_payload(
                    message="Delete AI automation did not succeed.",
                )
            return build_automation_mutation_success_payload({}, "deleted")

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_ai_automation(
            ctx: Context,
            name: str,
            event_id: PipefyId,
            pipe_id: PipefyId,
            prompt: str,
            field_ids: list[str],
            skills_ids: list[str] | None = None,
            event_params: dict | None = None,
            condition: dict | None = None,
            debug: bool = False,
        ) -> dict:
            """Create a simple AI automation that generates content with a prompt and writes the result to one or more card fields.

            Best for straightforward field-filling use cases (e.g. summarize, classify, extract data into a field).
            Requires AI to be enabled for the pipe in Pipefy UI.

            **Pre-flight (strongly recommended):** call ``validate_ai_automation_prompt`` first.
            It verifies prompt field references, output field IDs, event ID, AI-enabled
            status on the pipe, *and* the org-level AI credit budget. Without the pre-flight,
            a rule may be created successfully but never execute (e.g. AI Automations
            disabled at the org level, or credit budget exhausted).

            Args:
                name: Automation name.
                event_id: Event trigger (e.g. card_created, card_moved).
                    Discover via: ``get_automation_events(pipe_id)``.
                pipe_id: Pipe ID where the automation runs.
                    Discover via: ``search_pipes`` or ``get_organization``.
                prompt: AI prompt text. MUST reference at least one pipe field using %{internal_id} syntax (e.g. "Summarize the brief: %{425829426}"). Use the pipe's field internal_id values. Without a field reference the API rejects the request.
                    Discover via: ``get_phase_fields(phase_id)[].internal_id`` for ``%{internal_id}`` tokens.
                field_ids: List of field internal IDs where the AI writes its output.
                    Discover via: ``get_phase_fields(phase_id)[].internal_id``.
                skills_ids: AI skill IDs to attach. Defaults to empty (no skills).
                event_params: Trigger-specific filters (e.g. {"to_phase_id": "..."} for card_moved, {"triggerFieldIds": [...]} for field_updated).
                condition: Optional trigger condition dict. Omit to use the built-in placeholder (empty expression list) so Pipefy always receives a condition on create. Pass a dict to set a custom condition.
                debug: When True, append internal_api code and correlation_id to create failures (after sanitizing the main message).
            """
            await ctx.debug(
                f"create_ai_automation: name={name}, event_id={event_id}, pipe_id={pipe_id}"
            )
            if not client.ai_automation_available:
                return build_ai_tool_error(AI_AUTOMATION_NOT_CONFIGURED)

            optional_fields: dict = {}
            if skills_ids is not None:
                optional_fields["skills_ids"] = skills_ids
            if event_params is not None:
                optional_fields["event_params"] = event_params
            if condition is not None:
                optional_fields["condition"] = condition
            try:
                validated = CreateAiAutomationInput(
                    name=name,
                    event_id=event_id,
                    pipe_id=pipe_id,
                    prompt=prompt,
                    field_ids=field_ids,
                    **optional_fields,
                )
            except ValidationError as exc:
                return build_ai_tool_error(str(exc))

            try:
                result = await client.create_ai_automation(validated)
            except Exception as exc:  # noqa: BLE001
                return _ai_automation_api_failure_payload(
                    exc, fallback=AI_AUTOMATION_CREATE_FAILED, debug=debug
                )

            return build_create_automation_success(
                automation_id=result["automation_id"],
                message=result["message"],
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_ai_automation(
            ctx: Context,
            automation_id: PipefyId,
            name: str | None = None,
            active: bool | None = None,
            prompt: str | None = None,
            field_ids: list[str] | None = None,
            skills_ids: list[str] | None = None,
            event_params: dict | None = None,
            condition: dict | None = None,
            debug: bool = False,
        ) -> dict:
            """Update an existing AI automation's name, prompt, destination fields, or active state.

            Args:
                automation_id: ID of the automation to update.
                    Discover via: ``get_ai_automations(repo_uuid)[].id``.
                name: New automation name (optional).
                active: Whether the automation is active (optional).
                prompt: New AI prompt text (optional). Must use %{internal_id} syntax to reference pipe fields (e.g. "Classify %{425829426}").
                field_ids: New list of field internal IDs (optional).
                skills_ids: New list of AI skill IDs (optional).
                event_params: Trigger-specific filters (e.g. {"to_phase_id": "..."} for card_moved). Pass to change; omit to keep current.
                condition: New trigger condition dict. Omit to leave the automation's condition unchanged; pass a dict to replace it.
                debug: When True, append internal_api code and correlation_id to update failures (after sanitizing the main message).
            """
            await ctx.debug(f"update_ai_automation: automation_id={automation_id}")
            if not client.ai_automation_available:
                return build_ai_tool_error(AI_AUTOMATION_NOT_CONFIGURED)

            try:
                validated = UpdateAiAutomationInput(
                    automation_id=automation_id,
                    name=name,
                    active=active,
                    prompt=prompt,
                    field_ids=field_ids,
                    skills_ids=skills_ids,
                    event_params=event_params,
                    condition=condition,
                )
            except ValidationError as exc:
                return build_ai_tool_error(str(exc))

            try:
                result = await client.update_ai_automation(validated)
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(
                    exc,
                    ctx,
                    debug,
                    resource_kind="ai_automation",
                    resource_id=str(validated.automation_id),
                )

            return build_update_automation_success(
                automation_id=result["automation_id"],
                message=result["message"],
            )
