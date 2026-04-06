"""MCP tools for AI Automation operations (create + update)."""

from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from pipefy_mcp.models.ai_automation import (
    CreateAiAutomationInput,
    UpdateAiAutomationInput,
)
from pipefy_mcp.services.pipefy.ai_automation_service import AiAutomationService
from pipefy_mcp.tools.ai_tool_helpers import (
    build_ai_tool_error,
    build_create_automation_success,
    build_update_automation_success,
)


class AiAutomationTools:
    """Declares MCP tools for AI Automation create and update."""

    @staticmethod
    def register(mcp: FastMCP, service: AiAutomationService) -> None:
        """Register AI Automation tools on the MCP server."""

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_ai_automation(
            ctx: Context,
            name: str,
            event_id: str,
            pipe_id: str,
            prompt: str,
            field_ids: list[str],
            skills_ids: list[str] | None = None,
            condition: dict | None = None,
        ) -> dict:
            """Create a simple AI automation that generates content with a prompt and writes the result to one or more card fields.

            Best for straightforward field-filling use cases (e.g. summarize, classify, extract data into a field).
            Requires AI to be enabled for the pipe in Pipefy UI.

            Args:
                name: Automation name.
                event_id: Event trigger (e.g. card_created, card_moved).
                pipe_id: Pipe ID where the automation runs.
                prompt: AI prompt text that generates the content.
                field_ids: List of field internal IDs to write the result to.
                skills_ids: AI skill IDs to attach. Defaults to empty (no skills).
                condition: Optional condition structure for the automation trigger.
            """
            ctx.debug(
                f"create_ai_automation: name={name}, event_id={event_id}, pipe_id={pipe_id}"
            )
            optional_fields: dict = {}
            if skills_ids is not None:
                optional_fields["skills_ids"] = skills_ids
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
                result = await service.create_automation(validated)
            except Exception as exc:  # noqa: BLE001
                return build_ai_tool_error(str(exc))

            return build_create_automation_success(
                automation_id=result["automation_id"],
                message=result["message"],
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_ai_automation(
            ctx: Context,
            automation_id: str,
            name: str | None = None,
            active: bool | None = None,
            prompt: str | None = None,
            field_ids: list[str] | None = None,
            skills_ids: list[str] | None = None,
            condition: dict | None = None,
        ) -> dict:
            """Update an existing AI automation's name, prompt, destination fields, or active state.

            Args:
                automation_id: ID of the automation to update.
                name: New automation name (optional).
                active: Whether the automation is active (optional).
                prompt: New AI prompt text (optional).
                field_ids: New list of field internal IDs (optional).
                skills_ids: New list of AI skill IDs (optional).
                condition: New condition structure (optional).
            """
            ctx.debug(f"update_ai_automation: automation_id={automation_id}")
            try:
                validated = UpdateAiAutomationInput(
                    automation_id=automation_id,
                    name=name,
                    active=active,
                    prompt=prompt,
                    field_ids=field_ids,
                    skills_ids=skills_ids,
                    condition=condition,
                )
            except ValidationError as exc:
                return build_ai_tool_error(str(exc))

            try:
                result = await service.update_automation(validated)
            except Exception as exc:  # noqa: BLE001
                return build_ai_tool_error(str(exc))

            return build_update_automation_success(
                automation_id=result["automation_id"],
                message=result["message"],
            )
