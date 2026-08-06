"""MCP tools for Pipefy field condition read, create, update, and delete."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pipefy_sdk import PipefyId

from pipefy_mcp.core.tool_error_envelope import tool_error
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.field_condition_planner import (
    evaluate_condition_persistence,
    find_required_hidden_fields,
    phase_fields_from_payload,
)
from pipefy_mcp.tools.pipe_config_tool_helpers import (
    build_field_condition_delete_payload,
    build_field_condition_success_payload,
    build_pipe_tool_error_payload,
    field_condition_actions_error_message,
    handle_pipe_config_tool_graphql_error,
)
from pipefy_mcp.tools.remote_profile import REMOTE
from pipefy_mcp.tools.tool_context import get_pipefy_client
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
_UPDATE_FIELD_CONDITION_EXTRA_RESERVED = frozenset({"id", "actions"})

_VERIFY_UNAVAILABLE_WARNING = (
    "Field condition created but could not verify it persisted on the requested phase."
)

_CREATE_VERIFY_FAIL_RECOVERY = (
    " Delete this condition with delete_field_condition "
    "(confirm=true) using that condition_id before recreating; do not retry "
    "create on the same requested phase while that id exists."
)

_VERIFY_WRONG_PHASE_CODE = "FIELD_CONDITION_WRONG_PHASE"
_VERIFY_NOT_PERSISTED_CODE = "FIELD_CONDITION_NOT_PERSISTED"


def _field_condition_has_usable_phase_id(fetched: dict[str, Any]) -> bool:
    phase = fetched.get("phase")
    return isinstance(phase, dict) and phase.get("id") is not None


def _required_hidden_error_payload(field_ids: list[str]) -> dict[str, Any]:
    ids = ", ".join(field_ids)
    return build_pipe_tool_error_payload(
        message=(
            f"Cannot hide required field(s): {ids}. Clear required on the "
            f"field(s) first, or use show instead of hide."
        ),
        code="INVALID_ARGUMENTS",
    )


def _verify_fail_error_payload(
    *,
    message: str,
    code: str,
    condition_id: str,
    phase_id: str,
    actual_phase_id: str | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "condition_id": condition_id,
        "phase_id": phase_id,
    }
    if actual_phase_id is not None:
        details["actual_phase_id"] = actual_phase_id
    return build_pipe_tool_error_payload(
        message=message,
        code=code,
        details=details,
    )


async def _lint_required_hidden_actions(
    client: Any,
    phase_id: str,
    actions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Block when actions hide a required field; best-effort if fields cannot be read.

    Returns an error payload, or ``None`` when the mutation may proceed. The toolkit
    rejects required+hide even when the Pipefy API would accept it.
    """
    try:
        raw = await client.get_phase_fields(phase_id)
    except Exception:  # noqa: BLE001
        return None
    conflicts = find_required_hidden_fields(phase_fields_from_payload(raw), actions)
    if not conflicts:
        return None
    return _required_hidden_error_payload(conflicts)


async def _verify_created_field_condition(
    client: Any,
    phase_id: str,
    condition_id: str,
) -> dict[str, Any]:
    """Re-read after create; succeed only when the rule exists on ``phase_id``."""
    fetched: dict[str, Any] | None = None
    try:
        raw = await client.get_field_condition(condition_id)
        fc = raw.get("fieldCondition") if isinstance(raw, dict) else None
        if isinstance(fc, dict) and fc:
            fetched = fc
    except Exception:  # noqa: BLE001
        pass

    listed_ids: list[str] | None = None
    needs_list = fetched is None or not _field_condition_has_usable_phase_id(fetched)
    if needs_list:
        try:
            list_raw = await client.get_field_conditions(phase_id)
            phase = list_raw.get("phase") if isinstance(list_raw, dict) else None
            rows = phase.get("fieldConditions") if isinstance(phase, dict) else None
            if not isinstance(rows, list):
                rows = []
            listed_ids = [
                str(row["id"])
                for row in rows
                if isinstance(row, dict) and row.get("id") is not None
            ]
        except Exception:  # noqa: BLE001
            pass
        # List was required for a conclusive verdict and was not obtained.
        if listed_ids is None:
            return build_field_condition_success_payload(
                condition_id,
                "created",
                warning=_VERIFY_UNAVAILABLE_WARNING,
            )

    verdict = evaluate_condition_persistence(
        phase_id, condition_id, fetched, listed_ids
    )
    if verdict.status == "verified":
        return build_field_condition_success_payload(
            condition_id, "created", verified=True
        )
    if verdict.status == "wrong_phase":
        actual = verdict.actual_phase_id
        actual_note = f"; found on phase {actual}" if actual is not None else ""
        return _verify_fail_error_payload(
            message=(
                f"Field condition {condition_id} did not land on requested "
                f"phase {phase_id}{actual_note}.{_CREATE_VERIFY_FAIL_RECOVERY}"
            ),
            code=_VERIFY_WRONG_PHASE_CODE,
            condition_id=condition_id,
            phase_id=phase_id,
            actual_phase_id=actual,
        )
    return _verify_fail_error_payload(
        message=(
            f"Field condition {condition_id} did not persist on requested "
            f"phase {phase_id}.{_CREATE_VERIFY_FAIL_RECOVERY}"
        ),
        code=_VERIFY_NOT_PERSISTED_CODE,
        condition_id=condition_id,
        phase_id=phase_id,
    )


class FieldConditionTools:
    """Declares MCP tools for field conditions (read, create, update, delete)."""

    @staticmethod
    def register(mcp: MCPServer) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
            meta=REMOTE,
        )
        async def get_field_conditions(
            ctx: Context,
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
            client = get_pipefy_client(ctx)
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
                    exc,
                    "List field conditions failed.",
                    debug=debug,
                    resource_kind="phase",
                    resource_id=phase_id_str,
                )

            phase = raw.get("phase")
            if phase is None:
                return tool_error("Phase not found or access denied.")

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
            meta=REMOTE,
        )
        async def get_field_condition(
            ctx: Context,
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
            client = get_pipefy_client(ctx)
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
                    exc,
                    "Get field condition failed.",
                    debug=debug,
                    resource_kind="field_condition",
                    resource_id=cid,
                )

            fc = raw.get("fieldCondition")
            if fc is None:
                return tool_error("Field condition not found or access denied.")
            return {
                "success": True,
                "message": "Field condition loaded.",
                "field_condition": fc,
            }

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
            meta=REMOTE,
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

            After create, the tool re-reads the condition. Confirmed on the requested
            phase -> success with ``verified: true``. Missing or wrong phase ->
            ``success: false`` with ``error.code``
            (``FIELD_CONDITION_NOT_PERSISTED`` / ``FIELD_CONDITION_WRONG_PHASE``)
            and ``error.details`` (``condition_id``, ``phase_id``, optional
            ``actual_phase_id``). Delete with ``delete_field_condition`` and
            ``confirm=true`` before recreating; do not blind-retry create on the
            same phase. If verify evidence is inconclusive (list required and
            unavailable) -> success with a warning that verification was
            unavailable (no ``verified`` key).

            The toolkit **rejects** ``hide`` on a ``required=true`` field before
            calling the API (``success: false`` listing field ids), even though the
            Pipefy API may accept that combo. ``phaseFieldId`` may be
            ``internal_id``, ``id``, or ``uuid``. Clear ``required`` first or do
            not use ``hide``.

            **Working example** — hide field ``425848637`` when field ``425848636``
            equals ``"Option A"``::

                create_field_condition(
                    phase_id="342182326",
                    name="Hide brief when campaign is Option A",
                    condition={
                        "expressions": [
                            {
                                "structure_id": 0,
                                "field_address": "425848636",
                                "operation": "equals",
                                "value": "Option A"
                            }
                        ],
                        "expressions_structure": [[0]]
                    },
                    actions=[
                        {
                            "phaseFieldId": "425848637",
                            "actionId": "hide"
                        }
                    ]
                )

            ``expressions_structure`` is an array of arrays of indices (e.g.
            ``[[0]]`` for one expression, ``[[0, 1]]`` for AND). Each expression
            must carry a ``structure_id`` referencing its position in the
            structure. Omitting either causes ``"Structure can't be blank"``.

            The SDK normalizes the payload before calling the API
            (``pipefy_sdk.utils.normalize_field_condition_payload``): it drops any
            ``id`` keys (persisted PKs cause ``RECORD_NOT_FOUND`` on create) and
            coerces ``structure_id`` / ``expressions_structure`` entries to ``int``
            so callers can pass either strings or integers without triggering
            opaque ``INTERNAL_SERVER_ERROR`` responses from Pipefy.

            Args:
                ctx: MCP context for debug logging.
                phase_id: Phase ID that owns the condition (``phaseId`` on the API input).
                    Discover via: ``get_pipe(pipe_id)`` then inspect ``phases[].id``.
                condition: ``ConditionInput`` dict. Must include ``expressions`` (list of expression
                    objects with ``structure_id``, ``field_address``, ``operation``, ``value``) and
                    ``expressions_structure`` (array of arrays of string indices).
                    Discover via: ``get_phase_fields(phase_id)[].internal_id`` for ``field_address``.
                actions: List of ``FieldConditionActionInput`` dicts; each needs ``phaseFieldId``.
                    ``phaseFieldId`` is usually the field's ``internal_id`` from ``get_phase_fields``,
                    same pattern as ``fill_card_phase_fields`` and ``create_card_relation``.
                    Each action must include ``actionId`` (``hide`` or ``show``); legacy ``hidden`` is
                    mapped to ``hide``.
                name: Rule display name. Required by the API; may also be provided via
                    ``extra_input={"name": ...}`` for back-compat.
                extra_input: Optional extra keys for ``createFieldConditionInput`` (e.g. ``index``).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            client = get_pipefy_client(ctx)
            await ctx.debug(
                f"create_field_condition: phase_id={phase_id!r}, debug={debug}"
            )
            pid, err = validate_tool_id(phase_id, "phase_id")
            if err is not None:
                return err
            if not isinstance(condition, dict):
                return build_pipe_tool_error_payload(
                    message="Invalid 'condition': provide an object/dict.",
                    code="INVALID_ARGUMENTS",
                )
            if not condition:
                return build_pipe_tool_error_payload(
                    message="Invalid 'condition': provide a non-empty object (e.g. expressions).",
                    code="INVALID_ARGUMENTS",
                )
            expressions = condition.get("expressions")
            if isinstance(expressions, list) and len(expressions) == 0:
                return build_pipe_tool_error_payload(
                    message=(
                        "Invalid 'condition': 'expressions' must not be empty; "
                        "provide at least one expression."
                    ),
                    code="INVALID_ARGUMENTS",
                )
            if extra_input is not None and not isinstance(extra_input, dict):
                return build_pipe_tool_error_payload(
                    message="Invalid 'extra_input': provide an object/dict or omit.",
                    code="INVALID_ARGUMENTS",
                )
            act_err = field_condition_actions_error_message(actions)
            if act_err:
                return build_pipe_tool_error_payload(
                    message=act_err, code="INVALID_ARGUMENTS"
                )
            merged: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _CREATE_FIELD_CONDITION_EXTRA_RESERVED
            }
            if name is not None:
                if not isinstance(name, str) or not name.strip():
                    return build_pipe_tool_error_payload(
                        message="Invalid 'name': provide a non-empty string or omit.",
                        code="INVALID_ARGUMENTS",
                    )
                merged["name"] = name
            if not merged.get("name"):
                return build_pipe_tool_error_payload(
                    message=(
                        "Missing 'name': Pipefy requires a rule name. Pass 'name' as a "
                        "top-level argument (or inside 'extra_input')."
                    ),
                    code="INVALID_ARGUMENTS",
                )
            lint_err = await _lint_required_hidden_actions(client, pid, actions)
            if lint_err is not None:
                return lint_err
            try:
                raw = await client.create_field_condition(
                    pid,
                    condition,
                    actions,
                    **merged,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Create field condition failed.",
                    debug=debug,
                    resource_kind="phase",
                    resource_id=pid,
                    invalid_args_hint=(
                        "Use 'get_phase_fields' to list valid 'internal_id' values for "
                        "'field_address' / 'phaseFieldId'."
                    ),
                )
            fc = raw.get("createFieldCondition", {}).get("fieldCondition") or {}
            cid = fc.get("id")
            if cid is None or cid == "":
                return build_pipe_tool_error_payload(
                    message=(
                        "Create field condition succeeded but no condition id was returned."
                    ),
                    code="INVALID_ARGUMENTS",
                )
            cid_str = str(cid)
            return await _verify_created_field_condition(client, pid, cid_str)

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
            meta=REMOTE,
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
            back-compat (top-level wins when both are set). ``actions`` in
            ``extra_input`` is rejected (``INVALID_ARGUMENTS``); use the top-level
            ``actions`` argument.

            When ``actions`` is provided, the toolkit rejects ``hide`` on a
            ``required=true`` field before calling the API (``success: false``
            listing field ids), even though the Pipefy API may accept that combo.
            Phase is discovered via get-by-id; lint is best-effort if phase fields
            cannot be loaded. Clear ``required`` first or do not use ``hide``.

            Args:
                ctx: MCP context for debug logging.
                condition_id: Field condition ID to update.
                    Discover via: ``get_field_conditions(phase_id)[].id``.
                condition: Optional ``ConditionInput`` dict (same as create).
                    Discover via: ``get_phase_fields(phase_id)[].internal_id`` for ``field_address``.
                actions: Optional list of ``FieldConditionActionInput`` dicts (same as create).
                    Discover via: ``get_phase_fields(phase_id)[].internal_id`` for ``phaseFieldId``.
                name: Optional new rule name.
                extra_input: Additional fields to merge into ``UpdateFieldConditionInput``.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            client = get_pipefy_client(ctx)
            await ctx.debug(
                f"update_field_condition: condition_id={condition_id!r}, debug={debug}"
            )
            cid_str, err = validate_tool_id(condition_id, "condition_id")
            if err is not None:
                return err
            if extra_input is not None and not isinstance(extra_input, dict):
                return build_pipe_tool_error_payload(
                    message="Invalid 'extra_input': provide an object/dict or omit.",
                    code="INVALID_ARGUMENTS",
                )
            if extra_input is not None and "actions" in extra_input:
                return build_pipe_tool_error_payload(
                    message=(
                        "Invalid 'extra_input': do not pass 'actions' here; use the "
                        "top-level 'actions' argument."
                    ),
                    code="INVALID_ARGUMENTS",
                )
            if condition is not None and not isinstance(condition, dict):
                return build_pipe_tool_error_payload(
                    message="Invalid 'condition': provide an object/dict or omit.",
                    code="INVALID_ARGUMENTS",
                )
            if condition is not None:
                expressions = condition.get("expressions")
                if isinstance(expressions, list) and len(expressions) == 0:
                    return build_pipe_tool_error_payload(
                        message=(
                            "Invalid 'condition': 'expressions' must not be empty; "
                            "provide at least one expression."
                        ),
                        code="INVALID_ARGUMENTS",
                    )
            if actions is not None:
                act_err = field_condition_actions_error_message(actions)
                if act_err:
                    return build_pipe_tool_error_payload(
                        message=act_err, code="INVALID_ARGUMENTS"
                    )

            update_attrs: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _UPDATE_FIELD_CONDITION_EXTRA_RESERVED
            }
            if name is not None:
                if not isinstance(name, str) or not name.strip():
                    return build_pipe_tool_error_payload(
                        message="Invalid 'name': provide a non-empty string or omit.",
                        code="INVALID_ARGUMENTS",
                    )
                update_attrs["name"] = name
            if condition is not None:
                update_attrs["condition"] = condition
            if actions is not None:
                update_attrs["actions"] = actions
            if not update_attrs:
                return build_pipe_tool_error_payload(
                    message=(
                        "Provide at least one of: 'condition', 'actions', or a non-empty "
                        "'extra_input' to update."
                    ),
                    code="INVALID_ARGUMENTS",
                )
            if actions is not None:
                try:
                    cond_raw = await client.get_field_condition(cid_str)
                    fc_obj = (
                        cond_raw.get("fieldCondition")
                        if isinstance(cond_raw, dict)
                        else None
                    )
                    phase = fc_obj.get("phase") if isinstance(fc_obj, dict) else None
                    phase_id = phase.get("id") if isinstance(phase, dict) else None
                    if phase_id is not None:
                        lint_err = await _lint_required_hidden_actions(
                            client, str(phase_id), actions
                        )
                        if lint_err is not None:
                            return lint_err
                except Exception:  # noqa: BLE001
                    pass
            try:
                raw = await client.update_field_condition(cid_str, **update_attrs)
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Update field condition failed.",
                    debug=debug,
                    resource_kind="field_condition",
                    resource_id=cid_str,
                    invalid_args_hint=(
                        "Use 'get_phase_fields' to list valid 'internal_id' values for "
                        "'field_address' / 'phaseFieldId'."
                    ),
                )
            fc = raw.get("updateFieldCondition", {}).get("fieldCondition") or {}
            out_id = fc.get("id")
            if out_id is None or out_id == "":
                return build_pipe_tool_error_payload(
                    message=(
                        "Update field condition succeeded but no condition id was returned."
                    ),
                    code="INVALID_ARGUMENTS",
                )
            return build_field_condition_success_payload(str(out_id), "updated")

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
            meta=REMOTE,
        )
        async def delete_field_condition(
            ctx: Context,
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
            client = get_pipefy_client(ctx)
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
                    exc,
                    "Delete field condition failed.",
                    debug=debug,
                    resource_kind="field_condition",
                    resource_id=cid_str,
                )
            ok = bool(raw.get("success"))
            return build_field_condition_delete_payload(ok)
