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


class CreateAgentPartialFailurePayload(TypedDict):
    success: Literal[False]
    agent_uuid: str
    error: str


def build_create_automation_success(
    *, automation_id: str, message: str
) -> CreateAiAutomationSuccessPayload:
    """Successful AI automation create.

    Args:
        automation_id: New automation id from the API.
        message: Short summary for the client.
    """
    return {"success": True, "automation_id": automation_id, "message": message}


def build_update_automation_success(
    *, automation_id: str, message: str
) -> UpdateAiAutomationSuccessPayload:
    """Successful AI automation update.

    Args:
        automation_id: Target automation id.
        message: Short summary for the client.
    """
    return {"success": True, "automation_id": automation_id, "message": message}


def build_create_agent_success(
    *, agent_uuid: str, message: str
) -> CreateAiAgentSuccessPayload:
    """Successful AI agent create.

    Args:
        agent_uuid: New agent UUID from the API.
        message: Short summary for the client.
    """
    return {"success": True, "agent_uuid": agent_uuid, "message": message}


def build_update_agent_success(
    *, agent_uuid: str, message: str
) -> UpdateAiAgentSuccessPayload:
    """Successful AI agent update.

    Args:
        agent_uuid: Target agent UUID.
        message: Short summary for the client.
    """
    return {"success": True, "agent_uuid": agent_uuid, "message": message}


def build_toggle_agent_status_success(
    *, message: str
) -> ToggleAiAgentStatusSuccessPayload:
    """Successful agent enable/disable.

    Args:
        message: Short summary for the client.
    """
    return {"success": True, "message": message}


def build_get_agent_success(agent: AiAgentGraphPayload) -> GetAiAgentSuccessPayload:
    """Single-agent read envelope.

    Args:
        agent: ``aiAgent`` subtree (may be empty dict when missing).
    """
    return {"success": True, "agent": agent}


def build_get_agents_success(
    agents: list[AiAgentGraphPayload],
) -> GetAiAgentsSuccessPayload:
    """List-agents read envelope.

    Args:
        agents: Unwrapped connection nodes for the repo.
    """
    return {"success": True, "agents": agents}


def build_delete_agent_success(*, message: str) -> DeleteAiAgentSuccessPayload:
    """Successful AI agent delete.

    Args:
        message: Short summary for the client.
    """
    return {"success": True, "message": message}


def build_ai_tool_error(message: str) -> AiToolErrorPayload:
    """Generic AI-tool failure envelope.

    Args:
        message: User-visible failure reason.
    """
    return {"success": False, "error": message}


def build_create_agent_partial_failure(
    *, agent_uuid: str, error: str
) -> CreateAgentPartialFailurePayload:
    """Create OK but follow-up update failed — surface UUID for recovery.

    Args:
        agent_uuid: Agent UUID from ``createAiAgent`` (retry update or delete).
        error: Why the chained update failed.
    """
    return {"success": False, "agent_uuid": agent_uuid, "error": error}
