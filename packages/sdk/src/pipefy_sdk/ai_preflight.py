"""Read-only AI validation helpers for CLI and programmatic pre-flight checks."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from pydantic import ValidationError

from pipefy_sdk.ai_phase_transition_validation import (
    collect_ai_behavior_move_transition_problems,
)
from pipefy_sdk.ai_pipe_validation import (
    collect_field_ids_for_pipe,
    fetch_pipe_validation_context,
    phase_field_fetch_warning,
    pipe_ids_from_behavior,
    validate_behaviors_against_pipe,
)
from pipefy_sdk.behavior_placeholders import expand_behaviors_placeholders
from pipefy_sdk.client import PipefyClient
from pipefy_sdk.models import BehaviorInput

logger = logging.getLogger(__name__)

_PROMPT_FIELD_TOKEN_RE = re.compile(r"%\{(\d+)\}")

GENERATE_WITH_AI_ACTION_ID = "generate_with_ai"

VALIDATE_FETCH_TIMEOUT_SECONDS = 30.0
MAX_CROSS_PIPE_FIELD_FETCH = 100


def _is_ai_automation_summary_row(row: Any) -> bool:
    """True when the listing row is an AI (prompt) automation."""
    if not isinstance(row, dict):
        return False
    action_id = row.get("action_id") or row.get("actionId")
    if action_id == GENERATE_WITH_AI_ACTION_ID:
        return True
    ap = row.get("action_params") or row.get("actionParams")
    if isinstance(ap, dict) and (
        ap.get("aiParams") is not None or ap.get("ai_params") is not None
    ):
        return True
    return False


def filter_ai_automation_summaries(rows: list[Any]) -> list[Any]:
    """Keep only rows that represent ``generate_with_ai`` automations."""
    return [r for r in rows if _is_ai_automation_summary_row(r)]


def _validate_prompt_payload(
    *,
    problems: list[str],
    warnings: list[str],
    field_map: dict[str, str],
) -> dict[str, Any]:
    return {
        "success": True,
        "valid": len(problems) == 0,
        "problems": problems,
        "warnings": warnings,
        "field_map": field_map,
    }


async def validate_ai_automation_prompt_sdk(
    client: PipefyClient,
    pipe_id: str,
    prompt: str,
    field_ids: list[str],
    event_id: str | None = None,
) -> dict[str, Any]:
    """Mirror MCP ``validate_ai_automation_prompt`` checks (read-only, no mutations).

    Args:
        client: Authenticated Pipefy client.
        pipe_id: Pipe where the AI automation will run.
        prompt: Prompt text with ``%{internal_id}`` field references.
        field_ids: Output field internal IDs.
        event_id: Optional trigger id to validate against ``get_automation_events``.
    """
    problems: list[str] = []
    warnings: list[str] = []
    field_map: dict[str, str] = {}

    prompt_tokens = _PROMPT_FIELD_TOKEN_RE.findall(prompt)
    input_output_overlap = set(prompt_tokens) & {str(f) for f in field_ids}
    for oid in sorted(input_output_overlap):
        problems.append(
            f"Field %{{{oid}}} is used both as a prompt input and as an output field in "
            "`field_ids`. Pick a different output field; the API rejects the overlap with "
            "'The same parameter cannot be present in both input and output'."
        )
    if not prompt_tokens:
        problems.append(
            "Prompt must reference at least one pipe field using "
            "%{internal_id} syntax (e.g. 'Summarize: %{900000101}' — use your "
            "field's internal_id; the number is illustrative)."
        )

    try:
        pipe_data = await client.get_pipe_with_preferences(pipe_id)
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "valid": False,
            "error": f"Failed to fetch pipe {pipe_id}: {exc}",
        }

    pipe_info = pipe_data.get("pipe") or {}

    all_field_ids: set[str] = set()
    readonly_field_ids: set[str] = set()
    for phase in pipe_info.get("phases") or []:
        for field in phase.get("fields") or []:
            fid = str(field.get("internal_id") or field.get("id", ""))
            label = field.get("label", "")
            if fid:
                all_field_ids.add(fid)
                field_map[fid] = label
            if fid and field.get("editable") is False:
                readonly_field_ids.add(fid)
    for field in pipe_info.get("start_form_fields") or []:
        fid = str(field.get("internal_id") or field.get("id", ""))
        label = field.get("label", "")
        if fid:
            all_field_ids.add(fid)
            field_map[fid] = label
        if fid and field.get("editable") is False:
            readonly_field_ids.add(fid)

    for token_id in prompt_tokens:
        if token_id not in all_field_ids:
            problems.append(
                f"Prompt references field %{{{token_id}}} but it does not "
                f"exist in pipe {pipe_id}."
            )

    for fid in field_ids:
        if str(fid) not in all_field_ids:
            problems.append(
                f"Output field_id '{fid}' does not exist in pipe {pipe_id}."
            )

    if event_id is not None and str(event_id).strip():
        eid = str(event_id).strip()
        try:
            events = await client.get_automation_events(pipe_id)
            valid_event_ids = {
                str(e.get("id", "")) for e in events if isinstance(e, dict)
            }
            if eid not in valid_event_ids:
                problems.append(
                    f"event_id '{eid}' is not a valid automation event "
                    f"for pipe {pipe_id}. Valid events: "
                    f"{sorted(valid_event_ids)}."
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not fetch automation events: %s", exc)
            warnings.append(
                "Could not verify event_id: automation events "
                "endpoint returned an error."
            )

    preferences = pipe_info.get("preferences") or {}
    ai_enabled = preferences.get("aiAgentsEnabled")
    if ai_enabled is False:
        problems.append(
            "AI is not enabled for this pipe. Enable it in "
            "Pipefy UI > Pipe Settings > AI."
        )

    org_id = pipe_info.get("organizationId")
    if org_id:
        try:
            usage_data = await client.get_ai_credit_usage(str(org_id), "current_month")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not check AI credit usage: %s", exc)
        else:
            stats = (usage_data or {}).get("aiCreditUsageStats") or {}
            active = stats.get("active")
            usage = stats.get("usage") or 0
            limit = stats.get("limit") or 0
            has_addon = bool(stats.get("hasAddon"))
            ai_auto = stats.get("aiAutomation") or {}
            ai_auto_enabled = ai_auto.get("enabled")
            if active is False or ai_auto_enabled is False:
                problems.append(
                    "AI Automations are disabled on this organization. "
                    "Created rules will not execute. Contact your "
                    "Pipefy admin to enable AI Automations for the org."
                )
            elif limit > 0 and usage >= limit and not has_addon:
                warnings.append(
                    f"AI credit budget exhausted ({usage}/{limit}). "
                    "Rules will be created but may not execute until "
                    "credits reset or an addon is enabled."
                )

    referenced_ids = set(prompt_tokens) | set(str(f) for f in field_ids)
    for fid in referenced_ids & readonly_field_ids:
        warnings.append(f"Field {fid} ({field_map.get(fid, '')}) is read-only.")
    filtered_map = {k: v for k, v in field_map.items() if k in referenced_ids}

    return _validate_prompt_payload(
        problems=problems,
        warnings=warnings,
        field_map=filtered_map,
    )


def _behavior_input_validation_problems(exc: ValidationError) -> list[str]:
    """Turn ``BehaviorInput`` validation errors into short, actionable strings."""

    def _targets_name_field(err: dict[str, Any]) -> bool:
        loc = err.get("loc") or ()
        return bool(loc) and loc[-1] == "name"

    raw_errors = exc.errors()
    problems: list[str] = []

    if any(_targets_name_field(e) for e in raw_errors):
        problems.append(
            "Each behavior must include `name` (non-blank display name). "
            "Match create_ai_agent: `event_id` or `eventId`, plus `actionParams` with "
            "`aiBehaviorParams.instruction` and at least one entry in `actionsAttributes`."
        )

    for e in raw_errors:
        if _targets_name_field(e):
            continue
        loc = e.get("loc") or ()
        path = " -> ".join(str(p) for p in loc) if loc else "behavior"
        problems.append(f"{path}: {e.get('msg', 'validation error')}")

    return problems if problems else [str(exc)]


def _behavior_data_source_ids(behavior: dict[str, Any]) -> list[str]:
    """Extract ``actionParams.aiBehaviorParams.dataSourceIds`` from a behavior dict.

    Accepts both camelCase and snake_case keys (behaviors arrive in either shape).
    """
    action_params = behavior.get("actionParams") or behavior.get("action_params")
    if not isinstance(action_params, dict):
        return []
    ai_params = action_params.get("aiBehaviorParams") or action_params.get(
        "ai_behavior_params"
    )
    if not isinstance(ai_params, dict):
        return []
    ids = ai_params.get("dataSourceIds") or ai_params.get("data_source_ids")
    if not isinstance(ids, list):
        return []
    return [stripped for i in ids if (stripped := str(i).strip())]


def _collect_configured_data_source_ids(
    behaviors: list[dict[str, Any]],
    agent_data_source_ids: list[str] | None,
) -> set[str]:
    """Union of agent-level and behavior-level configured data source ids."""
    configured = {
        stripped
        for did in agent_data_source_ids or []
        if (stripped := str(did).strip())
    }
    for behavior in behaviors:
        configured.update(_behavior_data_source_ids(behavior))
    return configured


async def _data_source_membership_warnings(
    client: PipefyClient,
    pipe_id: str,
    configured_ids: set[str],
) -> list[str]:
    """Warn (never block) for configured data source ids not on the pipe.

    The knowledge base list is pipe-UUID-scoped, so this resolves the pipe UUID
    first. A failed list probe (permission, feature, transport) yields a single
    warning and skips every per-id membership claim, so an inability to read the
    knowledge base is never reported as a broken reference.
    """
    try:
        pipe_data = await client.get_pipe(pipe_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("data-source membership: pipe fetch failed: %s", exc)
        return [
            f"Could not verify data source membership: failed to load pipe {pipe_id}."
        ]
    pipe_uuid = (pipe_data.get("pipe") or {}).get("uuid")
    if not pipe_uuid:
        return [
            "Could not verify data source membership: pipe "
            f"{pipe_id} has no uuid in the response."
        ]
    try:
        knowledge_bases = await client.get_ai_knowledge_bases(str(pipe_uuid))
    except Exception as exc:  # noqa: BLE001
        logger.debug("data-source membership: kb list failed: %s", exc)
        return [
            "Could not verify data source membership: knowledge base list "
            f"probe failed ({exc})."
        ]
    known_ids = {
        str(kb.get("id"))
        for kb in knowledge_bases
        if isinstance(kb, dict) and kb.get("id")
    }
    missing = sorted(cid for cid in configured_ids if cid not in known_ids)
    return [
        f"data_source id '{cid}' is not a knowledge base of pipe {pipe_id}; "
        "attaching it may fail. Verify with get_ai_knowledge_bases."
        for cid in missing
    ]


async def validate_ai_agent_behaviors_sdk(
    client: PipefyClient,
    pipe_id: str,
    behaviors: list[dict[str, Any]],
    *,
    strict_unknown_action_types: bool = True,
    data_source_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Mirror MCP ``validate_ai_agent_behaviors`` (read-only).

    Args:
        client: Authenticated Pipefy client.
        pipe_id: Numeric pipe id for field/phase/relation context.
        behaviors: Raw behavior dicts (1-5).
        strict_unknown_action_types: When False, unknown action types become warnings only.
        data_source_ids: Optional agent-level knowledge base ids. These are unioned
            with each behavior's ``actionParams.aiBehaviorParams.dataSourceIds`` and
            checked against the pipe's knowledge bases; unknown ids yield warnings
            only (``valid`` stays true). A failed list probe skips the membership
            check with a single warning.
    """
    pid = str(pipe_id).strip()
    if not pid:
        return {
            "success": False,
            "valid": False,
            "problems": ["pipe_id must not be blank"],
            "warnings": [],
            "message": "Invalid pipe_id.",
        }

    try:
        behaviors_expanded = expand_behaviors_placeholders(behaviors)
    except ValueError as exc:
        return {
            "success": True,
            "valid": False,
            "problems": [str(exc)],
            "warnings": [],
            "message": "Behavior placeholder expansion failed.",
        }

    try:
        for b in behaviors_expanded:
            BehaviorInput.model_validate(b)
    except ValidationError as exc:
        return {
            "success": True,
            "valid": False,
            "problems": _behavior_input_validation_problems(exc),
            "warnings": [],
            "message": "Behavior dicts failed structural validation (BehaviorInput).",
        }

    behaviors = behaviors_expanded

    try:
        (
            field_ids,
            phase_ids,
            related_pipe_ids,
            context_fetch_warnings,
        ) = await fetch_pipe_validation_context(
            client, pid, timeout=VALIDATE_FETCH_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        return {
            "success": False,
            "valid": False,
            "problems": [
                f"Timed out fetching pipe {pid} after {VALIDATE_FETCH_TIMEOUT_SECONDS}s"
            ],
            "warnings": [],
            "message": "Pipe fetch timed out.",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "valid": False,
            "problems": [f"Failed to fetch pipe {pid}: {exc}"],
            "warnings": [],
            "message": "Pipe fetch failed.",
        }

    tool_warnings: list[str] = list(context_fetch_warnings)
    if related_pipe_ids is None:
        tool_warnings.append(
            "Could not load pipe relations; create_connected_card pipeId targets "
            "were not verified against relations."
        )

    cross_pipe_field_ids: dict[str, set[str]] = {}
    target_pipe_ids: set[str] = set()
    if related_pipe_ids is not None:
        for b in behaviors:
            for meta_pipe in pipe_ids_from_behavior(b):
                if meta_pipe != pid:
                    target_pipe_ids.add(meta_pipe)

    target_pipe_list = sorted(target_pipe_ids)
    if len(target_pipe_list) > MAX_CROSS_PIPE_FIELD_FETCH:
        return {
            "success": False,
            "valid": False,
            "problems": [
                f"Too many distinct cross-pipe target pipes ({len(target_pipe_list)}). "
                f"Maximum is {MAX_CROSS_PIPE_FIELD_FETCH}."
            ],
            "warnings": [],
            "message": "Too many cross-pipe targets.",
        }
    if target_pipe_list:
        fetch_results = await asyncio.gather(
            *(
                asyncio.wait_for(
                    client.get_pipe(tpid),
                    timeout=VALIDATE_FETCH_TIMEOUT_SECONDS,
                )
                for tpid in target_pipe_list
            ),
            return_exceptions=True,
        )
        targets_loaded: list[tuple[str, dict[str, Any]]] = []
        for tpid, result in zip(target_pipe_list, fetch_results, strict=True):
            if isinstance(result, BaseException):
                tool_warnings.append(
                    f"Could not load fields for target pipe {tpid}; "
                    f"fieldIds targeting it were not verified."
                )
                continue
            targets_loaded.append((tpid, (result.get("pipe") or {})))

        if targets_loaded:
            collect_results = await asyncio.gather(
                *(
                    collect_field_ids_for_pipe(
                        client,
                        target_info,
                        timeout=VALIDATE_FETCH_TIMEOUT_SECONDS,
                    )
                    for _tpid, target_info in targets_loaded
                )
            )
            for (tpid, _), (target_field_ids, failed_phases) in zip(
                targets_loaded, collect_results, strict=True
            ):
                cross_pipe_field_ids[tpid] = target_field_ids
                if failed_phases:
                    tool_warnings.append(
                        phase_field_fetch_warning(failed_phases, pipe_id=tpid)
                    )

    unknown_action_types = "error" if strict_unknown_action_types else "warning"
    problems, helper_warnings = validate_behaviors_against_pipe(
        behaviors,
        pipe_id=pid,
        pipe_field_ids=field_ids,
        pipe_phase_ids=phase_ids,
        related_pipe_ids=related_pipe_ids,
        cross_pipe_field_ids=cross_pipe_field_ids or None,
        unknown_action_types=unknown_action_types,
    )
    transition_problems = await collect_ai_behavior_move_transition_problems(
        client, behaviors
    )
    problems = [*problems, *transition_problems]
    warnings = [*tool_warnings, *helper_warnings]

    configured_data_source_ids = _collect_configured_data_source_ids(
        behaviors, data_source_ids
    )
    if configured_data_source_ids:
        warnings = [
            *warnings,
            *await _data_source_membership_warnings(
                client, pid, configured_data_source_ids
            ),
        ]

    if problems:
        msg = f"Found {len(problems)} problem(s) in behaviors."
    elif warnings:
        msg = f"Validation passed with {len(warnings)} warning(s)."
    else:
        msg = "All behaviors passed validation."

    return {
        "success": True,
        "valid": len(problems) == 0,
        "problems": problems,
        "warnings": warnings,
        "message": msg,
    }


__all__ = [
    "filter_ai_automation_summaries",
    "validate_ai_agent_behaviors_sdk",
    "validate_ai_automation_prompt_sdk",
]
