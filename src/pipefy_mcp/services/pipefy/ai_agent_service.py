"""Service for AI Agent create and update operations."""

from __future__ import annotations

import copy
import uuid

from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.models.ai_agent import CreateAiAgentInput, UpdateAiAgentInput
from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.ai_agent_queries import (
    CREATE_AI_AGENT_MUTATION,
    TOGGLE_AI_AGENT_STATUS_MUTATION,
    UPDATE_AI_AGENT_MUTATION,
)
from pipefy_mcp.services.pipefy.types import AgentServiceResult, ToggleAgentStatusResult
from pipefy_mcp.settings import PipefySettings


def inject_reference_ids(behaviors: list[dict]) -> list[dict]:
    """Generate and inject referenceIds into behavior actions.

    For each behavior, generates a UUID v4 per action in actionsAttributes,
    sets it as the action's referenceId, and appends a %{action:<uuid>}
    placeholder to the behavior's instruction.

    Args:
        behaviors: List of behavior dicts with actionParams.aiBehaviorParams.

    Returns:
        New list of behaviors (deep copy) with referenceIds injected.
        Original input is never mutated.
    """
    result = [copy.deepcopy(b) for b in behaviors]

    for behavior in result:
        ai_params = (behavior.get("actionParams") or {}).get("aiBehaviorParams")
        if not ai_params:
            continue

        actions = ai_params.get("actionsAttributes")
        if not actions:
            continue

        placeholders: list[str] = []
        for action in actions:
            ref_id = str(uuid.uuid4())
            action["referenceId"] = ref_id
            placeholders.append(f"%{{action:{ref_id}}}")

        instruction = ai_params.get("instruction") or ""
        separator = "\n" if instruction else ""
        ai_params["instruction"] = instruction + separator + "\n".join(placeholders)

    return result


class AiAgentService(BasePipefyClient):
    """Service for creating and updating AI Agents via GraphQL."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
    ) -> None:
        """Create the service.

        Args:
            settings: Pipefy settings (graphql_url, OAuth credentials).
            auth: Optional pre-built OAuth2 auth to share token cache.
        """
        super().__init__(settings=settings, auth=auth)

    async def create_agent(self, agent_input: CreateAiAgentInput) -> AgentServiceResult:
        """Create an AI Agent (empty, no behaviors).

        Args:
            agent_input: Validated create input with name and repo_uuid.

        Returns:
            Dict with agent_uuid and message.

        Raises:
            ValueError: When API response is missing agent.uuid.
        """
        variables = {
            "agent": {
                "name": agent_input.name,
                "repoUuid": agent_input.repo_uuid,
            }
        }

        response = await self.execute_query(CREATE_AI_AGENT_MUTATION, variables)

        agent = response.get("createAiAgent", {}).get("agent")
        if not agent or "uuid" not in agent:
            raise ValueError(
                "Unexpected API payload: agent.uuid missing from createAiAgent response"
            )

        agent_uuid = str(agent["uuid"])
        return {
            "agent_uuid": agent_uuid,
            "message": f"AI Agent created successfully. UUID: {agent_uuid}",
        }

    async def update_agent(self, agent_input: UpdateAiAgentInput) -> AgentServiceResult:
        """Update an AI Agent with instruction and behaviors.

        Calls inject_reference_ids on behaviors before building the payload
        so each action gets a fresh UUID v4 referenceId.

        Args:
            agent_input: Validated update input with uuid, name, repo_uuid, behaviors.

        Returns:
            Dict with agent_uuid and message.

        Raises:
            ValueError: When API response is missing agent.uuid.
        """
        behaviors_raw = [
            b.model_dump(by_alias=True, exclude_none=True)
            for b in agent_input.behaviors
        ]
        behaviors_with_refs = inject_reference_ids(behaviors_raw)

        variables = {
            "uuid": agent_input.uuid,
            "agent": {
                "name": agent_input.name,
                "repoUuid": agent_input.repo_uuid,
                "instruction": agent_input.instruction or "",
                "dataSourceIds": agent_input.data_source_ids,
                "behaviors": behaviors_with_refs,
            },
        }

        response = await self.execute_query(UPDATE_AI_AGENT_MUTATION, variables)

        agent = response.get("updateAiAgent", {}).get("agent")
        if not agent or "uuid" not in agent:
            raise ValueError(
                "Unexpected API payload: agent.uuid missing from updateAiAgent response"
            )

        agent_uuid = str(agent["uuid"])
        return {
            "agent_uuid": agent_uuid,
            "message": f"AI Agent updated successfully. UUID: {agent_uuid}",
        }

    async def toggle_agent_status(
        self, agent_uuid: str, active: bool
    ) -> ToggleAgentStatusResult:
        """Enable or disable an AI Agent.

        Args:
            agent_uuid: Agent UUID.
            active: True to activate, False to deactivate.

        Returns:
            Dict with success flag and message.

        Raises:
            ValueError: When the API reports failure.
        """
        variables = {"uuid": agent_uuid, "active": active}
        response = await self.execute_query(TOGGLE_AI_AGENT_STATUS_MUTATION, variables)

        result = response.get("updateAiAgentStatus", {})
        if not result.get("success"):
            raise ValueError("Toggle agent status failed: API returned success=false")

        action = "activated" if active else "deactivated"
        return {
            "success": True,
            "message": f"AI Agent {action} successfully.",
        }
