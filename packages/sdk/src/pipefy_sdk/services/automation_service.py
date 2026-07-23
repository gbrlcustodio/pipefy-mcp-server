"""GraphQL operations for Pipefy traditional automations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.models.ai_automation import (
    AutomationEventParamsInput,
    CreateAiAutomationInput,
    UpdateAiAutomationInput,
)
from pipefy_sdk.queries.automation_queries import (
    AUTOMATION_SIMULATION_QUERY,
    CREATE_AUTOMATION_MUTATION,
    CREATE_AUTOMATION_SIMULATION_MUTATION,
    DELETE_AUTOMATION_MUTATION,
    GET_AUTOMATION_ACTIONS_QUERY,
    GET_AUTOMATION_EVENT_ATTRIBUTES_QUERY,
    GET_AUTOMATION_EVENTS_QUERY,
    GET_AUTOMATION_QUERY,
    GET_AUTOMATIONS_BY_ORG_QUERY,
    GET_AUTOMATIONS_FOR_ORG_AND_REPO_QUERY,
    GET_PIPE_ORGANIZATION_ID_QUERY,
    UPDATE_AUTOMATION_MUTATION,
)
from pipefy_sdk.services.automation_graphql_types import (
    AutomationActionRow,
    AutomationEventAttributeRow,
    AutomationEventRow,
    AutomationRuleRecord,
    AutomationRuleSummary,
    AutomationSimulationRow,
    CreateAutomationMutationResult,
    DeleteAutomationServiceResult,
    SimulateAutomationServiceResult,
    UpdateAutomationMutationResult,
)
from pipefy_sdk.services.types import AutomationServiceResult

ACTION_ID_GENERATE_WITH_AI = "generate_with_ai"

_AUTOMATION_EVENT_ATTRIBUTE_GRAPHQL_KEYS: tuple[tuple[str, str], ...] = (
    ("automationEventExecutionDatetime", "automation_event_execution_datetime"),
)


def _automation_event_params_for_api(
    params: AutomationEventParamsInput,
) -> dict[str, Any]:
    """Serialize event_params to declared wire names, without unset/``None`` values."""
    return params.model_dump(
        mode="python",
        by_alias=True,
        exclude_unset=True,
        exclude_none=True,
    )


def _ai_params_payload(
    *,
    prompt: str | None,
    field_ids: list[str] | None,
    skills_ids: list[str] | None,
) -> dict[str, Any]:
    """Build the ``aiParams`` body from the fields the caller set (omits ``None``)."""
    payload: dict[str, Any] = {}
    if prompt is not None:
        payload["value"] = prompt
    if field_ids is not None:
        payload["fieldIds"] = field_ids
    if skills_ids is not None:
        payload["skillsIds"] = skills_ids
    return payload


def _extract_automation_id(raw: Mapping[str, Any], mutation_key: str) -> str:
    """Pull ``automation.id`` from a create/update mutation payload, or raise."""
    automation = (raw.get(mutation_key) or {}).get("automation")
    if not automation or "id" not in automation:
        raise ValueError(
            f"Unexpected API payload: automation.id missing from {mutation_key} response"
        )
    return str(automation["id"])


def normalize_automation_event_attributes(
    raw: dict[str, Any] | None,
) -> list[AutomationEventAttributeRow]:
    """Map ``automationEventAttributes`` GraphQL object keys to agent-friendly rows."""
    if not raw:
        return []
    rows: list[AutomationEventAttributeRow] = []
    for graphql_key, attr_id in _AUTOMATION_EVENT_ATTRIBUTE_GRAPHQL_KEYS:
        entry = raw.get(graphql_key)
        if not isinstance(entry, dict):
            continue
        internal_id = entry.get("internalId")
        if not isinstance(internal_id, str):
            internal_id = entry.get("internal_id")
        label = entry.get("label")
        field_type = entry.get("type")
        row: AutomationEventAttributeRow = {
            "id": attr_id,
            "value_token": f"%{{{attr_id}}}",
        }
        if isinstance(internal_id, str):
            row["internal_id"] = internal_id
        if isinstance(label, str):
            row["label"] = label
        if isinstance(field_type, str):
            row["type"] = field_type
        rows.append(row)
    return rows


def _format_automation_error_details(detail_val: Any) -> str:
    """Turn ``error_details`` (``[InternalError!]``-shaped payloads) into one line for :class:`ValueError`."""

    if detail_val is None:
        return ""
    if isinstance(detail_val, str):
        return detail_val
    if isinstance(detail_val, dict):
        messages = detail_val.get("messages")
        if isinstance(messages, list):
            return "; ".join(m for m in messages if isinstance(m, str) and m)
        return str(detail_val)
    if isinstance(detail_val, list):
        parts: list[str] = []
        for item in detail_val:
            if isinstance(item, str) and item:
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            chunks: list[str] = []
            raw_messages = item.get("messages")
            if isinstance(raw_messages, list):
                chunks.extend(m for m in raw_messages if isinstance(m, str) and m)
            single = item.get("message")
            if isinstance(single, str) and single:
                chunks.append(single)
            if not chunks:
                continue
            object_name = item.get("object_name")
            object_key = item.get("object_key")
            body = "; ".join(chunks)
            if object_name and object_key:
                parts.append(f"{object_name} ({object_key}): {body}")
            elif object_name:
                parts.append(f"{object_name}: {body}")
            elif object_key:
                parts.append(f"{object_key}: {body}")
            else:
                parts.append(body)
        return "; ".join(parts)
    return str(detail_val)


def _raise_if_automation_mutation_has_errors(
    mutation_key: str,
    raw: dict[str, Any],
) -> None:
    block = raw.get(mutation_key)
    if not isinstance(block, dict):
        return
    err_val = block.get("error_details")
    if not err_val:
        return
    text = _format_automation_error_details(err_val)
    if text:
        raise ValueError(text)


class AutomationService:
    """Reads and mutations for traditional pipe automations (rules engine)."""

    def __init__(self, *, executor: GraphQLExecutor) -> None:
        self._executor = executor

    async def get_automation(self, automation_id: str) -> AutomationRuleRecord | None:
        """Fetch one automation by ID.

        Args:
            automation_id: Automation rule ID (non-empty string; validate at MCP boundary).

        Returns:
            The automation row, or ``None`` when not found.
        """
        payload = await self._executor.execute_query(
            GET_AUTOMATION_QUERY,
            {"id": str(automation_id)},
        )
        row = payload.get("automation")
        if row is None or not isinstance(row, dict):
            return None
        return cast(AutomationRuleRecord, row)

    async def get_automations(
        self,
        organization_id: str | None = None,
        pipe_id: str | None = None,
    ) -> list[AutomationRuleSummary]:
        """List automations for an organization and/or pipe.

        Pipefy requires ``organizationId`` on ``automations``. When only ``pipe_id`` is set,
        the organization is resolved from the pipe.

        Args:
            organization_id: Organization ID to filter by, if any.
            pipe_id: Pipe (repo) ID to filter by, if any.
        """
        if organization_id is None and pipe_id is None:
            return []

        org_id: str | None = organization_id
        if org_id is None and pipe_id is not None:
            org_row = await self._executor.execute_query(
                GET_PIPE_ORGANIZATION_ID_QUERY,
                {"id": str(pipe_id)},
            )
            pipe = org_row.get("pipe") or {}
            oid = pipe.get("organizationId")
            org_id = str(oid) if oid is not None else None
            if org_id is None:
                return []

        if org_id is None:
            return []

        if pipe_id is None:
            payload = await self._executor.execute_query(
                GET_AUTOMATIONS_BY_ORG_QUERY,
                {"organizationId": str(org_id)},
            )
        else:
            payload = await self._executor.execute_query(
                GET_AUTOMATIONS_FOR_ORG_AND_REPO_QUERY,
                {"organizationId": str(org_id), "repoId": str(pipe_id)},
            )
        conn = payload.get("automations")
        if conn is None:
            return []
        rows = conn.get("nodes")
        if rows is None:
            return []
        return cast(list[AutomationRuleSummary], list(rows))

    async def get_automation_actions(self, pipe_id: str) -> list[AutomationActionRow]:
        """List available automation action types for a pipe.

        Args:
            pipe_id: Pipe ID.
        """
        payload = await self._executor.execute_query(
            GET_AUTOMATION_ACTIONS_QUERY,
            {"repoId": str(pipe_id)},
        )
        rows = payload.get("automationActions")
        if rows is None:
            return []
        return cast(list[AutomationActionRow], list(rows))

    async def get_automation_events(self, pipe_id: str) -> list[AutomationEventRow]:
        """List automation trigger event definitions (Pipefy exposes one global catalog).

        Args:
            pipe_id: Reserved for API compatibility; the GraphQL field takes no repo filter.
        """
        # Pipefy's automationEvents query has no repoId filter as of 2026-03; wire pipe_id when API supports it.
        _ = pipe_id
        payload = await self._executor.execute_query(
            GET_AUTOMATION_EVENTS_QUERY,
            {},
        )
        rows = payload.get("automationEvents")
        if rows is None:
            return []
        return cast(list[AutomationEventRow], list(rows))

    async def get_automation_event_attributes(
        self,
    ) -> list[AutomationEventAttributeRow]:
        """List official automation event attribute tokens for ``field_map.value`` templates."""
        payload = await self._executor.execute_query(
            GET_AUTOMATION_EVENT_ATTRIBUTES_QUERY, {}
        )
        raw = payload.get("automationEventAttributes")
        if raw is None:
            return []
        if not isinstance(raw, dict):
            return []
        return normalize_automation_event_attributes(raw)

    async def create_automation(
        self,
        pipe_id: str,
        name: str,
        trigger_id: str,
        action_id: str,
        *,
        action_repo_id: str | None = None,
        **attrs: Any,
    ) -> CreateAutomationMutationResult:
        """Create a traditional automation (`CreateAutomationInput`).

        Args:
            pipe_id: Source pipe ID for the trigger (maps to ``event_repo_id``).
            name: Rule display name.
            trigger_id: Event ID from `get_automation_events` (API field `event_id`).
            action_id: Action type ID from `get_automation_actions`.
            action_repo_id: Pipe ID where the action executes. Defaults to ``pipe_id``
                (same-pipe automation). For cross-pipe actions like ``create_connected_card``
                or ``move_card_to_pipe``, set this to the **destination** pipe ID.
            **attrs: Additional `CreateAutomationInput` fields (API key names). ``None`` values are omitted.
                When ``active`` is omitted, it defaults to ``True`` (rule created enabled in Pipefy).
        """
        input_obj: dict[str, Any] = {
            "name": name,
            "event_id": trigger_id,
            "action_id": action_id,
            "event_repo_id": pipe_id,
            "action_repo_id": action_repo_id or pipe_id,
        }
        for key, value in attrs.items():
            if value is not None:
                input_obj[key] = value
        if "active" not in input_obj:
            input_obj["active"] = True
        raw = await self._executor.execute_query(
            CREATE_AUTOMATION_MUTATION,
            {"input": input_obj},
        )
        _raise_if_automation_mutation_has_errors("createAutomation", raw)
        return cast(CreateAutomationMutationResult, raw)

    async def create_send_task_automation(
        self,
        pipe_id: str,
        name: str,
        event_id: str,
        task_title: str,
        recipients: str,
        *,
        active: bool = True,
        event_params: dict[str, Any] | None = None,
        condition: dict[str, Any] | None = None,
    ) -> CreateAutomationMutationResult:
        """Create a ``send_a_task`` traditional automation.

        Builds the ``action_params.taskParams`` envelope expected by Pipefy and
        delegates to :meth:`create_automation`. Both MCP and CLI surfaces use
        this method so the payload shape stays in one place.

        Args:
            pipe_id: Pipe ID where the trigger event is evaluated.
            name: Rule display name.
            event_id: Trigger event ID (e.g. ``card_created``).
            task_title: Title of the task sent to recipients.
            recipients: Comma-separated recipient e-mails.
            active: When True (default), the rule is created enabled.
            event_params: Optional trigger filter payload (passed through verbatim).
            condition: Optional condition expressions payload (passed through verbatim).
        """
        extra_input: dict[str, Any] = {
            "action_params": {
                "taskParams": {
                    "title": task_title,
                    "recipients": recipients,
                },
            },
        }
        if event_params is not None:
            extra_input["event_params"] = event_params
        if condition is not None:
            extra_input["condition"] = condition

        return await self.create_automation(
            pipe_id,
            name,
            event_id,
            "send_a_task",
            active=active,
            action_repo_id=None,
            **extra_input,
        )

    async def create_ai_automation(
        self, automation_input: CreateAiAutomationInput
    ) -> AutomationServiceResult:
        """Create a ``generate_with_ai`` automation via the public ``createAutomation``.

        Builds the ``action_params.aiParams`` envelope expected by Pipefy and
        delegates to :meth:`create_automation`. The public ``/graphql`` endpoint
        accepts ``action_id="generate_with_ai"`` under the caller's normal session
        auth, with no internal API or service-account credentials required.

        Args:
            automation_input: Validated create input. ``condition`` is always
                present on the mutation (the model supplies ``DEFAULT_CONDITION``
                when the caller did not set one).

        Raises:
            ValueError: When the API response is missing ``automation.id``.
        """
        event_params = automation_input.event_params
        raw = await self.create_automation(
            automation_input.pipe_id,
            automation_input.name,
            automation_input.event_id,
            ACTION_ID_GENERATE_WITH_AI,
            action_repo_id=automation_input.action_repo_id,
            action_params={
                "aiParams": _ai_params_payload(
                    prompt=automation_input.prompt,
                    field_ids=automation_input.field_ids,
                    skills_ids=automation_input.skills_ids,
                )
            },
            condition=automation_input.condition.to_api_payload(),
            event_params=(
                _automation_event_params_for_api(event_params)
                if event_params is not None
                else None
            ),
        )
        automation_id = _extract_automation_id(raw, "createAutomation")
        return {
            "automation_id": automation_id,
            "message": f"AI Automation created successfully. ID: {automation_id}",
        }

    async def update_ai_automation(
        self, automation_input: UpdateAiAutomationInput
    ) -> AutomationServiceResult:
        """Update a ``generate_with_ai`` automation via the public ``updateAutomation``.

        Only the fields the caller set are patched. Delegates to
        :meth:`update_automation` over the public ``/graphql`` endpoint.

        Args:
            automation_input: Validated update input.

        Raises:
            ValueError: When the API response is missing ``automation.id``.
        """
        ai_params = _ai_params_payload(
            prompt=automation_input.prompt,
            field_ids=automation_input.field_ids,
            skills_ids=automation_input.skills_ids,
        )
        event_params = automation_input.event_params
        condition = automation_input.condition
        # ``update_automation`` drops ``None`` attrs, so unset fields fall away here.
        raw = await self.update_automation(
            automation_input.automation_id,
            name=automation_input.name,
            active=automation_input.active,
            action_params={"aiParams": ai_params} if ai_params else None,
            event_params=(
                _automation_event_params_for_api(event_params)
                if event_params is not None
                else None
            ),
            condition=(condition.to_api_payload() if condition is not None else None),
        )
        automation_id = _extract_automation_id(raw, "updateAutomation")
        return {
            "automation_id": automation_id,
            "message": f"AI Automation updated successfully. ID: {automation_id}",
        }

    async def update_automation(
        self,
        automation_id: str,
        **attrs: Any,
    ) -> UpdateAutomationMutationResult:
        """Update an automation (`UpdateAutomationInput`).

        Args:
            automation_id: Automation rule ID.
            **attrs: Fields to patch (API key names). ``None`` values are omitted.
        """
        input_obj: dict[str, Any] = {"id": automation_id}
        for key, value in attrs.items():
            if value is not None:
                input_obj[key] = value
        raw = await self._executor.execute_query(
            UPDATE_AUTOMATION_MUTATION,
            {"input": input_obj},
        )
        _raise_if_automation_mutation_has_errors("updateAutomation", raw)
        return cast(UpdateAutomationMutationResult, raw)

    async def simulate_automation(
        self,
        *,
        pipe_id: str,
        action_id: str,
        sample_card_id: str,
        event_id: str | None = None,
        event_params: dict[str, Any] | None = None,
        action_params: dict[str, Any] | None = None,
        condition: dict[str, Any] | None = None,
        name: str | None = None,
        extra_input: dict[str, Any] | None = None,
    ) -> SimulateAutomationServiceResult:
        """Dry-run an automation against a real card (``createAutomationSimulation`` + ``automationSimulation``).

        The mutation only returns ``simulationId``; the service loads the full ``AutomationSimulation``
        row (``status``, ``details``, ``simulationResult``) via the companion query.

        Args:
            pipe_id: Source pipe ID — sent as ``event_repo_id`` and ``action_repo_id`` so the API
                can resolve repos (omitting these can yield ``INTERNAL_SERVER_ERROR`` from Pipefy).
                Override via ``extra_input`` when simulating cross-pipe scenarios.
            action_id: Simulation action (e.g. ``generate_with_ai``); forward-compatible string.
            sample_card_id: Card ID the simulation runs against (GraphQL ``sampleCardId``).
            event_id: Optional trigger event id.
            event_params: Optional trigger parameters.
            action_params: Optional action parameters.
            condition: Optional condition payload.
            name: Optional rule name for the simulation input.
            extra_input: Optional extra ``CreateAutomationSimulationInput`` keys merged last.
        """
        input_obj: dict[str, Any] = {
            "action_id": action_id,
            "sampleCardId": sample_card_id,
            "event_repo_id": pipe_id,
            "action_repo_id": pipe_id,
        }
        if event_id is not None:
            input_obj["event_id"] = event_id
        if event_params is not None:
            input_obj["event_params"] = event_params
        if action_params is not None:
            input_obj["action_params"] = action_params
        if condition is not None:
            input_obj["condition"] = condition
        if name is not None:
            input_obj["name"] = name
        for key, value in (extra_input or {}).items():
            if value is not None:
                input_obj[key] = value
        raw_mutation = await self._executor.execute_query(
            CREATE_AUTOMATION_SIMULATION_MUTATION,
            {"input": input_obj},
        )
        block = raw_mutation.get("createAutomationSimulation")
        if not isinstance(block, dict):
            raise ValueError(
                "createAutomationSimulation response was missing or invalid."
            )
        raw_sid = block.get("simulationId")
        if raw_sid is None or (isinstance(raw_sid, str) and not raw_sid.strip()):
            raise ValueError("createAutomationSimulation returned no simulationId.")
        simulation_id = str(raw_sid).strip()
        raw_query = await self._executor.execute_query(
            AUTOMATION_SIMULATION_QUERY,
            {"simulationId": simulation_id},
        )
        row = raw_query.get("automationSimulation")
        if not isinstance(row, dict):
            raise ValueError(
                "automationSimulation query returned no data for the simulationId."
            )
        return SimulateAutomationServiceResult(
            simulation_id=simulation_id,
            automation_simulation=cast(AutomationSimulationRow, row),
        )

    async def delete_automation(
        self, automation_id: str
    ) -> DeleteAutomationServiceResult:
        """Delete an automation (`DeleteAutomationInput`).

        Args:
            automation_id: Automation rule ID.

        Returns:
            ``{"success": bool}`` from the mutation payload.
        """
        payload = await self._executor.execute_query(
            DELETE_AUTOMATION_MUTATION,
            {"input": {"id": automation_id}},
        )
        block = payload.get("deleteAutomation") or {}
        result: DeleteAutomationServiceResult = {
            "success": bool(block.get("success")),
        }
        return result
