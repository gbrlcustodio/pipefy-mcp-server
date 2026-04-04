"""MCP tools for Pipefy field condition create, update, and delete."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

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
            ctx: Context,
            phase_id: str | int,
            condition: dict[str, Any],
            actions: list[dict[str, Any]],
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a conditional field rule (Pipefy ``createFieldCondition``).

            Args:
                ctx: MCP context for debug logging.
                phase_id: Phase ID that owns the condition (``phaseId`` on the API input).
                condition: ``ConditionInput`` dict (e.g. ``expressions``, ``expressions_structure``).
                actions: List of ``FieldConditionActionInput`` dicts; use ``phaseFieldId`` (often the
                    field's ``internal_id`` from ``get_phase_fields``). Each action must include
                    ``actionId`` (``hide`` or ``show``); legacy ``hidden`` is mapped to ``hide``.
                extra_input: Optional extra keys for ``createFieldConditionInput`` (e.g. ``name``, ``index``).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            await ctx.debug(
                f"create_field_condition: phase_id={phase_id!r}, debug={debug}"
            )
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
            act_err = field_condition_actions_error_message(actions)
            if act_err:
                return build_pipe_tool_error_payload(message=act_err)
            merged: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _CREATE_FIELD_CONDITION_EXTRA_RESERVED
            }
            condition_for_api = strip_expression_ids_for_create(condition)
            actions_for_api = normalize_field_condition_actions(actions)
            try:
                raw = await client.create_field_condition(
                    phase_id,
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
                ctx: MCP context for debug logging.
                condition_id: Field condition ID to update.
                condition: Optional ``ConditionInput`` dict (same as create).
                actions: Optional list of ``FieldConditionActionInput`` dicts (same as create).
                extra_input: Additional fields to merge into ``UpdateFieldConditionInput``.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            await ctx.debug(
                f"update_field_condition: condition_id={condition_id!r}, debug={debug}"
            )
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
                act_err = field_condition_actions_error_message(actions)
                if act_err:
                    return build_pipe_tool_error_payload(message=act_err)

            update_attrs: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _UPDATE_FIELD_CONDITION_EXTRA_RESERVED
            }
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
            cid_key = (
                condition_id.strip()
                if isinstance(condition_id, str)
                else str(condition_id)
            )
            try:
                raw = await client.update_field_condition(cid_key, **update_attrs)
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
            condition_id: str | int,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a field condition permanently.

            Two-step operation: call without ``confirm`` to preview, then with
            ``confirm=True`` after user approval. When the MCP client supports
            elicitation, the user is prompted interactively instead.

            Args:
                ctx: MCP context for debug logging.
                condition_id: Field condition ID to delete.
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            await ctx.debug(
                f"delete_field_condition: condition_id={condition_id!r}, debug={debug}"
            )
            if not valid_phase_field_id(condition_id):
                return build_pipe_tool_error_payload(
                    message=(
                        "Invalid 'condition_id'. Use a non-empty string or a positive integer."
                    ),
                )

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"field condition (ID: {condition_id})",
            )
            if guard is not None:
                return guard

            cid_key = (
                condition_id.strip()
                if isinstance(condition_id, str)
                else str(condition_id)
            )
            try:
                raw = await client.delete_field_condition(cid_key)
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc, "Delete field condition failed.", debug=debug
                )
            ok = bool(raw.get("success"))
            return build_field_condition_delete_payload(ok)
