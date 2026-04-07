"""Service for AI Automation create and update operations."""

from __future__ import annotations

from typing import Any

from pipefy_mcp.models.ai_automation import (
    CreateAiAutomationInput,
    UpdateAiAutomationInput,
)
from pipefy_mcp.services.pipefy.internal_api_client import InternalApiClient
from pipefy_mcp.services.pipefy.queries.ai_automation_queries import (
    AI_CREATE_AUTOMATION_MUTATION,
    AI_UPDATE_AUTOMATION_MUTATION,
)
from pipefy_mcp.services.pipefy.types import AutomationServiceResult

ACTION_ID_GENERATE_WITH_AI = "generate_with_ai"


class AiAutomationService:
    """Service for creating and updating AI Automations via the internal API."""

    def __init__(self, client: InternalApiClient) -> None:
        """Attach the client used for ``internal_api`` GraphQL calls.

        Args:
            client: Configured :class:`InternalApiClient` instance.
        """
        self._client = client

    async def create_automation(
        self, automation_input: CreateAiAutomationInput
    ) -> AutomationServiceResult:
        """Create an AI Automation (generate_with_ai action).

        Args:
            automation_input: Validated create input.

        Raises:
            ValueError: When API response is missing automation.id.
        """
        variables = {
            "name": automation_input.name,
            "action_id": ACTION_ID_GENERATE_WITH_AI,
            "event_id": automation_input.event_id,
            "event_repo_id": automation_input.pipe_id,
            "action_repo_id": automation_input.action_repo_id
            or automation_input.pipe_id,
            "action_params": {
                "aiParams": {
                    "value": automation_input.prompt,
                    "fieldIds": automation_input.field_ids,
                    "skillsIds": automation_input.skills_ids,
                }
            },
            "condition": automation_input.condition,
        }

        response = await self._client.execute_query(
            AI_CREATE_AUTOMATION_MUTATION, variables
        )

        create_result = response.get("createAutomation", {})
        error_details = create_result.get("error_details")
        if error_details:
            messages = error_details.get("messages", [])
            raise ValueError(f"API error: {'; '.join(messages)}")

        automation = create_result.get("automation")
        if not automation or "id" not in automation:
            raise ValueError(
                "Unexpected API payload: automation.id missing from createAutomation response"
            )

        automation_id = str(automation["id"])
        return {
            "automation_id": automation_id,
            "message": f"AI Automation created successfully. ID: {automation_id}",
        }

    async def update_automation(
        self, automation_input: UpdateAiAutomationInput
    ) -> AutomationServiceResult:
        """Update an existing AI Automation.

        Args:
            automation_input: Validated update input.

        Raises:
            ValueError: When API response is missing automation.id.
        """
        input_dict: dict[str, Any] = {"id": automation_input.automation_id}
        if automation_input.name is not None:
            input_dict["name"] = automation_input.name
        if automation_input.active is not None:
            input_dict["active"] = automation_input.active

        ai_params: dict[str, Any] = {}
        if automation_input.prompt is not None:
            ai_params["value"] = automation_input.prompt
        if automation_input.field_ids is not None:
            ai_params["fieldIds"] = automation_input.field_ids
        if automation_input.skills_ids is not None:
            ai_params["skillsIds"] = automation_input.skills_ids
        if ai_params:
            input_dict["action_params"] = {"aiParams": ai_params}

        if automation_input.condition is not None:
            input_dict["condition"] = automation_input.condition

        variables = {"input": input_dict}

        response = await self._client.execute_query(
            AI_UPDATE_AUTOMATION_MUTATION, variables
        )

        update_result = response.get("updateAutomation", {})
        error_details = update_result.get("error_details")
        if error_details:
            messages = error_details.get("messages", [])
            raise ValueError(f"API error: {'; '.join(messages)}")

        automation = update_result.get("automation")
        if not automation or "id" not in automation:
            raise ValueError(
                "Unexpected API payload: automation.id missing from updateAutomation response"
            )

        automation_id = str(automation["id"])
        return {
            "automation_id": automation_id,
            "message": f"AI Automation updated successfully. ID: {automation_id}",
        }
