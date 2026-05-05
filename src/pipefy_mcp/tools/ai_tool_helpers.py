"""Typed response payloads and builder functions for AI tools."""

from __future__ import annotations

import copy
import logging
import re
from typing import TYPE_CHECKING, Any, Literal, cast

from typing_extensions import TypedDict

from pipefy_mcp.services.pipefy.types import AiAgentGraphPayload
from pipefy_mcp.tools.graphql_error_helpers import (
    extract_error_strings,
    strip_internal_api_diagnostic_markers,
)
from pipefy_mcp.tools.tool_error_envelope import (
    ToolErrorDetail,
    is_unified_envelope_enabled,
    tool_error,
    tool_success,
)

if TYPE_CHECKING:
    from pipefy_mcp.services.pipefy import PipefyClient

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
    the source is ``InternalApiClient`` / GraphQL errors with diagnostic suffixes).

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


KNOWN_AI_ACTION_TYPES = frozenset(
    {
        "create_card",
        "create_connected_card",
        "create_table_record",
        "move_card",
        "send_email_template",
        "update_card",
    }
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

            if action_type == "move_card":
                dest = metadata.get("destinationPhaseId", "")
                if dest and str(dest) not in pipe_phase_ids:
                    problems.append(
                        f"{prefix}, action [{j}] (move_card): "
                        f'destinationPhaseId "{dest}" not found in pipe phases.'
                    )

            if action_type not in ("create_table_record", "send_email_template"):
                action_pipe = str(metadata.get("pipeId", ""))
                targets_source = not action_pipe or action_pipe == pipe_id
                if targets_source:
                    check_fields = pipe_field_ids
                elif (
                    cross_pipe_field_ids is not None
                    and action_pipe in cross_pipe_field_ids
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

            if action_type == "create_table_record":
                warnings.append(
                    f"{prefix}, action [{j}] (create_table_record): "
                    "fieldsAttributes reference table field IDs, which cannot be validated "
                    "against this pipe. Verify IDs with get_table or get_table_record."
                )

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


def _extract_slug_field_ids_by_pipe(
    behaviors: list[dict[str, Any]],
) -> dict[str, set[str]]:
    """Scan behaviors and collect non-numeric fieldIds grouped by their target pipeId.

    Args:
        behaviors: Raw behavior dicts (supports both camelCase and snake_case keys).

    Returns:
        Dict mapping pipeId → set of slug fieldIds found in that pipe's actions.
        Empty dict when no slugs are present.
    """
    slugs_by_pipe: dict[str, set[str]] = {}
    for b in behaviors:
        if not isinstance(b, dict):
            continue
        ap = b.get("actionParams") or b.get("action_params") or {}
        if not isinstance(ap, dict):
            continue
        abp = ap.get("aiBehaviorParams") or ap.get("ai_behavior_params") or {}
        if not isinstance(abp, dict):
            continue
        for a in abp.get("actionsAttributes") or abp.get("actions_attributes") or []:
            if not isinstance(a, dict):
                continue
            metadata = a.get("metadata") or {}
            pipe_id = str(metadata.get("pipeId", ""))
            if not pipe_id:
                continue
            for fa in metadata.get("fieldsAttributes") or []:
                if not isinstance(fa, dict):
                    continue
                fid = str(fa.get("fieldId", ""))
                if fid and not fid.isdigit():
                    slugs_by_pipe.setdefault(pipe_id, set()).add(fid)
    return slugs_by_pipe


_INSTRUCTION_FIELD_TOKEN_RE = re.compile(r"%\{field:([^}]+)\}")


def _instruction_has_non_numeric_field_tokens(instruction: str) -> bool:
    for m in _INSTRUCTION_FIELD_TOKEN_RE.finditer(instruction):
        if m.group(1) and not m.group(1).strip().isdigit():
            return True
    return False


def pipe_ids_from_behavior(behavior: dict[str, Any]) -> set[str]:
    """Extract target pipe IDs from a single behavior's action metadata.

    Args:
        behavior: Raw behavior dict (supports both camelCase and snake_case keys).

    Returns:
        Set of pipe ID strings found in ``metadata.pipeId`` across all actions.
    """
    pids: set[str] = set()
    ap = behavior.get("actionParams") or behavior.get("action_params") or {}
    if not isinstance(ap, dict):
        return pids
    abp = ap.get("aiBehaviorParams") or ap.get("ai_behavior_params") or {}
    if not isinstance(abp, dict):
        return pids
    for a in abp.get("actionsAttributes") or abp.get("actions_attributes") or []:
        if not isinstance(a, dict):
            continue
        pid = str((a.get("metadata") or {}).get("pipeId", ""))
        if pid:
            pids.add(pid)
    return pids


def collect_pipe_ids_from_behaviors(behaviors: list[dict[str, Any]]) -> list[str]:
    """Collect all unique pipe IDs referenced in behavior metadata.

    Args:
        behaviors: List of raw behavior dicts.

    Returns:
        Deduplicated list of pipe ID strings.
    """
    ids: set[str] = set()
    for b in behaviors:
        if isinstance(b, dict):
            ids.update(pipe_ids_from_behavior(b))
    return list(ids)


def _rewrite_instruction_field_tokens(
    instruction: str, slug_to_numeric: dict[str, str]
) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1).strip()
        if key.isdigit():
            return m.group(0)
        if key in slug_to_numeric:
            return f"%{{field:{slug_to_numeric[key]}}}"
        return m.group(0)

    return _INSTRUCTION_FIELD_TOKEN_RE.sub(repl, instruction)


async def build_field_slug_map(
    client: PipefyClient,
    pipe_id: str | int,
) -> dict[str, str]:
    """Build a slug → numeric internal_id map for all fields in a pipe.

    Fetches pipe info (for phase IDs and start form fields), then calls
    ``get_phase_fields`` per phase to collect ``internal_id`` values.

    Args:
        client: PipefyClient instance.
        pipe_id: Numeric pipe ID.

    Returns:
        Dict mapping field slug to its numeric ``internal_id`` string.
        Only includes entries where the slug is non-numeric.
    """
    slug_map: dict[str, str] = {}

    pipe_data = await client.get_pipe(pipe_id)
    pipe_info = pipe_data.get("pipe", {})

    for field in pipe_info.get("start_form_fields") or []:
        slug = str(field.get("id", ""))
        internal = str(field.get("internal_id", ""))
        if slug and internal and not slug.isdigit():
            slug_map[slug] = internal

    for phase in pipe_info.get("phases") or []:
        phase_id = phase.get("id")
        if not phase_id:
            continue
        try:
            phase_data = await client.get_phase_fields(phase_id)
            for field in phase_data.get("fields") or []:
                slug = str(field.get("id", ""))
                internal = str(field.get("internal_id", ""))
                if slug and internal and not slug.isdigit():
                    slug_map[slug] = internal
        except Exception:  # noqa: BLE001
            logger.debug("Failed to fetch fields for phase %s", phase_id, exc_info=True)
    return slug_map


async def resolve_field_slugs_to_numeric(
    client: PipefyClient,
    behaviors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve slug ``fieldId`` values and ``%{field:<slug>}`` tokens to numeric internal ids.

    Args:
        client: PipefyClient for fetching pipe field data.
        behaviors: Behavior dicts (same shape as ``create_ai_agent`` / ``update_ai_agent``).

    Returns:
        New list when any pipe fetch ran; otherwise the original list. Unresolved slugs unchanged.
    """
    slugs_by_pipe = _extract_slug_field_ids_by_pipe(behaviors)
    pipes_needed: set[str] = set(slugs_by_pipe.keys())

    for b in behaviors:
        if not isinstance(b, dict):
            continue
        ap = b.get("actionParams") or b.get("action_params") or {}
        if not isinstance(ap, dict):
            continue
        abp = ap.get("aiBehaviorParams") or ap.get("ai_behavior_params") or {}
        if not isinstance(abp, dict):
            continue
        instr = abp.get("instruction")
        if isinstance(instr, str) and _instruction_has_non_numeric_field_tokens(instr):
            pipes_needed.update(pipe_ids_from_behavior(b))

    if not pipes_needed:
        return behaviors

    slug_to_numeric: dict[str, str] = {}
    for pipe_id_str in pipes_needed:
        try:
            field_map = await build_field_slug_map(client, pipe_id_str)
            slug_to_numeric.update(field_map)
        except Exception:  # noqa: BLE001
            logger.debug(
                "Failed to fetch field map for pipe %s; slugs left as-is",
                pipe_id_str,
                exc_info=True,
            )

    if not slug_to_numeric:
        return behaviors

    resolved = copy.deepcopy(behaviors)
    for b in resolved:
        if not isinstance(b, dict):
            continue
        ap = b.get("actionParams") or b.get("action_params") or {}
        if not isinstance(ap, dict):
            continue
        abp = ap.get("aiBehaviorParams") or ap.get("ai_behavior_params") or {}
        if not isinstance(abp, dict):
            continue
        for a in abp.get("actionsAttributes") or abp.get("actions_attributes") or []:
            if not isinstance(a, dict):
                continue
            for fa in (a.get("metadata") or {}).get("fieldsAttributes") or []:
                if not isinstance(fa, dict):
                    continue
                fid = str(fa.get("fieldId", ""))
                if fid in slug_to_numeric:
                    fa["fieldId"] = slug_to_numeric[fid]

        instr = abp.get("instruction")
        if isinstance(instr, str):
            abp["instruction"] = _rewrite_instruction_field_tokens(
                instr, slug_to_numeric
            )

    return resolved


async def resolve_and_populate_field_refs(
    client: PipefyClient,
    behaviors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve slug fieldIds to numeric and populate ``referencedFieldIds``.

    Wraps :func:`resolve_field_slugs_to_numeric` and then runs
    :func:`populate_referenced_field_ids` on each behavior so the per-behavior
    ``referencedFieldIds`` list reflects the **post-resolution** instruction.

    Running populate after slug resolution is required for the mixed case where
    a single instruction contains both numeric (``%{field:159}``) and slug
    (``%{field:my_slug}``) refs: populating earlier would capture only the
    numeric subset and the conservative non-empty guard inside
    :func:`populate_referenced_field_ids` would then prevent a second pass from
    picking up the slug-resolved ids.

    Args:
        client: PipefyClient for fetching field-slug maps.
        behaviors: Behavior dicts (same shape as ``create_ai_agent``).

    Returns:
        Resolved-and-populated behavior dicts.
    """
    # Local import keeps the module-level dependency graph flat (the helpers
    # module doesn't otherwise need to know about the interpolation module).
    from pipefy_mcp.tools.behavior_placeholder_interpolation import (
        populate_referenced_field_ids,
    )

    resolved = await resolve_field_slugs_to_numeric(client, behaviors)
    for b in resolved:
        populate_referenced_field_ids(b)
    return resolved


async def fetch_pipe_validation_context(
    client: PipefyClient,
    pipe_id: str,
    *,
    timeout: float = 30,
) -> tuple[set[str], set[str], set[str] | None]:
    """Fetch pipe phases, fields, and relations for behavior validation.

    Exceptions from ``get_pipe`` propagate to the caller (e.g. TimeoutError,
    RuntimeError). Exceptions from ``get_pipe_relations`` are caught internally
    and result in ``related_pipe_ids=None``.

    Args:
        client: PipefyClient instance.
        pipe_id: Numeric pipe ID as string.
        timeout: Timeout in seconds for each API call.

    Returns:
        Tuple of (field_ids, phase_ids, related_pipe_ids).
        related_pipe_ids is None when relations could not be loaded.
    """
    import asyncio

    pipe_data = await asyncio.wait_for(
        client.get_pipe(pipe_id),
        timeout=timeout,
    )
    pipe_info = pipe_data.get("pipe", {})

    phase_ids: set[str] = set()
    field_ids: set[str] = set()
    for phase in pipe_info.get("phases") or []:
        phase_ids.add(str(phase.get("id", "")))
        for field in phase.get("fields") or []:
            fid = field.get("id") or field.get("internal_id")
            if fid:
                field_ids.add(str(fid))
    for field in pipe_info.get("start_form_fields") or []:
        fid = field.get("id") or field.get("internal_id")
        if fid:
            field_ids.add(str(fid))

    related_pipe_ids: set[str] | None
    try:
        relations = await asyncio.wait_for(
            client.get_pipe_relations(pipe_id),
            timeout=timeout,
        )
        related_pipe_ids = set()
        for rel in relations.get("children") or []:
            cid = rel.get("child", {}).get("id")
            if cid:
                related_pipe_ids.add(str(cid))
        for rel in relations.get("parents") or []:
            pid = rel.get("parent", {}).get("id")
            if pid:
                related_pipe_ids.add(str(pid))
    except Exception:  # noqa: BLE001
        related_pipe_ids = None

    return field_ids, phase_ids, related_pipe_ids


def enrich_behavior_error(
    exc: BaseException,
    behaviors: list[dict[str, Any]],
) -> str:
    """Build an enriched error message with behavior context and actionable hints.

    Extracts GraphQL messages, strips InternalApiClient-style ``[code=…]`` /
    ``[correlation_id=…]`` markers from the primary line, appends a behavior
    summary, and matches known error patterns to actionable advice.

    Args:
        exc: The exception from the service call.
        behaviors: The original behavior dicts sent by the caller (for context).
    """
    msgs = extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else str(exc)
    base = strip_internal_api_diagnostic_markers(base).strip()
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
