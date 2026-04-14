"""MCP tools for AI Automation operations (create, update, read, delete)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from pipefy_mcp.models.ai_automation import (
    CreateAiAutomationInput,
    UpdateAiAutomationInput,
)
from pipefy_mcp.models.validators import PipefyId
from pipefy_mcp.services.pipefy import PipefyClient
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
from pipefy_mcp.tools.automation_tools import (
    _normalize_optional_filter,
    _normalize_required_id,
)
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.graphql_error_helpers import (
    extract_internal_api_bracket_codes,
    extract_internal_api_bracket_correlation_id,
    strip_internal_api_diagnostic_markers,
    with_debug_suffix,
)

AI_AUTOMATION_CREATE_FAILED = (
    "Could not create the AI automation. Verify pipe, fields, prompt, and that AI is "
    "enabled for the pipe."
)
AI_AUTOMATION_UPDATE_FAILED = (
    "Could not update the AI automation. Verify the automation ID and your changes."
)

AI_AUTOMATION_NOT_CONFIGURED = (
    "AI Automation requires OAuth credentials "
    "(PIPEFY_OAUTH_CLIENT, PIPEFY_OAUTH_SECRET, PIPEFY_OAUTH_URL). "
    "Check .env.example for the required variables."
)

GENERATE_WITH_AI_ACTION_ID = "generate_with_ai"


def _reject_non_positive_numeric_id(aid: str) -> bool:
    """True when ``aid`` is only digits (optional leading ``-``) and <= 0.

    ``PipefyId`` coerces ``-1`` to ``"-1"``; ``_normalize_required_id`` would
    otherwise accept that string.
    """
    s = aid.strip()
    if s.startswith("-") and s[1:].isdigit():
        return True
    return bool(s.isdigit() and int(s) <= 0)


def _is_ai_automation_summary_row(row: Any) -> bool:
    """True when the listing row is an AI (prompt) automation."""
    if not isinstance(row, dict):
        return False
    action_id = row.get("action_id") or row.get("actionId")
    if action_id == GENERATE_WITH_AI_ACTION_ID:
        return True
    ap = row.get("action_params") or row.get("actionParams")
    if isinstance(ap, dict) and (
        ap.get("aiParams") is not None or ap.get("ai_params") is not None
    ):
        return True
    return False


def _filter_ai_automation_summaries(rows: list[Any]) -> list[Any]:
    return [r for r in rows if _is_ai_automation_summary_row(r)]


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
            aid = _normalize_required_id(automation_id)
            if aid is None or _reject_non_positive_numeric_id(aid):
                return build_automation_error_payload(
                    message=(
                        "Invalid 'automation_id': provide a non-empty string or "
                        "positive integer."
                    ),
                )
            try:
                raw = await client.get_automation(aid)
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(exc, ctx, debug)
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
            ok_o, org = _normalize_optional_filter(organization_id)
            if not ok_o:
                return build_automation_error_payload(
                    message=(
                        "Invalid 'organization_id': provide a non-empty string or "
                        "positive integer when supplied."
                    ),
                )
            pid = _normalize_required_id(pipe_id)
            if pid is None or _reject_non_positive_numeric_id(pid):
                return build_automation_error_payload(
                    message=(
                        "Invalid 'pipe_id': provide a non-empty string or "
                        "positive integer."
                    ),
                )
            try:
                rows = await client.get_automations(
                    organization_id=org,
                    pipe_id=pid,
                )
            except Exception as exc:  # noqa: BLE001
                return await handle_automation_tool_graphql_error(exc, ctx, debug)
            filtered = _filter_ai_automation_summaries(rows)
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
            if not client.ai_automation_available:
                return build_ai_tool_error(AI_AUTOMATION_NOT_CONFIGURED)

            rid = _normalize_required_id(automation_id)
            if rid is None or _reject_non_positive_numeric_id(rid):
                return build_automation_error_payload(
                    message=(
                        "Invalid 'automation_id': provide a non-empty string or "
                        "positive integer."
                    ),
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
                return await handle_automation_tool_graphql_error(exc, ctx, debug)
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

            Args:
                name: Automation name.
                event_id: Event trigger (e.g. card_created, card_moved).
                pipe_id: Pipe ID where the automation runs.
                prompt: AI prompt text. MUST reference at least one pipe field using %{internal_id} syntax (e.g. "Summarize the brief: %{425829426}"). Use the pipe's field internal_id values. Without a field reference the API rejects the request.
                field_ids: List of field internal IDs where the AI writes its output.
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
                return _ai_automation_api_failure_payload(
                    exc, fallback=AI_AUTOMATION_UPDATE_FAILED, debug=debug
                )

            return build_update_automation_success(
                automation_id=result["automation_id"],
                message=result["message"],
            )
