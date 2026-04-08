"""GraphQL operations for Pipefy traditional automations."""

from __future__ import annotations

from typing import Any, cast

from pipefy_mcp.services.pipefy.automation_graphql_types import (
    AutomationActionRow,
    AutomationEventRow,
    AutomationRuleRecord,
    AutomationRuleSummary,
    AutomationSimulationRow,
    CreateAutomationMutationResult,
    DeleteAutomationServiceResult,
    SimulateAutomationServiceResult,
    UpdateAutomationMutationResult,
)
from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.automation_queries import (
    AUTOMATION_SIMULATION_QUERY,
    CREATE_AUTOMATION_MUTATION,
    CREATE_AUTOMATION_SIMULATION_MUTATION,
    DELETE_AUTOMATION_MUTATION,
    GET_AUTOMATION_ACTIONS_QUERY,
    GET_AUTOMATION_EVENTS_QUERY,
    GET_AUTOMATION_QUERY,
    GET_AUTOMATIONS_BY_ORG_QUERY,
    GET_AUTOMATIONS_FOR_ORG_AND_REPO_QUERY,
    GET_PIPE_ORGANIZATION_ID_QUERY,
    UPDATE_AUTOMATION_MUTATION,
)


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


class AutomationService(BasePipefyClient):
    """Reads and mutations for traditional pipe automations (rules engine)."""

    async def get_automation(self, automation_id: str) -> AutomationRuleRecord | None:
        """Fetch one automation by ID.

        Args:
            automation_id: Automation rule ID (non-empty string; validate at MCP boundary).

        Returns:
            The automation row, or ``None`` when not found.
        """
        payload = await self.execute_query(
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
            org_row = await self.execute_query(
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
            payload = await self.execute_query(
                GET_AUTOMATIONS_BY_ORG_QUERY,
                {"organizationId": str(org_id)},
            )
        else:
            payload = await self.execute_query(
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
        payload = await self.execute_query(
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
        payload = await self.execute_query(
            GET_AUTOMATION_EVENTS_QUERY,
            {},
        )
        rows = payload.get("automationEvents")
        if rows is None:
            return []
        return cast(list[AutomationEventRow], list(rows))

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
        raw = await self.execute_query(
            CREATE_AUTOMATION_MUTATION,
            {"input": input_obj},
        )
        _raise_if_automation_mutation_has_errors("createAutomation", raw)
        return cast(CreateAutomationMutationResult, raw)

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
        raw = await self.execute_query(
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
        raw_mutation = await self.execute_query(
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
        raw_query = await self.execute_query(
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
        payload = await self.execute_query(
            DELETE_AUTOMATION_MUTATION,
            {"input": {"id": automation_id}},
        )
        block = payload.get("deleteAutomation") or {}
        result: DeleteAutomationServiceResult = {
            "success": bool(block.get("success")),
        }
        return result
