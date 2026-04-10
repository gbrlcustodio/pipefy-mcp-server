"""MCP tools for AI Automation operations (create + update)."""

from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP
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
