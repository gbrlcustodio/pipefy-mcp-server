"""MCP tools for Pipefy field condition create, update, and delete."""

from __future__ import annotations

import re
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.pipe_config_tool_helpers import (
    build_field_condition_delete_payload,
    build_field_condition_success_payload,
    build_pipe_tool_error_payload,
    handle_pipe_config_tool_graphql_error,
)
from pipefy_mcp.tools.pipe_config_validators import valid_phase_field_id

# Keys reserved so callers cannot override structured args via extra_input. Entries like
# ``condition_expression`` / ``phase_field_id`` catch alternate spellings the API does not use
# on ``createFieldConditionInput`` (see schema introspection); keeping them avoids silent drops.
_CREATE_FIELD_CONDITION_EXTRA_RESERVED = frozenset(
    {
        "phaseId",
        "phase_id",
        "condition",
        "actions",
        "phase_field_id",
        "condition_expression",
    }
)
_UPDATE_FIELD_CONDITION_EXTRA_RESERVED = frozenset({"id"})

_FIELD_CONDITION_PHASE_FIELD_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def field_condition_phase_field_id_looks_like_slug(value: object) -> bool:
    """True when ``value`` is probably a phase field slug (``id``) instead of ``internal_id``."""
    if isinstance(value, int):
        return False
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    if _FIELD_CONDITION_PHASE_FIELD_UUID_RE.fullmatch(s):
        return False
    if s.isdigit():
        return False
    return any(c.isalpha() for c in s)


def _normalize_field_condition_actions(
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Shallow-copy each action and map legacy ``hidden`` → ``hide``."""
    normalized: list[dict[str, Any]] = []
    for item in actions:
        row = dict(item)
        aid = row.get("actionId")
        if isinstance(aid, str) and aid.strip().lower() == "hidden":
            row["actionId"] = "hide"
        normalized.append(row)
    return normalized


def _strip_expression_ids_for_create(condition: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``condition`` with ``id`` removed and nested ints coerced.

    Output keys mirror the input ``condition`` (typically ``expressions``,
    ``expressions_structure``, plus any other ``ConditionInput`` fields present).

    ``ConditionExpressionInput.id`` is a persisted primary key — sending arbitrary
    client tokens on create causes ``RECORD_NOT_FOUND``. ``structure_id`` is coerced
    to ``int`` for consistency (GraphQL ``ID`` scalar).
    """
    expressions = condition.get("expressions")

    def _coerce_int(value: Any) -> Any:
        try:
            return int(value)
        except (ValueError, TypeError):
            return value

    if not isinstance(expressions, list):
        return condition
    cleaned: list[dict[str, Any]] = []
    for expr in expressions:
        row = {k: v for k, v in expr.items() if k != "id"}
        sid = row.get("structure_id")
        if sid is not None:
            try:
                row["structure_id"] = int(sid)
            except (ValueError, TypeError):
                pass
        cleaned.append(row)
    es = condition.get("expressions_structure")
    if isinstance(es, list):
        coerced_ints: list[list[Any]] = []
        for group in es:
            if isinstance(group, list):
                coerced_ints.append([_coerce_int(v) for v in group])
            else:
                coerced_ints.append([_coerce_int(group)])
        return {
            **condition,
            "expressions": cleaned,
            "expressions_structure": coerced_ints,
        }
    return {**condition, "expressions": cleaned}


def _field_condition_actions_error_message(
    actions: list[dict[str, Any]],
) -> str | None:
    if not isinstance(actions, list) or not actions:
        return "Invalid 'actions': provide a non-empty list of action objects."
    if not all(isinstance(item, dict) for item in actions):
        return "Invalid 'actions': each item must be an object/dict."
    for index, item in enumerate(actions):
        raw_id = item.get("phaseFieldId")
        if raw_id is None:
            continue
        if field_condition_phase_field_id_looks_like_slug(raw_id):
            return (
                f"Invalid actions[{index}] 'phaseFieldId': value looks like a field "
                "slug (the `id` from get_phase_fields), but Pipefy expects "
                "`internal_id` from get_phase_fields for field-condition actions. "
                "See README (Field condition tools)."
            )
    return None


class FieldConditionTools:
    """Declares MCP tools for field condition CRUD."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
        )
        async def create_field_condition(
            phase_id: str | int,
            condition: dict[str, Any],
            actions: list[dict[str, Any]],
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a conditional field rule (Pipefy ``createFieldCondition``).

            Args:
                phase_id: Phase ID that owns the condition (``phaseId`` on the API input).
                condition: ``ConditionInput`` dict (e.g. ``expressions``, ``expressions_structure``).
                actions: List of ``FieldConditionActionInput`` dicts; use ``phaseFieldId`` (often the
                    field's ``internal_id`` from ``get_phase_fields``). Each action must include
                    ``actionId`` (``hide`` or ``show``); legacy ``hidden`` is mapped to ``hide``.
                extra_input: Optional extra keys for ``createFieldConditionInput`` (e.g. ``name``, ``index``).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_phase_field_id(phase_id):
                return build_pipe_tool_error_payload(
                    message="Invalid 'phase_id'. Use a non-empty string or a positive integer.",
                )
            if not isinstance(condition, dict):
                return build_pipe_tool_error_payload(
                    message="Invalid 'condition': provide an object/dict.",
                )
            if not condition:
                return build_pipe_tool_error_payload(
                    message="Invalid 'condition': provide a non-empty object (e.g. expressions).",
                )
            expressions = condition.get("expressions")
            if isinstance(expressions, list) and len(expressions) == 0:
                return build_pipe_tool_error_payload(
                    message=(
                        "Invalid 'condition': 'expressions' must not be empty; "
                        "provide at least one expression."
                    ),
                )
            if extra_input is not None and not isinstance(extra_input, dict):
                return build_pipe_tool_error_payload(
                    message="Invalid 'extra_input': provide an object/dict or omit.",
                )
            act_err = _field_condition_actions_error_message(actions)
            if act_err:
                return build_pipe_tool_error_payload(message=act_err)
            merged: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _CREATE_FIELD_CONDITION_EXTRA_RESERVED
            }
            condition_for_api = _strip_expression_ids_for_create(condition)
            actions_for_api = _normalize_field_condition_actions(actions)
            try:
                raw = await client.create_field_condition(
                    phase_id,
                    condition_for_api,
                    actions_for_api,
                    **merged,
                )
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Create field condition failed.", debug=debug
                )
            fc = raw.get("createFieldCondition", {}).get("fieldCondition") or {}
            cid = fc.get("id")
            if cid is None or cid == "":
                return build_pipe_tool_error_payload(
                    message=(
                        "Create field condition succeeded but no condition id was returned."
                    ),
                )
            return build_field_condition_success_payload(str(cid), "created")

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
        )
        async def update_field_condition(
            condition_id: str | int,
            condition: dict[str, Any] | None = None,
            actions: list[dict[str, Any]] | None = None,
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update an existing field condition.

            Prefer the explicit ``condition`` and ``actions`` parameters (same shapes as
            ``create_field_condition``) when changing rule logic. ``extra_input`` still
            carries other ``UpdateFieldConditionInput`` keys (e.g. ``name``, ``index``).

            Args:
                condition_id: Field condition ID to update.
                condition: Optional ``ConditionInput`` dict (same as create).
                actions: Optional list of ``FieldConditionActionInput`` dicts (same as create).
                extra_input: Additional fields to merge into ``UpdateFieldConditionInput``.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_phase_field_id(condition_id):
                return build_pipe_tool_error_payload(
                    message=(
                        "Invalid 'condition_id'. Use a non-empty string or a positive integer."
                    ),
                )
            if extra_input is not None and not isinstance(extra_input, dict):
                return build_pipe_tool_error_payload(
                    message="Invalid 'extra_input': provide an object/dict or omit.",
                )
            if condition is not None and not isinstance(condition, dict):
                return build_pipe_tool_error_payload(
                    message="Invalid 'condition': provide an object/dict or omit.",
                )
            if condition is not None:
                expressions = condition.get("expressions")
                if isinstance(expressions, list) and len(expressions) == 0:
                    return build_pipe_tool_error_payload(
                        message=(
                            "Invalid 'condition': 'expressions' must not be empty; "
                            "provide at least one expression."
                        ),
                    )
            if actions is not None:
                act_err = _field_condition_actions_error_message(actions)
                if act_err:
                    return build_pipe_tool_error_payload(message=act_err)

            update_attrs: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _UPDATE_FIELD_CONDITION_EXTRA_RESERVED
            }
            if condition is not None:
                update_attrs["condition"] = _strip_expression_ids_for_create(condition)
            if actions is not None:
                update_attrs["actions"] = _normalize_field_condition_actions(actions)
            if not update_attrs:
                return build_pipe_tool_error_payload(
                    message=(
                        "Provide at least one of: 'condition', 'actions', or a non-empty "
                        "'extra_input' to update."
                    ),
                )
            cid_key = (
                condition_id.strip()
                if isinstance(condition_id, str)
                else str(condition_id)
            )
            try:
                raw = await client.update_field_condition(cid_key, **update_attrs)
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Update field condition failed.", debug=debug
                )
            fc = raw.get("updateFieldCondition", {}).get("fieldCondition") or {}
            out_id = fc.get("id")
            if out_id is None or out_id == "":
                return build_pipe_tool_error_payload(
                    message=(
                        "Update field condition succeeded but no condition id was returned."
                    ),
                )
            return build_field_condition_success_payload(str(out_id), "updated")

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_field_condition(
            condition_id: str | int,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a field condition permanently.

            This action is irreversible. Always confirm with the user before executing.

            Args:
                condition_id: Field condition ID to delete.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_phase_field_id(condition_id):
                return build_pipe_tool_error_payload(
                    message=(
                        "Invalid 'condition_id'. Use a non-empty string or a positive integer."
                    ),
                )
            cid_key = (
                condition_id.strip()
                if isinstance(condition_id, str)
                else str(condition_id)
            )
            try:
                raw = await client.delete_field_condition(cid_key)
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Delete field condition failed.", debug=debug
                )
            ok = bool(raw.get("success"))
            return build_field_condition_delete_payload(ok)
