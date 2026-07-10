"""Typed response payloads and builder functions for AI tools."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal, cast

from pipefy_sdk import AiAgentGraphPayload, BehaviorPayload
from pipefy_sdk.ai_pipe_validation import (
    KNOWN_AI_ACTION_TYPES,
    build_field_slug_map,
    collect_pipe_ids_from_behaviors,
    fetch_pipe_validation_context,
    pipe_ids_from_behavior,
    resolve_and_populate_field_refs,
    resolve_field_slugs_to_numeric,
    validate_behaviors_against_pipe,
)
from pydantic import ValidationError
from typing_extensions import TypedDict

from pipefy_mcp.core.tool_error_envelope import (
    ToolErrorDetail,
    is_unified_envelope_enabled,
    tool_error,
    tool_success,
)
from pipefy_mcp.tools.graphql_error_helpers import (
    extract_error_strings,
)

logger = logging.getLogger(__name__)


class ValidateAiAutomationPromptPayload(TypedDict):
    success: Literal[True]
    valid: bool
    problems: list[str]
    warnings: list[str]
    field_map: dict[str, str]


# The ``Legacy*SuccessPayload`` TypedDicts below describe the flag=false shape
# only. Under the default ``PIPEFY_MCP_UNIFIED_ENVELOPE=true``, helpers return
# ``ToolSuccessPayload`` instead (see ADR-0001).


class LegacyCreateAiAutomationSuccessPayload(TypedDict):
    success: Literal[True]
    automation_id: str
    message: str


class LegacyUpdateAiAutomationSuccessPayload(TypedDict):
    success: Literal[True]
    automation_id: str
    message: str


class LegacyCreateAiAgentSuccessPayload(TypedDict):
    success: Literal[True]
    agent_uuid: str
    message: str


class LegacyUpdateAiAgentSuccessPayload(TypedDict):
    success: Literal[True]
    agent_uuid: str
    message: str


class LegacyToggleAiAgentStatusSuccessPayload(TypedDict):
    success: Literal[True]
    message: str


class LegacyGetAiAgentSuccessPayload(TypedDict):
    success: Literal[True]
    agent: AiAgentGraphPayload


class LegacyGetAiAgentsSuccessPayload(TypedDict):
    success: Literal[True]
    agents: list[AiAgentGraphPayload]


class LegacyDeleteAiAgentSuccessPayload(TypedDict):
    success: Literal[True]
    message: str


class AiToolErrorPayload(TypedDict):
    success: Literal[False]
    error: ToolErrorDetail


class CreateAgentPartialFailurePayload(TypedDict):
    success: Literal[False]
    agent_uuid: str
    error: ToolErrorDetail


def build_create_automation_success(
    *, automation_id: str, message: str
) -> dict[str, Any]:
    """Successful AI automation create.

    Args:
        automation_id: New automation id from the API.
        message: Short summary for the client.
    """
    if is_unified_envelope_enabled():
        return tool_success(data={"automation_id": automation_id}, message=message)
    return {"success": True, "automation_id": automation_id, "message": message}


def build_update_automation_success(
    *, automation_id: str, message: str
) -> dict[str, Any]:
    """Successful AI automation update.

    Args:
        automation_id: Target automation id.
        message: Short summary for the client.
    """
    if is_unified_envelope_enabled():
        return tool_success(data={"automation_id": automation_id}, message=message)
    return {"success": True, "automation_id": automation_id, "message": message}


def build_create_agent_success(*, agent_uuid: str, message: str) -> dict[str, Any]:
    """Successful AI agent create.

    Args:
        agent_uuid: New agent UUID from the API.
        message: Short summary for the client.
    """
    if is_unified_envelope_enabled():
        return tool_success(data={"agent_uuid": agent_uuid}, message=message)
    return {"success": True, "agent_uuid": agent_uuid, "message": message}


def build_update_agent_success(*, agent_uuid: str, message: str) -> dict[str, Any]:
    """Successful AI agent update.

    Args:
        agent_uuid: Target agent UUID.
        message: Short summary for the client.
    """
    if is_unified_envelope_enabled():
        return tool_success(data={"agent_uuid": agent_uuid}, message=message)
    return {"success": True, "agent_uuid": agent_uuid, "message": message}


def build_toggle_agent_status_success(*, message: str) -> dict[str, Any]:
    """Successful agent enable/disable.

    Args:
        message: Short summary for the client.
    """
    if is_unified_envelope_enabled():
        return tool_success(message=message)
    return {"success": True, "message": message}


def build_get_agent_success(agent: AiAgentGraphPayload) -> dict[str, Any]:
    """Single-agent read envelope.

    Args:
        agent: ``aiAgent`` subtree (may be empty dict when missing).
    """
    if is_unified_envelope_enabled():
        return tool_success(data={"agent": agent})
    return {"success": True, "agent": agent}


def build_get_agents_success(
    agents: list[AiAgentGraphPayload],
) -> dict[str, Any]:
    """List-agents read envelope.

    Args:
        agents: Unwrapped connection nodes for the repo.
    """
    if is_unified_envelope_enabled():
        return tool_success(data={"agents": agents})
    return {"success": True, "agents": agents}


def build_delete_agent_success(*, message: str) -> dict[str, Any]:
    """Successful AI agent delete.

    Args:
        message: Short summary for the client.
    """
    if is_unified_envelope_enabled():
        return tool_success(message=message)
    return {"success": True, "message": message}


def build_ai_tool_error(message: str) -> AiToolErrorPayload:
    """Generic AI-tool failure envelope.

    Does not alter ``message``; callers must pass user-safe text (sanitized when
    the source is the Internal API executor / GraphQL errors with diagnostic suffixes).

    Args:
        message: User-visible failure reason.
    """
    return cast(AiToolErrorPayload, tool_error(message))


def build_validate_prompt_payload(
    *,
    problems: list[str],
    warnings: list[str],
    field_map: dict[str, str],
) -> ValidateAiAutomationPromptPayload:
    """Build the response for ``validate_ai_automation_prompt``.

    Args:
        problems: Blocking issues found during validation.
        warnings: Non-blocking notices.
        field_map: Mapping of numeric field ID to field slug/label.
    """
    return {
        "success": True,
        "valid": len(problems) == 0,
        "problems": problems,
        "warnings": warnings,
        "field_map": field_map,
    }


def build_create_agent_partial_failure(
    *, agent_uuid: str, error: str
) -> CreateAgentPartialFailurePayload:
    """Create OK but follow-up update failed — surface UUID for recovery.

    Args:
        agent_uuid: Agent UUID from ``createAiAgent`` (retry update or delete).
        error: Why the chained update failed.
    """
    body: dict[str, Any] = tool_error(error)
    body["agent_uuid"] = agent_uuid
    return cast(CreateAgentPartialFailurePayload, body)


_BEHAVIOR_ERROR_EMPTY_AFTER_SANITIZE = (
    "The AI behavior request failed. Check behaviors and pipe context, then retry."
)

_ERROR_HINTS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"RECORD_NOT_SAVED", re.IGNORECASE),
        "Check that metadata is complete for each actionType "
        "(e.g. update_card needs pipeId + fieldsAttributes; "
        "move_card needs destinationPhaseId).",
    ),
    (
        re.compile(r"must contain at least 1 action", re.IGNORECASE),
        "Each behavior requires actionParams.aiBehaviorParams.actionsAttributes "
        "with at least one action entry.",
    ),
]


def _summarize_behaviors(behaviors: list[dict[str, Any]]) -> str:
    """Build a compact one-line-per-behavior summary for error context.

    Tolerates malformed entries (non-dict behaviors, actionParams as string, etc.)
    so it never raises when called from an error handler.

    Args:
        behaviors: Raw behavior dicts (pre-validation, may use either key style).
    """
    lines: list[str] = []
    for i, b in enumerate(behaviors):
        if not isinstance(b, dict):
            lines.append(f"  [{i}] <malformed: {type(b).__name__}>")
            continue

        name = "<unnamed>"
        event = "?"
        actions_desc: list[str] = []

        try:
            payload = BehaviorPayload.model_validate(b)
        except ValidationError:
            payload = None

        if payload is not None:
            name = payload.name or name
            event = payload.event_id or event
            abp = (
                payload.action_params.ai_behavior_params
                if payload.action_params
                else None
            )
            for a in (abp.actions_attributes if abp else None) or []:
                actions_desc.append(a.action_type or "?")
        else:
            # Typed parse failed (e.g. actionParams is a non-dict): fall back to
            # best-effort scalar reads so the summary still names the behavior.
            if isinstance(b.get("name"), str):
                name = b["name"]
            raw_event = b.get("eventId") or b.get("event_id")
            if raw_event:
                event = str(raw_event)

        actions_str = ", ".join(actions_desc) if actions_desc else "none"
        lines.append(f'  [{i}] "{name}" (event={event}, actions=[{actions_str}])')
    return "\n".join(lines)


def enrich_behavior_error(
    exc: BaseException,
    behaviors: list[dict[str, Any]],
) -> str:
    """Build an enriched error message with behavior context and actionable hints.

    Extracts the GraphQL messages, appends a behavior summary, and matches known
    error patterns to actionable advice.

    Args:
        exc: The exception from the service call.
        behaviors: The original behavior dicts sent by the caller (for context).
    """
    msgs = extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else str(exc)
    base = base.strip()
    if not base:
        base = _BEHAVIOR_ERROR_EMPTY_AFTER_SANITIZE

    hints: list[str] = []
    for pattern, hint in _ERROR_HINTS:
        if pattern.search(base):
            hints.append(hint)

    parts = [base]
    if behaviors:
        parts.append(
            f"Behaviors sent ({len(behaviors)}):\n{_summarize_behaviors(behaviors)}"
        )
    if hints:
        parts.append("Hints: " + " ".join(hints))
    return "\n".join(parts)


__all__ = [
    "AiToolErrorPayload",
    "CreateAgentPartialFailurePayload",
    "KNOWN_AI_ACTION_TYPES",
    "LegacyCreateAiAgentSuccessPayload",
    "LegacyCreateAiAutomationSuccessPayload",
    "LegacyDeleteAiAgentSuccessPayload",
    "LegacyGetAiAgentSuccessPayload",
    "LegacyGetAiAgentsSuccessPayload",
    "LegacyToggleAiAgentStatusSuccessPayload",
    "LegacyUpdateAiAgentSuccessPayload",
    "LegacyUpdateAiAutomationSuccessPayload",
    "ValidateAiAutomationPromptPayload",
    "build_ai_tool_error",
    "build_create_agent_partial_failure",
    "build_create_agent_success",
    "build_create_automation_success",
    "build_delete_agent_success",
    "build_field_slug_map",
    "build_get_agent_success",
    "build_get_agents_success",
    "build_toggle_agent_status_success",
    "build_update_agent_success",
    "build_update_automation_success",
    "build_validate_prompt_payload",
    "collect_pipe_ids_from_behaviors",
    "enrich_behavior_error",
    "fetch_pipe_validation_context",
    "pipe_ids_from_behavior",
    "resolve_and_populate_field_refs",
    "resolve_field_slugs_to_numeric",
    "validate_behaviors_against_pipe",
]
