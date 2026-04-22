"""MCP tools for Pipefy field condition read, create, update, and delete."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from pipefy_mcp.models.validators import PipefyId
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.pipe_config_tool_helpers import (
    build_field_condition_delete_payload,
    build_field_condition_success_payload,
    build_pipe_tool_error_payload,
    field_condition_actions_error_message,
    handle_pipe_config_tool_graphql_error,
    normalize_field_condition_actions,
    strip_expression_ids_for_create,
)
from pipefy_mcp.tools.validation_helpers import (
    validate_tool_id,
)

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


class FieldConditionTools:
    """Declares MCP tools for field conditions (read, create, update, delete)."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_field_conditions(
            ctx: Context[ServerSession, None],
            phase_id: PipefyId,
            debug: bool = False,
        ) -> dict[str, Any]:
            """List field conditions defined on a phase (rules, expressions, actions).

            Use after resolving ``phase_id`` (e.g. from ``get_pipe`` or ``get_phase_fields``)
            to inspect conditional field logic before creating or updating rules.

            Args:
                ctx: MCP context for debug logging.
                phase_id: Phase that owns the conditions.
                debug: When True, append GraphQL codes and correlation_id on errors.

            Returns:
                On success: ``success``, ``message``, and ``field_conditions`` (list from the API).
                On failure: ``success: False`` and ``error``.
            """
            await ctx.debug(
                f"get_field_conditions: phase_id={phase_id!r}, debug={debug}"
            )
            phase_id_str, err = validate_tool_id(phase_id, "phase_id")
            if err is not None:
                return err

            try:
                raw = await client.get_field_conditions(phase_id_str)
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc, "List field conditions failed.", debug=debug
                )

            phase = raw.get("phase")
            if phase is None:
                return {
                    "success": False,
                    "error": "Phase not found or access denied.",
                }

            rows = phase.get("fieldConditions")
            if rows is None:
                rows = []
            return {
                "success": True,
                "message": "Field conditions loaded.",
                "field_conditions": rows,
            }

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_field_condition(
            ctx: Context[ServerSession, None],
            field_condition_id: PipefyId,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Load one field condition by ID (name, phase, condition, actions).

            Args:
                ctx: MCP context for debug logging.
                field_condition_id: Field condition ID.
                debug: When True, append GraphQL codes and correlation_id on errors.

            Returns:
                On success: ``success``, ``message``, and ``field_condition`` (single object).
                On failure: ``success: False`` and ``error``.
            """
            await ctx.debug(
                f"get_field_condition: field_condition_id={field_condition_id!r}, debug={debug}"
            )
            cid, err = validate_tool_id(field_condition_id, "field_condition_id")
            if err is not None:
                return err

            try:
                raw = await client.get_field_condition(cid)
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc, "Get field condition failed.", debug=debug
                )

            fc = raw.get("fieldCondition")
            if fc is None:
                return {
                    "success": False,
                    "error": "Field condition not found or access denied.",
                }
            return {
                "success": True,
                "message": "Field condition loaded.",
                "field_condition": fc,
            }

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
        )
        async def create_field_condition(
            ctx: Context,
            phase_id: PipefyId,
            condition: dict[str, Any],
            actions: list[dict[str, Any]],
            name: str | None = None,
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a conditional field rule (Pipefy ``createFieldCondition``).

            ``name`` is **required** by the Pipefy API — omitting it returns
            ``"Validation failed: Name can't be blank"``. Pass it as the top-level
            ``name`` argument; for backwards compatibility it is also accepted inside
            ``extra_input={"name": ...}`` (top-level wins when both are set).

            **Working example** — hide field ``425848637`` when field ``425848636``
            equals ``"Option A"``::

                create_field_condition(
                    phase_id="342182326",
                    name="Hide brief when campaign is Option A",
                    condition={
                        "expressions": [
                            {
                                "structure_id": "0",
                                "field_address": "425848636",
                                "operation": "equals",
                                "value": "Option A"
                            }
                        ],
                        "expressions_structure": [["0"]]
                    },
                    actions=[
                        {
                            "phaseFieldId": "425848637",
                            "actionId": "hide"
                        }
                    ]
                )

            ``expressions_structure`` is an array of arrays of **string** indices
            (e.g. ``[["0"]]`` for one expression, ``[["0", "1"]]`` for AND). Each
            expression must carry a ``structure_id`` (string) referencing its
            position in the structure. Omitting either causes
            ``"Structure can't be blank"``.

            Args:
                ctx: MCP context for debug logging.
                phase_id: Phase ID that owns the condition (``phaseId`` on the API input).
                condition: ``ConditionInput`` dict. Must include ``expressions`` (list of expression
                    objects with ``structure_id``, ``field_address``, ``operation``, ``value``) and
                    ``expressions_structure`` (array of arrays of string indices).
                actions: List of ``FieldConditionActionInput`` dicts; use ``phaseFieldId`` (often the
                    field's ``internal_id`` from ``get_phase_fields``). Each action must include
                    ``actionId`` (``hide`` or ``show``); legacy ``hidden`` is mapped to ``hide``.
                name: Rule display name. Required by the API; may also be provided via
                    ``extra_input={"name": ...}`` for back-compat.
                extra_input: Optional extra keys for ``createFieldConditionInput`` (e.g. ``index``).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            await ctx.debug(
                f"create_field_condition: phase_id={phase_id!r}, debug={debug}"
            )
            pid, err = validate_tool_id(phase_id, "phase_id")
            if err is not None:
                return err
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
            act_err = field_condition_actions_error_message(actions)
            if act_err:
                return build_pipe_tool_error_payload(message=act_err)
            merged: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _CREATE_FIELD_CONDITION_EXTRA_RESERVED
            }
            if name is not None:
                if not isinstance(name, str) or not name.strip():
                    return build_pipe_tool_error_payload(
                        message="Invalid 'name': provide a non-empty string or omit.",
                    )
                merged["name"] = name
            if not merged.get("name"):
                return build_pipe_tool_error_payload(
                    message=(
                        "Missing 'name': Pipefy requires a rule name. Pass 'name' as a "
                        "top-level argument (or inside 'extra_input')."
                    ),
                )
            condition_for_api = strip_expression_ids_for_create(condition)
            actions_for_api = normalize_field_condition_actions(actions)
            try:
                raw = await client.create_field_condition(
                    pid,
                    condition_for_api,
                    actions_for_api,
                    **merged,
                )
            except Exception as exc:  # noqa: BLE001
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
            ctx: Context,
            condition_id: PipefyId,
            condition: dict[str, Any] | None = None,
            actions: list[dict[str, Any]] | None = None,
            name: str | None = None,
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update an existing field condition.

            Prefer the explicit ``condition``, ``actions``, and ``name`` parameters
            (same shapes as ``create_field_condition``) when changing rule logic.
            ``extra_input`` still carries other ``UpdateFieldConditionInput`` keys
            (e.g. ``index``). ``name`` in ``extra_input`` is also accepted for
            back-compat (top-level wins when both are set).

            Args:
                ctx: MCP context for debug logging.
                condition_id: Field condition ID to update.
                condition: Optional ``ConditionInput`` dict (same as create).
                actions: Optional list of ``FieldConditionActionInput`` dicts (same as create).
                name: Optional new rule name.
                extra_input: Additional fields to merge into ``UpdateFieldConditionInput``.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            await ctx.debug(
                f"update_field_condition: condition_id={condition_id!r}, debug={debug}"
            )
            cid_str, err = validate_tool_id(condition_id, "condition_id")
            if err is not None:
                return err
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
                act_err = field_condition_actions_error_message(actions)
                if act_err:
                    return build_pipe_tool_error_payload(message=act_err)

            update_attrs: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _UPDATE_FIELD_CONDITION_EXTRA_RESERVED
            }
            if name is not None:
                if not isinstance(name, str) or not name.strip():
                    return build_pipe_tool_error_payload(
                        message="Invalid 'name': provide a non-empty string or omit.",
                    )
                update_attrs["name"] = name
            if condition is not None:
                update_attrs["condition"] = strip_expression_ids_for_create(condition)
            if actions is not None:
                update_attrs["actions"] = normalize_field_condition_actions(actions)
            if not update_attrs:
                return build_pipe_tool_error_payload(
                    message=(
                        "Provide at least one of: 'condition', 'actions', or a non-empty "
                        "'extra_input' to update."
                    ),
                )
            try:
                raw = await client.update_field_condition(cid_str, **update_attrs)
            except Exception as exc:  # noqa: BLE001
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
            ctx: Context[ServerSession, None],
            condition_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a field condition permanently.

            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval. Elicitation does not authorize
            deletion (only ``confirm=True`` does).

            Args:
                ctx: MCP context for debug logging.
                condition_id: Field condition ID to delete.
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            await ctx.debug(
                f"delete_field_condition: condition_id={condition_id!r}, debug={debug}"
            )
            cid_str, err = validate_tool_id(condition_id, "condition_id")
            if err is not None:
                return err

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"field condition (ID: {condition_id})",
            )
            if guard is not None:
                return guard

            try:
                raw = await client.delete_field_condition(cid_str)
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc, "Delete field condition failed.", debug=debug
                )
            ok = bool(raw.get("success"))
            return build_field_condition_delete_payload(ok)
