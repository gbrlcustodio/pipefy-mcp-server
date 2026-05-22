"""GraphQL mutations for pipe configuration (pipes, phases, fields, labels, conditions)."""

from __future__ import annotations

import asyncio
from typing import Any

from httpx import Auth

from pipefy_sdk.base_client import BasePipefyClient
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
from pipefy_sdk.settings import PipefySettings
from pipefy_sdk.utils import (
    normalize_field_condition_actions,
    normalize_field_condition_payload,
    slug_like_field_token,
)

_CREATE_FIELD_CONDITION_RESERVED_ATTRS = frozenset({"phaseId"})
_UPDATE_FIELD_CONDITION_RESERVED_ATTRS = frozenset({"id"})

_PHASE_FIELD_SLUG_RESOLVE_FETCH_FAILED = (
    "Could not load fields for one or more phases while resolving this slug; "
    "pass `uuid` from get_phase_fields or `phase_id` so the lookup does not "
    "depend on every phase."
)


class PipeConfigService(BasePipefyClient):
    """GraphQL mutations for pipe configuration (create, update, delete, clone)."""

    def __init__(
        self,
        settings: PipefySettings,
        *,
        auth: Auth,
        pipe_service: PipeService | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)
        self._pipe_service = pipe_service

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
        """Update a phase field by slug (or numeric/uuid field id) on Pipefy.

        Pipefy's ``UpdatePhaseFieldInput`` takes the field **slug** as ``id`` and
        accepts an optional ``uuid`` to disambiguate when the same slug repeats
        across phases. The numeric ``internal_id`` from ``get_phase_fields`` is
        **not** a valid ``id`` here — use the slug.

        Args:
            field_id: Phase field slug (preferred), uuid, or numeric ``id``.
            **attrs: ``UpdatePhaseFieldInput`` fields. Optional ``phase_id`` /
                ``pipe_id`` (stripped before the mutation) trigger a slug-only
                disambiguation: the SDK looks up the field's ``uuid`` and injects
                it into ``attrs["uuid"]`` when the match is unique. ``phase_id``
                scans one phase; ``pipe_id`` scans the start form and every phase.
        """
        attrs = dict(attrs)
        phase_id = attrs.pop("phase_id", None)
        pipe_id = attrs.pop("pipe_id", None)
        uuid_val = attrs.get("uuid")
        raw_token = str(field_id).strip()

        if (
            uuid_val is None
            and self._pipe_service is not None
            and slug_like_field_token(raw_token)
        ):
            resolved_uuid: str | None = None
            if phase_id is not None:
                resolved_uuid = await self._resolve_phase_field_uuid_with_phase(
                    raw_token, str(phase_id).strip()
                )
            elif pipe_id is not None:
                resolved_uuid = await self._resolve_phase_field_uuid_with_pipe(
                    raw_token, str(pipe_id).strip()
                )
            if resolved_uuid is not None:
                attrs["uuid"] = resolved_uuid

        payload: dict[str, Any] = {"id": raw_token}
        for key, value in attrs.items():
            if value is not None:
                payload[key] = value
        return await self.execute_query(UPDATE_PHASE_FIELD_MUTATION, {"input": payload})

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
            fid = str(field.get("id", "")).strip()
            iid = field.get("internal_id")
            iid_str = str(iid).strip() if iid is not None else ""
            uuid_str = str(field.get("uuid") or "").strip()
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
                keys with value ``None`` are omitted. The camelCase ``phaseId`` is
                rejected here to prevent callers from silently overriding the
                positional ``phase_id`` (the snake_case forms ``phase_id``,
                ``condition``, ``actions`` are auto-rejected by Python because they
                collide with the explicit positional parameters).
        """
        reserved = sorted(
            k for k in attrs if k in _CREATE_FIELD_CONDITION_RESERVED_ATTRS
        )
        if reserved:
            raise ValueError(
                "create_field_condition received reserved key(s) via **attrs: "
                f"{', '.join(reserved)}. Pass them as positional arguments instead."
            )
        phase_key = phase_id.strip() if isinstance(phase_id, str) else str(phase_id)
        normalized_condition = normalize_field_condition_payload(condition)
        normalized_actions = normalize_field_condition_actions(actions)
        input_obj: dict[str, Any] = {
            "phaseId": phase_key,
            "condition": normalized_condition,
            "actions": normalized_actions,
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
            **attrs: Fields to set; keys with value ``None`` are omitted. ``id``
                is reserved and must be passed positionally via ``condition_id``.
                When ``condition`` is a dict, the SDK normalizes it
                (drops persisted ``expression.id``, coerces ``structure_id`` /
                ``expressions_structure`` entries to ``int``). When ``actions``
                is a list, ``actionId: "hidden"`` is canonicalized to ``"hide"``.
        """
        reserved = sorted(
            k for k in attrs if k in _UPDATE_FIELD_CONDITION_RESERVED_ATTRS
        )
        if reserved:
            raise ValueError(
                "update_field_condition received reserved key(s) via **attrs: "
                f"{', '.join(reserved)}. 'id' must be passed as condition_id."
            )
        payload: dict[str, Any] = {"id": condition_id}
        for key, value in attrs.items():
            if value is None:
                continue
            if key == "condition" and isinstance(value, dict):
                payload[key] = normalize_field_condition_payload(value)
            elif key == "actions" and isinstance(value, list):
                payload[key] = normalize_field_condition_actions(value)
            else:
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
