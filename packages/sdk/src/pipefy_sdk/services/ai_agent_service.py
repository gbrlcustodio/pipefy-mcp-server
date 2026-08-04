"""Service for AI Agent create, read, update, and delete operations."""

from __future__ import annotations

import copy
import uuid
from typing import Any

from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.models.ai_agent import CreateAiAgentInput, UpdateAiAgentInput
from pipefy_sdk.queries.ai_agent_queries import (
    CREATE_AI_AGENT_MUTATION,
    DELETE_AI_AGENT_MUTATION,
    GET_AI_AGENT_QUERY,
    GET_AI_AGENTS_QUERY,
    TOGGLE_AI_AGENT_STATUS_MUTATION,
    UPDATE_AI_AGENT_MUTATION,
)
from pipefy_sdk.services.types import (
    AgentServiceResult,
    AiAgentGraphPayload,
    ToggleAgentStatusResult,
)
from pipefy_sdk.utils.relay import unwrap_relay_connection_nodes


def inject_reference_ids(behaviors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deep-copy behaviors and assign a UUID ``referenceId`` per action; append ``%{action:<uuid>}`` lines to instruction.

    Args:
        behaviors: Behavior dicts with ``actionParams.aiBehaviorParams.actionsAttributes``.
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


def resolve_update_disabled_at(provided: str | None, current: str | None) -> str | None:
    """Choose ``disabledAt`` for updateAiAgent; never clear (activation is toggle-only)."""
    if provided is not None:
        return provided
    if current:
        return current
    return None


class AiAgentService:
    """Service for AI Agent CRUD via GraphQL."""

    def __init__(self, *, executor: GraphQLExecutor) -> None:
        self._executor = executor

    async def create_agent(self, agent_input: CreateAiAgentInput) -> AgentServiceResult:
        """Create an AI Agent (empty, no behaviors).

        Args:
            agent_input: Validated create input with name and repo_uuid.

        Raises:
            ValueError: When API response is missing agent.uuid.
        """
        agent_payload: dict[str, Any] = {
            "name": agent_input.name,
            "repoUuid": agent_input.repo_uuid,
        }
        if agent_input.disabled_at is not None:
            agent_payload["disabledAt"] = agent_input.disabled_at

        variables = {"agent": agent_payload}

        response = await self._executor.execute_query(
            CREATE_AI_AGENT_MUTATION, variables
        )

        agent = response.get("createAiAgent", {}).get("agent")
        if not agent or "uuid" not in agent:
            raise ValueError(
                "Unexpected API payload: agent.uuid missing from createAiAgent response"
            )

        agent_uuid = str(agent["uuid"])
        return {
            "agent_uuid": agent_uuid,
            "message": f"AI Agent created successfully. UUID: {agent_uuid}",
            "disabled_at": agent.get("disabledAt"),
            "active": agent.get("disabledAt") is None,
        }

    async def update_agent(self, agent_input: UpdateAiAgentInput) -> AgentServiceResult:
        """Update an AI Agent with instruction and behaviors.

        Args:
            agent_input: Validated update input with uuid, name, repo_uuid, behaviors.

        Raises:
            ValueError: When API response is missing agent.uuid.
        """
        behaviors_raw = [
            b.model_dump(by_alias=True, exclude_none=True)
            for b in agent_input.behaviors
        ]
        behaviors_with_refs = inject_reference_ids(behaviors_raw)

        disabled_at = agent_input.disabled_at
        if agent_input.disabled_at is None and agent_input.preserve_disabled_at:
            current = await self.get_agent(agent_input.uuid)
            raw = current.get("disabledAt")
            current_disabled_at = raw if isinstance(raw, str) else None
            disabled_at = resolve_update_disabled_at(None, current_disabled_at)

        agent_payload: dict[str, Any] = {
            "name": agent_input.name,
            "repoUuid": agent_input.repo_uuid,
            "instruction": agent_input.instruction or "",
            "dataSourceIds": agent_input.data_source_ids,
            "behaviors": behaviors_with_refs,
        }
        if disabled_at is not None:
            agent_payload["disabledAt"] = disabled_at

        variables = {
            "uuid": agent_input.uuid,
            "agent": agent_payload,
        }

        response = await self._executor.execute_query(
            UPDATE_AI_AGENT_MUTATION, variables
        )

        agent = response.get("updateAiAgent", {}).get("agent")
        if not agent or "uuid" not in agent:
            raise ValueError(
                "Unexpected API payload: agent.uuid missing from updateAiAgent response"
            )

        agent_uuid = str(agent["uuid"])
        return {
            "agent_uuid": agent_uuid,
            "message": f"AI Agent updated successfully. UUID: {agent_uuid}",
            "disabled_at": agent.get("disabledAt"),
            "active": agent.get("disabledAt") is None,
        }

    async def toggle_agent_status(
        self, agent_uuid: str, active: bool
    ) -> ToggleAgentStatusResult:
        """Enable or disable an AI Agent.

        Args:
            agent_uuid: Agent UUID.
            active: True to activate, False to deactivate.

        Raises:
            ValueError: When the API reports failure.
        """
        variables = {"uuid": agent_uuid, "active": active}
        response = await self._executor.execute_query(
            TOGGLE_AI_AGENT_STATUS_MUTATION, variables
        )

        result = response.get("updateAiAgentStatus", {})
        if not result.get("success"):
            raise ValueError("Toggle agent status failed: API returned success=false")

        action = "activated" if active else "deactivated"
        return {
            "success": True,
            "message": f"AI Agent {action} successfully.",
        }

    async def get_agent(self, agent_uuid: str) -> AiAgentGraphPayload:
        """Load a single AI Agent by UUID.

        Args:
            agent_uuid: Agent UUID.

        Returns:
            ``aiAgent`` fields when found; empty dict when the API returns null or a non-object.
        """
        response = await self._executor.execute_query(
            GET_AI_AGENT_QUERY, {"uuid": agent_uuid}
        )
        agent = response.get("aiAgent")
        return agent if isinstance(agent, dict) else {}

    async def get_agents(self, repo_uuid: str) -> list[AiAgentGraphPayload]:
        """List AI Agents for a pipe (repo).

        Args:
            repo_uuid: Pipe UUID (`repoUuid` in the API).

        Returns:
            List of agent dicts from `aiAgents`.
        """
        response = await self._executor.execute_query(
            GET_AI_AGENTS_QUERY, {"repoUuid": repo_uuid}
        )
        return unwrap_relay_connection_nodes(response.get("aiAgents"))

    async def delete_agent(self, agent_uuid: str) -> dict[str, Any]:
        """Delete an AI Agent permanently.

        Args:
            agent_uuid: Agent UUID.

        Returns:
            Dict with `success` bool from `deleteAiAgent`.
        """
        response = await self._executor.execute_query(
            DELETE_AI_AGENT_MUTATION, {"uuid": agent_uuid}
        )
        payload = response.get("deleteAiAgent", {})
        return {"success": bool(payload.get("success"))}
