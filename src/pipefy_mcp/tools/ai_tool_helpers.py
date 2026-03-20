"""Typed response payloads and builder functions for AI tools."""

from __future__ import annotations

from typing import Literal

from typing_extensions import TypedDict

from pipefy_mcp.services.pipefy.types import AiAgentGraphPayload


class CreateAiAutomationSuccessPayload(TypedDict):
    success: Literal[True]
    automation_id: str
    message: str


class UpdateAiAutomationSuccessPayload(TypedDict):
    success: Literal[True]
    automation_id: str
    message: str


class CreateAiAgentSuccessPayload(TypedDict):
    success: Literal[True]
    agent_uuid: str
    message: str


class UpdateAiAgentSuccessPayload(TypedDict):
    success: Literal[True]
    agent_uuid: str
    message: str


class ToggleAiAgentStatusSuccessPayload(TypedDict):
    success: Literal[True]
    message: str


class GetAiAgentSuccessPayload(TypedDict):
    success: Literal[True]
    agent: AiAgentGraphPayload


class GetAiAgentsSuccessPayload(TypedDict):
    success: Literal[True]
    agents: list[AiAgentGraphPayload]


class DeleteAiAgentSuccessPayload(TypedDict):
    success: Literal[True]
    message: str


class AiToolErrorPayload(TypedDict):
    success: Literal[False]
    error: str


def build_create_automation_success(
    *, automation_id: str, message: str
) -> CreateAiAutomationSuccessPayload:
    """Build success payload for create_ai_automation."""
    return {"success": True, "automation_id": automation_id, "message": message}


def build_update_automation_success(
    *, automation_id: str, message: str
) -> UpdateAiAutomationSuccessPayload:
    """Build success payload for update_ai_automation."""
    return {"success": True, "automation_id": automation_id, "message": message}


def build_create_agent_success(
    *, agent_uuid: str, message: str
) -> CreateAiAgentSuccessPayload:
    """Build success payload for create_ai_agent."""
    return {"success": True, "agent_uuid": agent_uuid, "message": message}


def build_update_agent_success(
    *, agent_uuid: str, message: str
) -> UpdateAiAgentSuccessPayload:
    """Build success payload for update_ai_agent."""
    return {"success": True, "agent_uuid": agent_uuid, "message": message}


def build_toggle_agent_status_success(
    *, message: str
) -> ToggleAiAgentStatusSuccessPayload:
    """Build success payload for toggle_ai_agent_status."""
    return {"success": True, "message": message}


def build_get_agent_success(agent: AiAgentGraphPayload) -> GetAiAgentSuccessPayload:
    """Build success payload for get_ai_agent."""
    return {"success": True, "agent": agent}


def build_get_agents_success(
    agents: list[AiAgentGraphPayload],
) -> GetAiAgentsSuccessPayload:
    """Build success payload for get_ai_agents."""
    return {"success": True, "agents": agents}


def build_delete_agent_success(*, message: str) -> DeleteAiAgentSuccessPayload:
    """Build success payload for delete_ai_agent."""
    return {"success": True, "message": message}


def build_ai_tool_error(message: str) -> AiToolErrorPayload:
    """Build error payload for any AI tool."""
    return {"success": False, "error": message}
