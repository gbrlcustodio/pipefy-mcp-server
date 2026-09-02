"""GraphQL mutations for pipe configuration (pipes, phases, fields, labels, conditions)."""

from __future__ import annotations

import asyncio
from typing import Any

from pipefy_infra.coerce import optional_str

from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.graphql_inputs import (
    CreateFieldConditionInput,
    CreatePhaseFieldInput,
    UpdateFieldConditionInput,
    UpdateLabelInput,
    UpdatePhaseFieldInput,
    UpdatePhaseInput,
    UpdatePipeInput,
)
from pipefy_sdk.label_color import normalize_label_color
from pipefy_sdk.queries.pipe_config_queries import (
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
from pipefy_sdk.services.pipe_service import PipeService
from pipefy_sdk.utils import (
    normalize_field_condition_actions,
    normalize_field_condition_payload,
    slug_like_field_token,
)

_PHASE_FIELD_SLUG_RESOLVE_FETCH_FAILED = (
    "Could not load fields for one or more phases while resolving this slug; "
    "pass `uuid` from get_phase_fields or `phase_id` so the lookup does not "
    "depend on every phase."
)


def _normalized_field_condition_input(
    input: CreateFieldConditionInput | UpdateFieldConditionInput,
) -> dict[str, Any]:
    """Render a field-condition input with its two payload shapes corrected.

    The normalizers work on the serialized payload rather than on the model so
    the generated models stay inert mirrors of the schema. Both mutations need
    the same treatment, and the schema types the two inputs identically here.
    """
    payload = input.to_graphql_input()
    if "condition" in payload:
        payload["condition"] = normalize_field_condition_payload(payload["condition"])
    if "actions" in payload:
        payload["actions"] = normalize_field_condition_actions(payload["actions"])
    return payload


class PipeConfigService:
    """GraphQL mutations for pipe configuration (create, update, delete, clone)."""

    def __init__(
        self,
        *,
        executor: GraphQLExecutor,
        pipe_service: PipeService,
    ) -> None:
        self._executor = executor
        self._pipe_service = pipe_service

    async def create_pipe(self, name: str, organization_id: str | int) -> dict:
        """Create a pipe in the organization."""
        variables: dict[str, Any] = {
            "input": {"name": name, "organization_id": str(organization_id)},
        }
        return await self._executor.execute_query(CREATE_PIPE_MUTATION, variables)

    async def update_pipe(self, input: UpdatePipeInput) -> dict:
        """Update a pipe. Fields left unset on the input are not sent."""
        return await self._executor.execute_query(
            UPDATE_PIPE_MUTATION, {"input": input.to_graphql_input()}
        )

    async def delete_pipe(self, pipe_id: str | int) -> dict:
        """Delete a pipe by ID (permanent). Caller must enforce preview/confirm UX."""
        variables: dict[str, Any] = {"input": {"id": str(pipe_id)}}
        return await self._executor.execute_query(DELETE_PIPE_MUTATION, variables)

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
        return await self._executor.execute_query(CLONE_PIPE_MUTATION, variables)

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
        return await self._executor.execute_query(
            CREATE_PHASE_MUTATION, {"input": input_obj}
        )

    async def update_phase(self, input: UpdatePhaseInput) -> dict:
        """Update a phase. ``name`` is required by the API on every update."""
        return await self._executor.execute_query(
            UPDATE_PHASE_MUTATION, {"input": input.to_graphql_input()}
        )

    async def delete_phase(self, phase_id: str | int) -> dict:
        """Delete a phase by ID (permanent)."""
        return await self._executor.execute_query(
            DELETE_PHASE_MUTATION, {"input": {"id": str(phase_id)}}
        )

    async def create_phase_field(self, input: CreatePhaseFieldInput) -> dict:
        """Create a field on a phase.

        ``type`` is the Pipefy field type. It is a soft enum: any value is sent
        and the API validates it, so a field type added server-side works
        without an SDK release.
        """
        return await self._executor.execute_query(
            CREATE_PHASE_FIELD_MUTATION, {"input": input.to_graphql_input()}
        )

    async def update_phase_field(
        self,
        input: UpdatePhaseFieldInput,
        *,
        phase_id: str | int | None = None,
        pipe_id: str | int | None = None,
    ) -> dict:
        """Update a phase field by slug (or numeric/uuid field id) on Pipefy.

        Pipefy's ``UpdatePhaseFieldInput`` takes the field **slug** as ``id`` and
        accepts an optional ``uuid`` to disambiguate when the same slug repeats
        across phases. The numeric ``internal_id`` from ``get_phase_fields`` is
        **not** a valid ``id`` here — use the slug.

        Args:
            input: The mutation input. ``id`` is the slug, uuid, or numeric id,
                and is stripped and sent as a string — the slug lookup needs one,
                and every form of this id is a string in practice.
            phase_id: Narrows a slug lookup to that phase's fields. The mutation
                has no such field, so it is a parameter rather than part of
                ``input``: when ``input.uuid`` is unset and ``id`` looks like a
                slug, the SDK resolves the field's ``uuid`` and fills it in.
            pipe_id: Same, scanning the start form and every phase. Used only
                when ``phase_id`` is absent.
        """
        raw_token = str(input.id).strip()
        resolved_uuid: str | None = None
        if input.uuid is None and slug_like_field_token(raw_token):
            if phase_id is not None:
                resolved_uuid = await self._resolve_phase_field_uuid_with_phase(
                    raw_token, str(phase_id).strip()
                )
            elif pipe_id is not None:
                resolved_uuid = await self._resolve_phase_field_uuid_with_pipe(
                    raw_token, str(pipe_id).strip()
                )
        updates: dict[str, Any] = {"id": raw_token}
        if resolved_uuid is not None:
            updates["uuid"] = resolved_uuid
        payload = input.model_copy(update=updates).to_graphql_input()
        return await self._executor.execute_query(
            UPDATE_PHASE_FIELD_MUTATION, {"input": payload}
        )

    @staticmethod
    def _field_rows_matching_token(
        fields: list[Any], token: str
    ) -> list[dict[str, Any]]:
        """Return field dicts whose ``id`` (slug), ``internal_id``, or ``uuid`` matches ``token``."""
        out: list[dict[str, Any]] = []
        tok = str(token).strip()
        for field in fields:
            if not isinstance(field, dict):
                continue
            fid = optional_str(field.get("id")) or ""
            iid_str = optional_str(field.get("internal_id")) or ""
            uuid_str = optional_str(field.get("uuid")) or ""
            if (
                tok == fid
                or (iid_str and tok == iid_str)
                or (uuid_str and tok == uuid_str)
            ):
                out.append(field)
        return out

    async def _resolve_phase_field_uuid_with_phase(
        self, token: str, phase_id: str
    ) -> str | None:
        """Return the unique field ``uuid`` for ``token`` within ``phase_id`` or ``None``."""
        data = await self._pipe_service.get_phase_fields(phase_id)
        matches = self._field_rows_matching_token(list(data.get("fields") or []), token)
        uuids = {str(f["uuid"]) for f in matches if f.get("uuid")}
        if len(uuids) == 1:
            return next(iter(uuids))
        return None

    async def _resolve_phase_field_uuid_with_pipe(
        self, token: str, pipe_id: str
    ) -> str | None:
        """Return the unique field ``uuid`` for ``token`` across the pipe or ``None``."""
        pipe_row = await self._pipe_service.get_pipe(pipe_id)
        pipe = (pipe_row or {}).get("pipe") or {}
        uuids: set[str] = set()
        for field in pipe.get("start_form_fields") or []:
            if not isinstance(field, dict):
                continue
            if (
                self._field_rows_matching_token([field], token)
                and field.get("uuid") is not None
            ):
                uuids.add(str(field["uuid"]))
        phase_ids = [
            str(p["id"])
            for p in (pipe.get("phases") or [])
            if isinstance(p, dict) and p.get("id") is not None
        ]
        phase_results = await asyncio.gather(
            *(self._pipe_service.get_phase_fields(pid) for pid in phase_ids),
            return_exceptions=True,
        )
        failed_phase_fetches = 0
        for result in phase_results:
            if isinstance(result, BaseException):
                failed_phase_fetches += 1
                continue
            pdata = result or {}
            for field in self._field_rows_matching_token(
                list(pdata.get("fields") or []), token
            ):
                if field.get("uuid") is not None:
                    uuids.add(str(field["uuid"]))
        if failed_phase_fetches and len(uuids) <= 1:
            raise ValueError(_PHASE_FIELD_SLUG_RESOLVE_FETCH_FAILED)
        if len(uuids) == 1:
            return next(iter(uuids))
        if len(uuids) > 1:
            msg = (
                "Multiple phase fields match this slug on the pipe. Pass `uuid` from "
                "get_phase_fields for the specific field, or pass `phase_id` to narrow "
                "the lookup to one phase."
            )
            raise ValueError(msg)
        return None

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
        return await self._executor.execute_query(
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
            color: Label color as hex ``#RGB`` or ``#RRGGBB`` (normalized to ``#RRGGBB``;
                raises ``ValueError`` otherwise).
        """
        input_obj: dict[str, Any] = {
            "pipe_id": str(pipe_id),
            "name": name,
            "color": normalize_label_color(color),
        }
        return await self._executor.execute_query(
            CREATE_LABEL_MUTATION, {"input": input_obj}
        )

    async def update_label(self, input: UpdateLabelInput) -> dict:
        """Update a label.

        The API requires ``name`` and ``color`` on every update, so both are
        required on the input; pass the current value for the one not changing.
        ``color`` is normalized to hex ``#RRGGBB`` (raises ``ValueError`` on
        non-hex input).
        """
        payload = input.to_graphql_input()
        payload["color"] = normalize_label_color(payload["color"])
        return await self._executor.execute_query(
            UPDATE_LABEL_MUTATION, {"input": payload}
        )

    async def delete_label(self, label_id: str | int) -> dict:
        """Delete a label by ID (permanent).

        Args:
            label_id: Label ID to delete.
        """
        return await self._executor.execute_query(
            DELETE_LABEL_MUTATION, {"input": {"id": str(label_id)}}
        )

    async def create_field_condition(self, input: CreateFieldConditionInput) -> dict:
        """Create a field condition (Pipefy ``createFieldConditionInput``).

        ``condition`` and ``actions`` are normalized on the way out; see
        :func:`normalize_field_condition_payload` for the two shapes the
        mutation answers with an opaque 500.
        """
        return await self._executor.execute_query(
            CREATE_FIELD_CONDITION_MUTATION,
            {"input": _normalized_field_condition_input(input)},
        )

    async def update_field_condition(self, input: UpdateFieldConditionInput) -> dict:
        """Update an existing field condition (`UpdateFieldConditionInput`).

        ``condition`` is normalized (persisted ``expression.id`` dropped,
        ``structure_id`` and ``expressions_structure`` entries coerced to
        ``int``) and ``actions`` has ``actionId: "hidden"`` canonicalized to
        ``"hide"``.
        """
        return await self._executor.execute_query(
            UPDATE_FIELD_CONDITION_MUTATION,
            {"input": _normalized_field_condition_input(input)},
        )

    async def delete_field_condition(self, condition_id: str) -> dict:
        """Delete a field condition permanently (`DeleteFieldConditionInput`).

        Args:
            condition_id: Field condition ID.

        Returns:
            Dict with ``success`` bool from ``deleteFieldCondition``.
        """
        response = await self._executor.execute_query(
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
        return await self._executor.execute_query(
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
        return await self._executor.execute_query(
            GET_FIELD_CONDITION_QUERY, {"id": cid}
        )
