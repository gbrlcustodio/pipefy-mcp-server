"""Typed response payloads and builder functions for AI tools."""

from __future__ import annotations

import re
from typing import Any, Literal

from typing_extensions import TypedDict

from pipefy_mcp.services.pipefy.types import AiAgentGraphPayload
from pipefy_mcp.tools.graphql_error_helpers import extract_error_strings


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


# --- Error enrichment for behavior-level failures ---

# Patterns the Pipefy API returns that map to actionable advice.
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
        name = b.get("name", "<unnamed>")
        event = b.get("eventId") or b.get("event_id") or "?"
        actions_desc: list[str] = []

        ap = b.get("actionParams") or b.get("action_params")
        if isinstance(ap, dict):
            abp = ap.get("aiBehaviorParams") or ap.get("ai_behavior_params")
            if isinstance(abp, dict):
                attrs = (
                    abp.get("actionsAttributes") or abp.get("actions_attributes") or []
                )
                for a in attrs:
                    if isinstance(a, dict):
                        actions_desc.append(a.get("actionType", "?"))

        actions_str = ", ".join(actions_desc) if actions_desc else "none"
        lines.append(f'  [{i}] "{name}" (event={event}, actions=[{actions_str}])')
    return "\n".join(lines)


# --- Behavior validation against pipe context ---

# actionTypes that the Pipefy AI behavior system recognizes.
KNOWN_AI_ACTION_TYPES = frozenset(
    {"move_card", "update_card", "create_card", "create_connected_card"}
)


def validate_behaviors_against_pipe(
    behaviors: list[dict[str, Any]],
    *,
    pipe_id: str = "",
    pipe_field_ids: set[str],
    pipe_phase_ids: set[str],
    related_pipe_ids: set[str] | None,
    cross_pipe_field_ids: dict[str, set[str]] | None = None,
    unknown_action_types: Literal["error", "warning", "ignore"] = "error",
) -> tuple[list[str], list[str]]:
    """Check behaviors against resolved pipe context and return problems and warnings.

    Pure function — no API calls. The caller is responsible for fetching
    pipe fields, phases, and relations beforehand.

    Args:
        behaviors: Raw behavior dicts (pre-validation format).
        pipe_id: Source pipe ID (used to decide whether fieldId checks apply).
        pipe_field_ids: Set of valid field internal IDs for the source pipe.
        pipe_phase_ids: Set of valid phase IDs (as strings) for the source pipe.
        related_pipe_ids: Pipe IDs related to the source pipe for
            ``create_connected_card`` validation; ``None`` skips that check
            (avoids false positives when relations were not loaded). A set
            (possibly empty) runs the relation check as before.
        cross_pipe_field_ids: Optional mapping of ``{pipe_id: field_ids}`` for
            target pipes referenced by cross-pipe actions. When provided,
            fieldIds targeting those pipes are validated against the map.
            When ``None`` (default), cross-pipe fieldIds are skipped.
        unknown_action_types: How to treat non-empty ``actionType`` values not in
            ``KNOWN_AI_ACTION_TYPES``: ``error`` adds to problems, ``warning``
            adds the same message to warnings, ``ignore`` skips.

    Returns:
        Tuple ``(problems, warnings)`` of human-readable strings. Empty lists
        mean no issues at that severity.
    """
    problems: list[str] = []
    warnings: list[str] = []

    for i, b in enumerate(behaviors):
        name = b.get("name", f"<behavior {i}>")
        prefix = f'Behavior [{i}] "{name}"'

        ap = b.get("actionParams") or b.get("action_params") or {}
        abp = ap.get("aiBehaviorParams") or ap.get("ai_behavior_params") or {}
        attrs = abp.get("actionsAttributes") or abp.get("actions_attributes") or []

        # Check eventParams phase references
        ep = b.get("eventParams") or b.get("event_params") or {}
        to_phase = ep.get("to_phase_id") or ep.get("toPhaseId")
        if to_phase and str(to_phase) not in pipe_phase_ids:
            problems.append(
                f'{prefix}: eventParams.to_phase_id / toPhaseId "{to_phase}" '
                f"not found in pipe phases."
            )

        for j, action in enumerate(attrs):
            if not isinstance(action, dict):
                continue
            action_type = action.get("actionType", "")
            metadata = action.get("metadata") or {}

            if action_type and action_type not in KNOWN_AI_ACTION_TYPES:
                msg = (
                    f"{prefix}, action [{j}]: unknown actionType "
                    f'"{action_type}". Known types: {sorted(KNOWN_AI_ACTION_TYPES)}.'
                )
                if unknown_action_types == "error":
                    problems.append(msg)
                elif unknown_action_types == "warning":
                    warnings.append(msg)

            # Check destinationPhaseId for move_card
            if action_type == "move_card":
                dest = metadata.get("destinationPhaseId", "")
                if dest and str(dest) not in pipe_phase_ids:
                    problems.append(
                        f"{prefix}, action [{j}] (move_card): "
                        f'destinationPhaseId "{dest}" not found in pipe phases.'
                    )

            # Check fieldsAttributes fieldId references.
            # Same-pipe actions check against pipe_field_ids; cross-pipe actions
            # check against cross_pipe_field_ids when available.
            action_pipe = str(metadata.get("pipeId", ""))
            targets_source = not action_pipe or action_pipe == pipe_id
            if targets_source:
                check_fields = pipe_field_ids
            elif (
                cross_pipe_field_ids is not None and action_pipe in cross_pipe_field_ids
            ):
                check_fields = cross_pipe_field_ids[action_pipe]
            else:
                check_fields = None

            if check_fields is not None:
                fields_attrs = metadata.get("fieldsAttributes") or []
                for k, fa in enumerate(fields_attrs):
                    if not isinstance(fa, dict):
                        continue
                    fid = fa.get("fieldId", "")
                    if fid and check_fields and fid not in check_fields:
                        pipe_label = (
                            "pipe fields"
                            if targets_source
                            else f"target pipe {action_pipe} fields"
                        )
                        problems.append(
                            f"{prefix}, action [{j}] ({action_type}): "
                            f'fieldsAttributes[{k}].fieldId "{fid}" '
                            f"not found in {pipe_label}."
                        )

            # Check create_connected_card relation (skipped when related_pipe_ids is None)
            if action_type == "create_connected_card" and related_pipe_ids is not None:
                target_pipe = metadata.get("pipeId", "")
                if target_pipe and str(target_pipe) not in related_pipe_ids:
                    problems.append(
                        f"{prefix}, action [{j}] (create_connected_card): "
                        f'pipeId "{target_pipe}" has no relation with the '
                        f"source pipe. Create a pipe relation first "
                        f"(get_pipe_relations / create_pipe_relation)."
                    )

    return problems, warnings


def enrich_behavior_error(
    exc: BaseException,
    behaviors: list[dict[str, Any]],
) -> str:
    """Build an enriched error message with behavior context and actionable hints.

    Extracts raw GraphQL messages, appends a behavior summary, and matches
    known error patterns to actionable advice.

    Args:
        exc: The exception from the service call.
        behaviors: The original behavior dicts sent by the caller (for context).
    """
    msgs = extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else str(exc)

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
