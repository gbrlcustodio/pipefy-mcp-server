from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.graphql_error_helpers import (
    extract_graphql_correlation_id,
    extract_graphql_error_codes,
    with_debug_suffix,
)
from pipefy_mcp.tools.pipe_config_tool_helpers import (
    build_delete_pipe_error_payload,
    build_delete_pipe_preview_payload,
    build_delete_pipe_success_payload,
    build_pipe_mutation_success_payload,
    build_pipe_tool_error_payload,
    handle_pipe_config_tool_graphql_error,
    map_delete_pipe_error_to_message,
)
from pipefy_mcp.tools.pipe_config_validators import valid_phase_field_id

_CREATE_PHASE_FIELD_EXTRA_RESERVED = frozenset({"phase_id", "label", "type"})
_UPDATE_PHASE_FIELD_EXTRA_RESERVED = frozenset({"id"})
_UPDATE_LABEL_EXTRA_RESERVED = frozenset({"id"})


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
            organization_id: int,
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
                )
            if not isinstance(organization_id, int) or organization_id <= 0:
                return build_pipe_tool_error_payload(
                    message="Invalid 'organization_id'. Use a positive integer.",
                )
            try:
                raw = await client.create_pipe(name.strip(), organization_id)
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Create pipe failed.", debug=debug
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
            pipe_id: int,
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
            if not isinstance(pipe_id, int) or pipe_id <= 0:
                return build_pipe_tool_error_payload(
                    message="Invalid 'pipe_id'. Use a positive integer.",
                )
            if all(x is None for x in (name, icon, color, preferences)):
                return build_pipe_tool_error_payload(
                    message=(
                        "Provide at least one of: name, icon, color, preferences."
                    ),
                )
            try:
                raw = await client.update_pipe(
                    pipe_id,
                    name=name,
                    icon=icon,
                    color=color,
                    preferences=preferences,
                )
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Update pipe failed.", debug=debug
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
            pipe_id: int,
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
            if not isinstance(pipe_id, int) or pipe_id <= 0:
                return build_delete_pipe_error_payload(
                    message="Invalid 'pipe_id'. Use a positive integer.",
                )

            pipe_name = "Unknown"
            try:
                pipe_response = await client.get_pipe(pipe_id)
                pipe_data = pipe_response.get("pipe") or {}
                pipe_name = pipe_data.get("name") or "Unknown"
            except Exception as exc:
                codes = extract_graphql_error_codes(exc)
                correlation_id = extract_graphql_correlation_id(exc)
                base = map_delete_pipe_error_to_message(
                    pipe_id=pipe_id,
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

            if not confirm:
                return build_delete_pipe_preview_payload(
                    pipe_id=pipe_id,
                    pipe_name=pipe_name,
                    pipe_data=pipe_data,
                )

            try:
                delete_response = await client.delete_pipe(pipe_id)
                success = (delete_response.get("deletePipe") or {}).get("success")
                if success:
                    return build_delete_pipe_success_payload(pipe_id=pipe_id)
                return build_delete_pipe_error_payload(
                    message=map_delete_pipe_error_to_message(
                        pipe_id=pipe_id,
                        pipe_name=pipe_name,
                        codes=[],
                    )
                )
            except Exception as exc:
                codes = extract_graphql_error_codes(exc)
                correlation_id = extract_graphql_correlation_id(exc)
                base = map_delete_pipe_error_to_message(
                    pipe_id=pipe_id,
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
            pipe_template_id: int,
            organization_id: int | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Clone a pipe from a template pipe ID.

            Returns cloned pipe objects (including new IDs) from the API payload.

            Args:
                pipe_template_id: Source pipe ID to use as template.
                organization_id: Optional organization ID for the clone operation.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not isinstance(pipe_template_id, int) or pipe_template_id <= 0:
                return build_pipe_tool_error_payload(
                    message="Invalid 'pipe_template_id'. Use a positive integer.",
                )
            if organization_id is not None and (
                not isinstance(organization_id, int) or organization_id <= 0
            ):
                return build_pipe_tool_error_payload(
                    message="Invalid 'organization_id'. Use a positive integer or omit.",
                )
            try:
                raw = await client.clone_pipe(
                    pipe_template_id,
                    organization_id=organization_id,
                )
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Clone pipe failed.", debug=debug
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
            pipe_id: int,
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
            if not isinstance(pipe_id, int) or pipe_id <= 0:
                return build_pipe_tool_error_payload(
                    message="Invalid 'pipe_id'. Use a positive integer.",
                )
            if not isinstance(name, str) or not name.strip():
                return build_pipe_tool_error_payload(
                    message="Invalid 'name': provide a non-empty string.",
                )
            try:
                raw = await client.create_phase(
                    pipe_id,
                    name.strip(),
                    done=done,
                    index=index,
                    description=description,
                )
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Create phase failed.", debug=debug
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
            phase_id: int,
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
            name (resolved via get_phase_fields).

            Args:
                phase_id: Phase ID to update.
                name: New name, if changing.
                description: New description, if changing.
                done: Whether the phase is a final phase, if changing.
                color: Phase color (API enum), if changing.
                lateness_time: SLA in seconds, if changing.
                can_receive_card_directly_from_draft: If changing.
                only_admin_can_move_to_previous: If changing (deprecated in API).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not isinstance(phase_id, int) or phase_id <= 0:
                return build_pipe_tool_error_payload(
                    message="Invalid 'phase_id'. Use a positive integer.",
                )

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
                )

            if "name" not in update_attrs:
                try:
                    phase_info = await client.get_phase_fields(phase_id)
                except Exception as exc:
                    return handle_pipe_config_tool_graphql_error(
                        exc, "Could not load phase.", debug=debug
                    )
                current = phase_info.get("phase_name")
                if not current:
                    return build_pipe_tool_error_payload(
                        message=f"Phase {phase_id} not found or has no name.",
                    )
                update_attrs["name"] = current

            try:
                raw = await client.update_phase(phase_id, **update_attrs)
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Update phase failed.", debug=debug
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
        async def delete_phase(phase_id: int, debug: bool = False) -> dict[str, Any]:
            """Delete a phase permanently.

            Always confirm impact with the human user before calling this tool.

            Args:
                phase_id: Phase ID to delete.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not isinstance(phase_id, int) or phase_id <= 0:
                return build_pipe_tool_error_payload(
                    message="Invalid 'phase_id'. Use a positive integer.",
                )
            try:
                raw = await client.delete_phase(phase_id)
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Delete phase failed.", debug=debug
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
            phase_id: int,
            label: str,
            field_type: str,
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a custom field on a phase.

            ``field_type`` is passed through to Pipefy (use schema introspection on
            ``CreatePhaseFieldInput`` to list valid types). Optional keys in
            ``extra_input`` are merged into the mutation input (e.g. description,
            required, options).

            **Select / radio / checklist fields:** pass ``options`` inside
            ``extra_input`` (e.g. ``extra_input={"options": ["Alta", "Média",
            "Baixa"]}``). If the API rejects options on creation, create the field
            first and then call ``update_phase_field`` with the ``options`` list.

            Args:
                phase_id: Phase that will receive the field.
                label: Field label shown in the UI.
                field_type: Pipefy field type string (API input field ``type``).
                extra_input: Additional ``CreatePhaseFieldInput`` fields, if any
                    (e.g. description, required, options).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not isinstance(phase_id, int) or phase_id <= 0:
                return build_pipe_tool_error_payload(
                    message="Invalid 'phase_id'. Use a positive integer.",
                )
            if not isinstance(label, str) or not label.strip():
                return build_pipe_tool_error_payload(
                    message="Invalid 'label': provide a non-empty string.",
                )
            if not isinstance(field_type, str) or not field_type.strip():
                return build_pipe_tool_error_payload(
                    message="Invalid 'field_type': provide a non-empty string.",
                )
            merged: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _CREATE_PHASE_FIELD_EXTRA_RESERVED
            }
            try:
                raw = await client.create_phase_field(
                    phase_id,
                    label.strip(),
                    field_type.strip(),
                    **merged,
                )
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Create phase field failed.", debug=debug
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
            field_id: str | int,
            label: str | None = None,
            description: str | None = None,
            required: bool | None = None,
            options: list[Any] | dict[str, Any] | None = None,
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update a phase field.

            Pass only fields to change. Use introspection on `UpdatePhaseFieldInput` for the full list.

            Args:
                field_id: Phase field ID (slug string from create/get_phase_fields, or positive integer).
                label: New label, if changing.
                description: New description, if changing.
                required: Whether the field is required, if changing.
                options: Field options structure (API-specific), if changing.
                extra_input: Additional UpdatePhaseFieldInput fields, if any.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_phase_field_id(field_id):
                return build_pipe_tool_error_payload(
                    message=(
                        "Invalid 'field_id'. Use a non-empty string (field slug) "
                        "or a positive integer."
                    ),
                )
            update_attrs: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _UPDATE_PHASE_FIELD_EXTRA_RESERVED
            }
            if label is not None:
                update_attrs["label"] = label
            if description is not None:
                update_attrs["description"] = description
            if required is not None:
                update_attrs["required"] = required
            if options is not None:
                update_attrs["options"] = options
            if not update_attrs:
                return build_pipe_tool_error_payload(
                    message="Provide at least one attribute to update.",
                )
            fid = field_id.strip() if isinstance(field_id, str) else field_id
            try:
                raw = await client.update_phase_field(fid, **update_attrs)
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Update phase field failed.", debug=debug
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
            field_id: str | int,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a phase field permanently.

            Always confirm impact with the human user before calling this tool.

            Args:
                field_id: Phase field ID to delete (slug string or positive integer).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_phase_field_id(field_id):
                return build_pipe_tool_error_payload(
                    message=(
                        "Invalid 'field_id'. Use a non-empty string (field slug) "
                        "or a positive integer."
                    ),
                )
            fid = field_id.strip() if isinstance(field_id, str) else field_id
            try:
                raw = await client.delete_phase_field(fid)
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Delete phase field failed.", debug=debug
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
            pipe_id: int,
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
            if not isinstance(pipe_id, int) or pipe_id <= 0:
                return build_pipe_tool_error_payload(
                    message="Invalid 'pipe_id'. Use a positive integer.",
                )
            if not isinstance(name, str) or not name.strip():
                return build_pipe_tool_error_payload(
                    message="Invalid 'name': provide a non-empty string.",
                )
            if not isinstance(color, str) or not color.strip():
                return build_pipe_tool_error_payload(
                    message="Invalid 'color': provide a non-empty string.",
                )
            try:
                raw = await client.create_label(
                    pipe_id,
                    name.strip(),
                    color.strip(),
                )
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Create label failed.", debug=debug
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
            label_id: int,
            name: str | None = None,
            color: str | None = None,
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update a pipe label.

            Args:
                label_id: Label ID to update.
                name: New name, if changing.
                color: New color, if changing.
                extra_input: Additional UpdateLabelInput fields, if any.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not isinstance(label_id, int) or label_id <= 0:
                return build_pipe_tool_error_payload(
                    message="Invalid 'label_id'. Use a positive integer.",
                )
            update_attrs: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _UPDATE_LABEL_EXTRA_RESERVED
            }
            if name is not None:
                update_attrs["name"] = name
            if color is not None:
                update_attrs["color"] = color
            if not update_attrs:
                return build_pipe_tool_error_payload(
                    message="Provide at least one attribute to update.",
                )
            try:
                raw = await client.update_label(label_id, **update_attrs)
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Update label failed.", debug=debug
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
        async def delete_label(label_id: int, debug: bool = False) -> dict[str, Any]:
            """Delete a label permanently.

            Always confirm impact with the human user before calling this tool.

            Args:
                label_id: Label ID to delete.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not isinstance(label_id, int) or label_id <= 0:
                return build_pipe_tool_error_payload(
                    message="Invalid 'label_id'. Use a positive integer.",
                )
            try:
                raw = await client.delete_label(label_id)
            except Exception as exc:
                return handle_pipe_config_tool_graphql_error(
                    exc, "Delete label failed.", debug=debug
                )
            return build_pipe_mutation_success_payload(
                label="Label deleted.",
                data=raw,
            )
