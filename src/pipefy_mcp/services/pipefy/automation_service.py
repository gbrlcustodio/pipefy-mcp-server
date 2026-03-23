"""GraphQL operations for Pipefy traditional automations."""

from __future__ import annotations

from typing import Any, cast

from pipefy_mcp.services.pipefy.automation_graphql_types import (
    AutomationActionRow,
    AutomationEventRow,
    AutomationRuleRecord,
    AutomationRuleSummary,
    CreateAutomationMutationResult,
    DeleteAutomationServiceResult,
    UpdateAutomationMutationResult,
)
from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.automation_queries import (
    CREATE_AUTOMATION_MUTATION,
    DELETE_AUTOMATION_MUTATION,
    GET_AUTOMATION_ACTIONS_QUERY,
    GET_AUTOMATION_EVENTS_QUERY,
    GET_AUTOMATION_QUERY,
    GET_AUTOMATIONS_BY_ORG_QUERY,
    GET_AUTOMATIONS_FOR_ORG_AND_REPO_QUERY,
    GET_PIPE_ORGANIZATION_ID_QUERY,
    UPDATE_AUTOMATION_MUTATION,
)


def _format_automation_mutation_errors(errors: Any) -> str:
    if errors is None:
        return ""
    if isinstance(errors, str):
        return errors
    if isinstance(errors, list):
        parts: list[str] = []
        for item in errors:
            if isinstance(item, str) and item:
                parts.append(item)
            elif isinstance(item, dict):
                msg = item.get("message")
                if isinstance(msg, str) and msg:
                    parts.append(msg)
        return "; ".join(parts)
    return str(errors)


def _raise_if_automation_mutation_has_errors(
    mutation_key: str,
    raw: dict[str, Any],
) -> None:
    block = raw.get(mutation_key)
    if not isinstance(block, dict):
        return
    err_val = block.get("errors")
    if not err_val:
        return
    text = _format_automation_mutation_errors(err_val)
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
            {"id": automation_id},
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
                {"id": pipe_id},
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
                {"organizationId": org_id},
            )
        else:
            payload = await self.execute_query(
                GET_AUTOMATIONS_FOR_ORG_AND_REPO_QUERY,
                {"organizationId": org_id, "repoId": pipe_id},
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
            {"repoId": pipe_id},
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
        **attrs: Any,
    ) -> CreateAutomationMutationResult:
        """Create a traditional automation (`CreateAutomationInput`).

        Args:
            pipe_id: Pipe ID used as event and action repository context.
            name: Rule display name.
            trigger_id: Event ID from `get_automation_events` (API field `event_id`).
            action_id: Action type ID from `get_automation_actions`.
            **attrs: Additional `CreateAutomationInput` fields (API key names). ``None`` values are omitted.
                When ``active`` is omitted, it defaults to ``True`` (rule created enabled in Pipefy).
        """
        input_obj: dict[str, Any] = {
            "name": name,
            "event_id": trigger_id,
            "action_id": action_id,
            "event_repo_id": pipe_id,
            "action_repo_id": pipe_id,
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
