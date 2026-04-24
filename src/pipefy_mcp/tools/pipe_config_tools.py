from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from pipefy_mcp.models.validators import PipefyId
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.graphql_error_helpers import (
    extract_error_strings,
    extract_graphql_correlation_id,
    extract_graphql_error_codes,
    with_debug_suffix,
)
from pipefy_mcp.tools.pipe_config_tool_helpers import (
    build_delete_pipe_error_payload,
    build_delete_pipe_success_payload,
    build_pipe_mutation_success_payload,
    build_pipe_tool_error_payload,
    handle_pipe_config_tool_graphql_error,
    map_delete_pipe_error_to_message,
)
from pipefy_mcp.tools.tool_error_envelope import tool_error_message
from pipefy_mcp.tools.validation_helpers import (
    validate_optional_tool_id,
    validate_tool_id,
)

_CREATE_PHASE_FIELD_EXTRA_RESERVED = frozenset({"phase_id", "label", "type"})
_UPDATE_PHASE_FIELD_EXTRA_RESERVED = frozenset({"id", "uuid"})
_UPDATE_LABEL_EXTRA_RESERVED = frozenset({"id"})
# Upstream signatures for the generic Pipefy failure that most often means the
# parent phase was deleted in the same session and the field was cascaded.
_CASCADE_ERROR_MARKERS = ("internal_server_error", "something went wrong")


async def _diagnose_phase_field_cascade(
    client: PipefyClient,
    exc: BaseException,
    field_id: str,
    pipe_id: str | None,
) -> dict[str, Any] | None:
    """Return an enriched error payload if the field was likely cascaded.

    Only runs when ``pipe_id`` is provided and the raw exception matches the
    generic Pipefy INTERNAL_SERVER_ERROR shape. Walks every phase of the pipe
    to confirm that ``field_id`` is no longer present; if absent everywhere,
    we infer the phase was deleted earlier in the same session (which cascades
    the field) and return an actionable message instead of the opaque upstream
    error.
    """
    if pipe_id is None:
        return None
    # gql's ``TransportQueryError`` hides the structured per-error ``message``
    # and ``extensions.code`` behind attributes, so ``str(exc)`` alone only
    # returns the outer wrapper ("GraphQL Error"). Combine both signals.
    signal_parts: list[str] = [str(exc).lower()]
    signal_parts.extend(m.lower() for m in extract_error_strings(exc))
    signal_parts.extend(c.lower() for c in extract_graphql_error_codes(exc))
    if not any(
        marker in part for marker in _CASCADE_ERROR_MARKERS for part in signal_parts
    ):
        return None
    try:
        pipe_data = await client.get_pipe(pipe_id)
    except Exception:  # noqa: BLE001
        return None
    pipe_obj = (pipe_data or {}).get("pipe") or {}
    phase_ids = [
        str(p.get("id"))
        for p in (pipe_obj.get("phases") or [])
        if p.get("id") is not None
    ]
    for pid in phase_ids:
        try:
            fields_data = await client.get_phase_fields(pid)
        except Exception:  # noqa: BLE001
            continue
        fields = fields_data.get("fields") if isinstance(fields_data, dict) else None
        if not isinstance(fields, list):
            continue
        for f in fields:
            if not isinstance(f, dict):
                continue
            if str(f.get("id")) == field_id or str(f.get("uuid")) == field_id:
                # Field still exists — the error is not a cascade.
                return None
    return build_pipe_tool_error_payload(
        message=(
            f"Phase field '{field_id}' no longer exists in pipe {pipe_id}. "
            "The Pipefy API returned INTERNAL_SERVER_ERROR, which typically "
            "means the parent phase was deleted in the same session and the "
            "field was cascaded automatically — no further action needed. "
            "If you expected the field to still exist, verify with "
            "get_phase_fields on each phase of this pipe."
        ),
        code="NOT_FOUND",
    )


class PipeConfigTools:
    """MCP tools for pipe, phase, field, and label configuration (builder CRUD)."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
        )
        async def create_pipe(
            name: str,
            organization_id: PipefyId,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a new empty pipe in an organization.

            Add phases, fields, and labels with the dedicated tools after the pipe exists.

            Args:
                name: Display name of the pipe.
                organization_id: Organization ID that will own the pipe.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not isinstance(name, str) or not name.strip():
                return build_pipe_tool_error_payload(
                    message="Invalid 'name': provide a non-empty string.",
                    code="INVALID_ARGUMENTS",
                )
            org_id, err = validate_tool_id(organization_id, "organization_id")
            if err is not None:
                return err
            try:
                raw = await client.create_pipe(name.strip(), org_id)
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Create pipe failed.",
                    debug=debug,
                    resource_kind="organization",
                    resource_id=org_id,
                )
            return build_pipe_mutation_success_payload(
                label="Pipe created.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
        )
        async def update_pipe(
            pipe_id: PipefyId,
            name: str | None = None,
            icon: str | None = None,
            color: str | None = None,
            preferences: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update pipe settings (name, icon, color, preferences).

            Pass only fields you want to change. Use schema introspection on
            `UpdatePipeInput` for the full attribute list.

            Args:
                pipe_id: Pipe ID to update.
                name: New name, if changing.
                icon: Icon identifier, if changing.
                color: Color enum/string per API, if changing.
                preferences: Repo preferences object, if changing.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            pipe_id_str, err = validate_tool_id(pipe_id, "pipe_id")
            if err is not None:
                return err
            if all(x is None for x in (name, icon, color, preferences)):
                return build_pipe_tool_error_payload(
                    message=(
                        "Provide at least one of: name, icon, color, preferences."
                    ),
                    code="INVALID_ARGUMENTS",
                )
            try:
                raw = await client.update_pipe(
                    pipe_id_str,
                    name=name,
                    icon=icon,
                    color=color,
                    preferences=preferences,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Update pipe failed.",
                    debug=debug,
                    resource_kind="pipe",
                    resource_id=pipe_id_str,
                )
            return build_pipe_mutation_success_payload(
                label="Pipe updated.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_pipe(
            ctx: Context[ServerSession, None],
            pipe_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a pipe permanently.

            Without confirmation, returns a preview of the pipe and does not delete.
            Always confirm the impact with the human user before calling with confirm=True.

            Args:
                pipe_id: Pipe ID to delete.
                confirm: When True, performs the deletion after explicit user confirmation.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            pipe_id_str, err = validate_tool_id(pipe_id, "pipe_id")
            if err is not None:
                return build_delete_pipe_error_payload(message=tool_error_message(err))

            pipe_name = "Unknown"
            try:
                pipe_response = await client.get_pipe(pipe_id_str)
                pipe_data = pipe_response.get("pipe") or {}
                pipe_name = pipe_data.get("name") or "Unknown"
            except Exception as exc:  # noqa: BLE001
                codes = extract_graphql_error_codes(exc)
                correlation_id = extract_graphql_correlation_id(exc)
                base = map_delete_pipe_error_to_message(
                    pipe_id=pipe_id_str,
                    pipe_name=pipe_name,
                    codes=codes,
                )
                return build_delete_pipe_error_payload(
                    message=with_debug_suffix(
                        base,
                        debug=debug,
                        codes=codes,
                        correlation_id=correlation_id,
                    ),
                )

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"pipe '{pipe_name}' (ID: {pipe_id_str})",
            )
            if guard is not None:
                return guard

            try:
                delete_response = await client.delete_pipe(pipe_id_str)
                success = (delete_response.get("deletePipe") or {}).get("success")
                if success:
                    return build_delete_pipe_success_payload(pipe_id=pipe_id_str)
                return build_delete_pipe_error_payload(
                    message=map_delete_pipe_error_to_message(
                        pipe_id=pipe_id_str,
                        pipe_name=pipe_name,
                        codes=[],
                    )
                )
            except Exception as exc:  # noqa: BLE001
                codes = extract_graphql_error_codes(exc)
                correlation_id = extract_graphql_correlation_id(exc)
                base = map_delete_pipe_error_to_message(
                    pipe_id=pipe_id_str,
                    pipe_name=pipe_name,
                    codes=codes,
                )
                return build_delete_pipe_error_payload(
                    message=with_debug_suffix(
                        base,
                        debug=debug,
                        codes=codes,
                        correlation_id=correlation_id,
                    )
                )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
        )
        async def clone_pipe(
            pipe_template_id: PipefyId,
            organization_id: PipefyId | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Clone a pipe from a template pipe ID.

            Returns cloned pipe objects (including new IDs) from the API payload.

            Args:
                pipe_template_id: Source pipe ID to use as template.
                organization_id: Optional organization ID for the clone operation.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            pipe_template_id, err = validate_tool_id(
                pipe_template_id, "pipe_template_id"
            )
            if err is not None:
                return err
            ok, organization_id, err = validate_optional_tool_id(
                organization_id, "organization_id"
            )
            if not ok:
                return err
            try:
                raw = await client.clone_pipe(
                    pipe_template_id,
                    organization_id=organization_id,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Clone pipe failed.",
                    debug=debug,
                    resource_kind="pipe",
                    resource_id=str(pipe_template_id),
                )
            return build_pipe_mutation_success_payload(
                label="Pipe(s) cloned.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
        )
        async def create_phase(
            pipe_id: PipefyId,
            name: str,
            done: bool = False,
            index: float | int | None = None,
            description: str | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a phase in a pipe.

            Args:
                pipe_id: Pipe that will contain the phase.
                name: Phase name.
                done: When True, marks a final/done phase.
                index: Optional position index within the pipe.
                description: Optional phase description.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            pipe_id, err = validate_tool_id(pipe_id, "pipe_id")
            if err is not None:
                return err
            if not isinstance(name, str) or not name.strip():
                return build_pipe_tool_error_payload(
                    message="Invalid 'name': provide a non-empty string.",
                    code="INVALID_ARGUMENTS",
                )
            try:
                raw = await client.create_phase(
                    pipe_id,
                    name.strip(),
                    done=done,
                    index=index,
                    description=description,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Create phase failed.",
                    debug=debug,
                    resource_kind="pipe",
                    resource_id=str(pipe_id),
                )
            return build_pipe_mutation_success_payload(
                label="Phase created.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
        )
        async def update_phase(
            phase_id: PipefyId,
            name: str | None = None,
            description: str | None = None,
            done: bool | None = None,
            color: str | None = None,
            lateness_time: int | None = None,
            can_receive_card_directly_from_draft: bool | None = None,
            only_admin_can_move_to_previous: bool | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update a phase.

            Pipefy requires the phase name on update. Omit `name` to keep the current
            name (resolved via get_phase_fields). Values identical to the current state
            are accepted but result in a no-op API call.

            Args:
                phase_id: Phase ID to update.
                    Discover via: ``get_pipe(pipe_id).phases[].id``.
                name: New name, if changing.
                description: New description, if changing.
                done: Whether the phase is a final phase, if changing.
                color: Phase color (API enum), if changing.
                lateness_time: SLA in seconds, if changing.
                can_receive_card_directly_from_draft: If changing.
                only_admin_can_move_to_previous: If changing (deprecated in API).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            phase_id, err = validate_tool_id(phase_id, "phase_id")
            if err is not None:
                return err

            update_attrs: dict[str, Any] = {}
            if name is not None:
                update_attrs["name"] = name
            if description is not None:
                update_attrs["description"] = description
            if done is not None:
                update_attrs["done"] = done
            if color is not None:
                update_attrs["color"] = color
            if lateness_time is not None:
                update_attrs["lateness_time"] = lateness_time
            if can_receive_card_directly_from_draft is not None:
                update_attrs["can_receive_card_directly_from_draft"] = (
                    can_receive_card_directly_from_draft
                )
            if only_admin_can_move_to_previous is not None:
                update_attrs["only_admin_can_move_to_previous"] = (
                    only_admin_can_move_to_previous
                )

            if not update_attrs:
                return build_pipe_tool_error_payload(
                    message="Provide at least one attribute to update.",
                    code="INVALID_ARGUMENTS",
                )

            if "name" not in update_attrs:
                try:
                    phase_info = await client.get_phase_fields(phase_id)
                except Exception as exc:  # noqa: BLE001
                    return handle_pipe_config_tool_graphql_error(
                        exc,
                        "Could not load phase.",
                        debug=debug,
                        resource_kind="phase",
                        resource_id=str(phase_id),
                    )
                current = phase_info.get("phase_name")
                if not current:
                    return build_pipe_tool_error_payload(
                        message=f"Phase {phase_id} not found or has no name.",
                        code="INVALID_ARGUMENTS",
                    )
                update_attrs["name"] = current

            try:
                raw = await client.update_phase(phase_id, **update_attrs)
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Update phase failed.",
                    debug=debug,
                    resource_kind="phase",
                    resource_id=str(phase_id),
                )
            return build_pipe_mutation_success_payload(
                label="Phase updated.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_phase(
            ctx: Context[ServerSession, None],
            phase_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a phase permanently.

            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval. Elicitation does not authorize
            deletion (only ``confirm=True`` does).

            Args:
                phase_id: Phase ID to delete.
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            phase_id, err = validate_tool_id(phase_id, "phase_id")
            if err is not None:
                return err

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"phase (ID: {phase_id})",
            )
            if guard is not None:
                return guard

            try:
                raw = await client.delete_phase(phase_id)
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Delete phase failed.",
                    debug=debug,
                    resource_kind="phase",
                    resource_id=str(phase_id),
                )
            return build_pipe_mutation_success_payload(
                label="Phase deleted.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
        )
        async def create_phase_field(
            phase_id: PipefyId,
            label: str,
            field_type: str,
            options: list[str] | None = None,
            description: str | None = None,
            required: bool | None = None,
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a custom field on a phase.

            ``field_type`` is passed through to Pipefy (use schema introspection on
            ``CreatePhaseFieldInput`` to list valid types).

            The response includes ``internal_id`` — use that numeric ID (not the slug
            ``id``) for subsequent ``update_phase_field`` or ``delete_phase_field`` calls.

            Args:
                phase_id: Phase that will receive the field.
                    Discover via: ``get_pipe(pipe_id).phases[].id``.
                label: Field label shown in the UI.
                field_type: Pipefy field type string (API input field ``type``).
                options: Option values for select/radio/checklist fields (e.g. ["Alta", "Média", "Baixa"]).
                description: Optional field description.
                required: Whether the field is required.
                extra_input: Additional ``CreatePhaseFieldInput`` fields, if any.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            phase_id, err = validate_tool_id(phase_id, "phase_id")
            if err is not None:
                return err
            if not isinstance(label, str) or not label.strip():
                return build_pipe_tool_error_payload(
                    message="Invalid 'label': provide a non-empty string.",
                    code="INVALID_ARGUMENTS",
                )
            if not isinstance(field_type, str) or not field_type.strip():
                return build_pipe_tool_error_payload(
                    message="Invalid 'field_type': provide a non-empty string.",
                    code="INVALID_ARGUMENTS",
                )
            merged: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _CREATE_PHASE_FIELD_EXTRA_RESERVED
            }
            if options is not None:
                merged["options"] = options
            if description is not None:
                merged["description"] = description
            if required is not None:
                merged["required"] = required
            try:
                raw = await client.create_phase_field(
                    phase_id,
                    label.strip(),
                    field_type.strip(),
                    **merged,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Create phase field failed.",
                    debug=debug,
                    resource_kind="phase",
                    resource_id=str(phase_id),
                )
            return build_pipe_mutation_success_payload(
                label="Phase field created.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
        )
        async def update_phase_field(
            field_id: PipefyId,
            label: str,
            description: str | None = None,
            required: bool | None = None,
            options: list[Any] | dict[str, Any] | None = None,
            uuid: str | None = None,
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update a phase field.

            Pass only fields to change (besides ``label`` which is always required by the API).

            ``field_id`` is the field slug (e.g. ``"prioridade"``) returned by
            ``create_phase_field`` or ``get_phase_fields``. When the same slug exists on
            multiple phases, pass ``uuid`` to disambiguate (available from
            ``create_phase_field`` and ``get_phase_fields``).

            Args:
                field_id: Field slug (from create_phase_field or get_phase_fields).
                    Discover via: ``get_phase_fields(phase_id)[].id`` (or ``uuid`` for disambiguation).
                label: Field label (required by the Pipefy API even if unchanged — pass the current value).
                description: New description, if changing.
                required: Whether the field is required, if changing.
                options: Field options list (e.g. ["Alta", "Média", "Baixa"] for select fields).
                uuid: Field UUID for disambiguation when the slug exists on multiple phases.
                    Discover via: ``get_phase_fields(phase_id)[].uuid``.
                extra_input: Additional UpdatePhaseFieldInput fields, if any.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            field_id, err = validate_tool_id(field_id, "field_id")
            if err is not None:
                return err
            if not isinstance(label, str) or not label.strip():
                return build_pipe_tool_error_payload(
                    message=(
                        "Invalid 'label': the Pipefy API requires label on every update "
                        "(pass the current label if unchanged)."
                    ),
                    code="INVALID_ARGUMENTS",
                )
            update_attrs: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _UPDATE_PHASE_FIELD_EXTRA_RESERVED
            }
            update_attrs["label"] = label
            if description is not None:
                update_attrs["description"] = description
            if required is not None:
                update_attrs["required"] = required
            if options is not None:
                update_attrs["options"] = options
            if uuid is not None:
                update_attrs["uuid"] = uuid
            fid = field_id.strip() if isinstance(field_id, str) else field_id
            try:
                raw = await client.update_phase_field(fid, **update_attrs)
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Update phase field failed.",
                    debug=debug,
                    resource_kind="phase_field",
                    resource_id=str(fid),
                    invalid_args_hint=(
                        "Use 'get_phase_fields' to list valid field slugs and UUIDs."
                    ),
                )
            return build_pipe_mutation_success_payload(
                label="Phase field updated.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_phase_field(
            ctx: Context[ServerSession, None],
            field_id: PipefyId,
            confirm: bool = False,
            pipe_uuid: str | None = None,
            pipe_id: PipefyId | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a phase field permanently.

            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval. Elicitation does not authorize
            deletion (only ``confirm=True`` does).

            ``field_id`` is the field slug (e.g. ``"prioridade"``) or uuid.
            When the slug is shared across phases, pass ``pipe_uuid`` to
            disambiguate (available from ``get_pipe``).

            **Cascade-aware error diagnosis:** pass ``pipe_id`` (numeric) to enable
            a post-hoc check when the Pipefy API returns a generic
            ``INTERNAL_SERVER_ERROR``. This error often fires when the parent
            phase was deleted earlier in the same session and the field was
            cascaded automatically. When ``pipe_id`` is provided, the tool
            verifies whether the field still exists in the pipe's phases and
            returns an actionable message; without ``pipe_id`` the raw
            upstream error is returned.

            Args:
                field_id: Field slug or uuid (from create_phase_field or get_phase_fields).
                    Discover via: ``get_phase_fields(phase_id)[].id`` or ``.uuid``.
                confirm: Set to True to execute the deletion (step 2).
                pipe_uuid: Pipe UUID for disambiguation when the slug is not unique across phases.
                pipe_id: Numeric pipe ID; enables cascade-aware error diagnosis when set.
                    Discover via: ``search_pipes`` or ``get_organization``.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            field_id, err = validate_tool_id(field_id, "field_id")
            if err is not None:
                return err
            ok_p, pipe_id_norm, pid_err = validate_optional_tool_id(pipe_id, "pipe_id")
            if not ok_p:
                return build_pipe_tool_error_payload(
                    message=tool_error_message(pid_err),
                    code="INVALID_ARGUMENTS",
                )

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"phase field (ID: {field_id})",
            )
            if guard is not None:
                return guard

            try:
                raw = await client.delete_phase_field(field_id, pipe_uuid=pipe_uuid)
            except Exception as exc:  # noqa: BLE001
                enriched = await _diagnose_phase_field_cascade(
                    client, exc, field_id, pipe_id_norm
                )
                if enriched is not None:
                    return enriched
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Delete phase field failed.",
                    debug=debug,
                    resource_kind="phase_field",
                    resource_id=str(field_id),
                )
            return build_pipe_mutation_success_payload(
                label="Phase field deleted.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
        )
        async def create_label(
            pipe_id: PipefyId,
            name: str,
            color: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a label on a pipe.

            Args:
                pipe_id: Pipe that will receive the label.
                name: Label name.
                color: Label color (per Pipefy/API).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            pipe_id, err = validate_tool_id(pipe_id, "pipe_id")
            if err is not None:
                return err
            if not isinstance(name, str) or not name.strip():
                return build_pipe_tool_error_payload(
                    message="Invalid 'name': provide a non-empty string.",
                    code="INVALID_ARGUMENTS",
                )
            if not isinstance(color, str) or not color.strip():
                return build_pipe_tool_error_payload(
                    message="Invalid 'color': provide a non-empty string.",
                    code="INVALID_ARGUMENTS",
                )
            try:
                raw = await client.create_label(
                    pipe_id,
                    name.strip(),
                    color.strip(),
                )
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Create label failed.",
                    debug=debug,
                    resource_kind="pipe",
                    resource_id=str(pipe_id),
                )
            return build_pipe_mutation_success_payload(
                label="Label created.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
            ),
        )
        async def update_label(
            label_id: PipefyId,
            name: str,
            color: str,
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update a pipe label.

            Both ``name`` and ``color`` are **required on every call**. Pipefy's
            ``UpdateLabelInput`` schema declares both as NON_NULL — there is no
            partial-update path. To change just one attribute, fetch the current
            value for the other via ``get_labels(pipe_id)`` and pass it through.

            Args:
                label_id: Label ID to update.
                name: New label name (non-empty).
                color: New label color, hex string (non-empty).
                extra_input: Additional UpdateLabelInput fields, if any.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            label_id, err = validate_tool_id(label_id, "label_id")
            if err is not None:
                return err
            if not isinstance(name, str) or not name.strip():
                return build_pipe_tool_error_payload(
                    message="Invalid 'name': provide a non-empty string.",
                    code="INVALID_ARGUMENTS",
                )
            if not isinstance(color, str) or not color.strip():
                return build_pipe_tool_error_payload(
                    message="Invalid 'color': provide a non-empty string.",
                    code="INVALID_ARGUMENTS",
                )
            update_attrs: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _UPDATE_LABEL_EXTRA_RESERVED
            }
            update_attrs["name"] = name.strip()
            update_attrs["color"] = color.strip()
            try:
                raw = await client.update_label(label_id, **update_attrs)
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Update label failed.",
                    debug=debug,
                    resource_kind="label",
                    resource_id=str(label_id),
                )
            return build_pipe_mutation_success_payload(
                label="Label updated.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_label(
            ctx: Context[ServerSession, None],
            label_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a label permanently.

            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval. Elicitation does not authorize
            deletion (only ``confirm=True`` does).

            Args:
                label_id: Label ID to delete.
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            label_id, err = validate_tool_id(label_id, "label_id")
            if err is not None:
                return err

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"label (ID: {label_id})",
            )
            if guard is not None:
                return guard

            try:
                raw = await client.delete_label(label_id)
            except Exception as exc:  # noqa: BLE001
                return handle_pipe_config_tool_graphql_error(
                    exc,
                    "Delete label failed.",
                    debug=debug,
                    resource_kind="label",
                    resource_id=str(label_id),
                )
            return build_pipe_mutation_success_payload(
                label="Label deleted.",
                data=raw,
            )
