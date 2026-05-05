"""GraphQL mutations for pipe configuration (pipes, phases, fields, labels, conditions)."""

from __future__ import annotations

from typing import Any

from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.pipe_config_queries import (
    CLONE_PIPE_MUTATION,
    CREATE_FIELD_CONDITION_MUTATION,
    CREATE_LABEL_MUTATION,
    CREATE_PHASE_FIELD_MUTATION,
    CREATE_PHASE_MUTATION,
    CREATE_PIPE_MUTATION,
    DELETE_FIELD_CONDITION_MUTATION,
    DELETE_LABEL_MUTATION,
    DELETE_PHASE_FIELD_MUTATION,
    DELETE_PHASE_MUTATION,
    DELETE_PIPE_MUTATION,
    GET_FIELD_CONDITION_QUERY,
    GET_FIELD_CONDITIONS_QUERY,
    UPDATE_FIELD_CONDITION_MUTATION,
    UPDATE_LABEL_MUTATION,
    UPDATE_PHASE_FIELD_MUTATION,
    UPDATE_PHASE_MUTATION,
    UPDATE_PIPE_MUTATION,
)
from pipefy_mcp.settings import PipefySettings


class PipeConfigService(BasePipefyClient):
    """GraphQL mutations for pipe configuration (create, update, delete, clone)."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    async def create_pipe(self, name: str, organization_id: str | int) -> dict:
        """Create a pipe in the organization."""
        variables: dict[str, Any] = {
            "input": {"name": name, "organization_id": str(organization_id)},
        }
        return await self.execute_query(CREATE_PIPE_MUTATION, variables)

    async def update_pipe(self, pipe_id: str | int, **attrs: Any) -> dict:
        """Update a pipe by ID. Pass only Pipefy `UpdatePipeInput` fields (e.g. name, icon, color, preferences)."""
        payload: dict[str, Any] = {"id": str(pipe_id)}
        for key, value in attrs.items():
            if value is not None:
                payload[key] = value
        variables = {"input": payload}
        return await self.execute_query(UPDATE_PIPE_MUTATION, variables)

    async def delete_pipe(self, pipe_id: str | int) -> dict:
        """Delete a pipe by ID (permanent). Caller must enforce preview/confirm UX."""
        variables: dict[str, Any] = {"input": {"id": str(pipe_id)}}
        return await self.execute_query(DELETE_PIPE_MUTATION, variables)

    async def clone_pipe(
        self,
        pipe_template_id: str | int,
        organization_id: str | int | None = None,
    ) -> dict:
        """Clone pipe(s) from template ID(s). Optionally scopes clone to an organization."""
        input_obj: dict[str, Any] = {"pipe_template_ids": [str(pipe_template_id)]}
        if organization_id is not None:
            input_obj["organization_id"] = str(organization_id)
        variables = {"input": input_obj}
        return await self.execute_query(CLONE_PIPE_MUTATION, variables)

    async def create_phase(
        self,
        pipe_id: str | int,
        name: str,
        done: bool = False,
        index: float | int | None = None,
        description: str | None = None,
    ) -> dict:
        """Create a phase in a pipe."""
        input_obj: dict[str, Any] = {
            "pipe_id": str(pipe_id),
            "name": name,
            "done": done,
        }
        if index is not None:
            input_obj["index"] = float(index)
        if description is not None:
            input_obj["description"] = description
        return await self.execute_query(CREATE_PHASE_MUTATION, {"input": input_obj})

    async def update_phase(self, phase_id: str | int, **attrs: Any) -> dict:
        """Update a phase by ID. Pass only Pipefy `UpdatePhaseInput` fields (e.g. name, description, done)."""
        payload: dict[str, Any] = {"id": str(phase_id)}
        for key, value in attrs.items():
            if value is not None:
                payload[key] = value
        return await self.execute_query(UPDATE_PHASE_MUTATION, {"input": payload})

    async def delete_phase(self, phase_id: str | int) -> dict:
        """Delete a phase by ID (permanent)."""
        return await self.execute_query(
            DELETE_PHASE_MUTATION, {"input": {"id": str(phase_id)}}
        )

    async def create_phase_field(
        self,
        phase_id: str | int,
        label: str,
        field_type: str,
        **attrs: Any,
    ) -> dict:
        """Create a field on a phase.

        Args:
            phase_id: Phase that will receive the field.
            label: Field label shown in the UI.
            field_type: Pipefy field type string (maps to `type` on `CreatePhaseFieldInput`; not validated here).
            **attrs: Additional `CreatePhaseFieldInput` fields (e.g. description, required), when not None.
        """
        input_obj: dict[str, Any] = {
            "phase_id": str(phase_id),
            "label": label,
            "type": field_type,
        }
        for key, value in attrs.items():
            if value is not None:
                input_obj[key] = value
        return await self.execute_query(
            CREATE_PHASE_FIELD_MUTATION, {"input": input_obj}
        )

    async def update_phase_field(self, field_id: str | int, **attrs: Any) -> dict:
        """Update a phase field by ID.

        Args:
            field_id: Phase field ID (Pipefy may return string slugs from create; integers still supported).
            **attrs: `UpdatePhaseFieldInput` fields to set (omit or pass None to skip).
        """
        payload: dict[str, Any] = {"id": str(field_id)}
        for key, value in attrs.items():
            if value is not None:
                payload[key] = value
        return await self.execute_query(UPDATE_PHASE_FIELD_MUTATION, {"input": payload})

    async def delete_phase_field(
        self,
        field_id: str | int,
        *,
        pipe_uuid: str | None = None,
    ) -> dict:
        """Delete a phase field by ID (permanent).

        Args:
            field_id: Phase field slug or uuid to delete.
            pipe_uuid: Optional pipe UUID for disambiguation when the slug exists on multiple phases.
        """
        input_obj: dict[str, Any] = {"id": str(field_id)}
        if pipe_uuid is not None:
            input_obj["pipeUuid"] = pipe_uuid
        return await self.execute_query(
            DELETE_PHASE_FIELD_MUTATION,
            {"input": input_obj},
        )

    async def create_label(
        self,
        pipe_id: str | int,
        name: str,
        color: str,
    ) -> dict:
        """Create a label on a pipe.

        Args:
            pipe_id: Pipe that will receive the label.
            name: Label name.
            color: Label color (per API).
        """
        input_obj: dict[str, Any] = {
            "pipe_id": str(pipe_id),
            "name": name,
            "color": color,
        }
        return await self.execute_query(CREATE_LABEL_MUTATION, {"input": input_obj})

    async def update_label(self, label_id: str | int, **attrs: Any) -> dict:
        """Update a label by ID.

        Args:
            label_id: Label ID.
            **attrs: `UpdateLabelInput` fields to set (omit or pass None to skip).
        """
        payload: dict[str, Any] = {"id": str(label_id)}
        for key, value in attrs.items():
            if value is not None:
                payload[key] = value
        return await self.execute_query(UPDATE_LABEL_MUTATION, {"input": payload})

    async def delete_label(self, label_id: str | int) -> dict:
        """Delete a label by ID (permanent).

        Args:
            label_id: Label ID to delete.
        """
        return await self.execute_query(
            DELETE_LABEL_MUTATION, {"input": {"id": str(label_id)}}
        )

    async def create_field_condition(
        self,
        phase_id: str | int,
        condition: dict[str, Any],
        actions: list[dict[str, Any]],
        **attrs: Any,
    ) -> dict:
        """Create a field condition (Pipefy ``createFieldConditionInput``).

        Args:
            phase_id: Phase ID (sent as ``phaseId`` on the mutation input).
            condition: ``ConditionInput`` (e.g. ``expressions``, ``expressions_structure``).
            actions: Non-empty list of ``FieldConditionActionInput`` dicts (use ``phaseFieldId``).
            **attrs: Optional fields such as ``name``, ``index``, ``clientMutationId``;
                keys with value ``None`` are omitted.
        """
        phase_key = phase_id.strip() if isinstance(phase_id, str) else str(phase_id)
        input_obj: dict[str, Any] = {
            "phaseId": phase_key,
            "condition": condition,
            "actions": actions,
        }
        for key, value in attrs.items():
            if value is not None:
                input_obj[key] = value
        return await self.execute_query(
            CREATE_FIELD_CONDITION_MUTATION, {"input": input_obj}
        )

    async def update_field_condition(
        self,
        condition_id: str,
        **attrs: Any,
    ) -> dict:
        """Update an existing field condition (`UpdateFieldConditionInput`).

        Args:
            condition_id: Field condition ID.
            **attrs: Fields to set; keys with value ``None`` are omitted.
        """
        payload: dict[str, Any] = {"id": condition_id}
        for key, value in attrs.items():
            if value is not None:
                payload[key] = value
        return await self.execute_query(
            UPDATE_FIELD_CONDITION_MUTATION, {"input": payload}
        )

    async def delete_field_condition(self, condition_id: str) -> dict:
        """Delete a field condition permanently (`DeleteFieldConditionInput`).

        Args:
            condition_id: Field condition ID.

        Returns:
            Dict with ``success`` bool from ``deleteFieldCondition``.
        """
        response = await self.execute_query(
            DELETE_FIELD_CONDITION_MUTATION,
            {"input": {"id": condition_id}},
        )
        payload = response.get("deleteFieldCondition", {})
        return {"success": bool(payload.get("success"))}

    async def get_field_conditions(self, phase_id: str | int) -> dict:
        """Load field conditions for a phase (``phase.fieldConditions``).

        Args:
            phase_id: Phase ID passed as GraphQL variable ``phaseId``.
        """
        phase_key = phase_id.strip() if isinstance(phase_id, str) else str(phase_id)
        return await self.execute_query(
            GET_FIELD_CONDITIONS_QUERY,
            {"phaseId": phase_key},
        )

    async def get_field_condition(self, condition_id: str | int) -> dict:
        """Load a single field condition by ID.

        Args:
            condition_id: Field condition ID passed as GraphQL variable ``id``.
        """
        cid = (
            condition_id.strip() if isinstance(condition_id, str) else str(condition_id)
        )
        return await self.execute_query(GET_FIELD_CONDITION_QUERY, {"id": cid})
