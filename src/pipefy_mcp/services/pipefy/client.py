from __future__ import annotations

from typing import Any

from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.ai_agent_service import AiAgentService
from pipefy_mcp.services.pipefy.automation_graphql_types import (
    AutomationActionRow,
    AutomationEventRow,
    AutomationRuleRecord,
    AutomationRuleSummary,
    CreateAutomationMutationResult,
    DeleteAutomationServiceResult,
    UpdateAutomationMutationResult,
)
from pipefy_mcp.services.pipefy.automation_service import AutomationService
from pipefy_mcp.services.pipefy.card_service import CardService
from pipefy_mcp.services.pipefy.pipe_config_service import PipeConfigService
from pipefy_mcp.services.pipefy.pipe_service import PipeService
from pipefy_mcp.services.pipefy.relation_service import RelationService
from pipefy_mcp.services.pipefy.schema_introspection_service import (
    SchemaIntrospectionService,
)
from pipefy_mcp.services.pipefy.table_service import TableService
from pipefy_mcp.services.pipefy.types import AiAgentGraphPayload, CardSearch
from pipefy_mcp.settings import PipefySettings


class PipefyClient:
    """Facade client for Pipefy API operations (pure delegation)."""

    def __init__(self, settings: PipefySettings):
        auth = OAuth2ClientCredentials(
            token_url=settings.oauth_url,
            client_id=settings.oauth_client,
            client_secret=settings.oauth_secret,
        )
        self._pipe_service = PipeService(settings=settings, auth=auth)
        self._card_service = CardService(settings=settings, auth=auth)
        self._pipe_config_service = PipeConfigService(settings=settings, auth=auth)
        self._table_service = TableService(settings=settings, auth=auth)
        self._relation_service = RelationService(settings=settings, auth=auth)
        self._automation_service = AutomationService(settings=settings, auth=auth)
        self._ai_agent_service = AiAgentService(settings=settings, auth=auth)
        self._introspection_service = SchemaIntrospectionService(
            settings=settings, auth=auth
        )

    async def get_pipe(self, pipe_id: int) -> dict:
        """Get a pipe by ID, including phases, labels, and start form fields."""
        return await self._pipe_service.get_pipe(pipe_id)

    async def create_pipe(self, name: str, organization_id: int) -> dict:
        """Create a new pipe in the organization."""
        return await self._pipe_config_service.create_pipe(name, organization_id)

    async def update_pipe(self, pipe_id: int, **attrs: Any) -> dict:
        """Update pipe attributes (see Pipefy `UpdatePipeInput`)."""
        return await self._pipe_config_service.update_pipe(pipe_id, **attrs)

    async def delete_pipe(self, pipe_id: int) -> dict:
        """Delete a pipe by ID (permanent)."""
        return await self._pipe_config_service.delete_pipe(pipe_id)

    async def clone_pipe(
        self,
        pipe_template_id: int,
        organization_id: int | None = None,
    ) -> dict:
        """Clone a pipe from a template pipe ID."""
        return await self._pipe_config_service.clone_pipe(
            pipe_template_id,
            organization_id=organization_id,
        )

    async def create_phase(
        self,
        pipe_id: int,
        name: str,
        done: bool = False,
        index: float | int | None = None,
        description: str | None = None,
    ) -> dict:
        """Create a phase in a pipe."""
        return await self._pipe_config_service.create_phase(
            pipe_id,
            name,
            done=done,
            index=index,
            description=description,
        )

    async def update_phase(self, phase_id: int, **attrs: Any) -> dict:
        """Update phase attributes (see Pipefy `UpdatePhaseInput`)."""
        return await self._pipe_config_service.update_phase(phase_id, **attrs)

    async def delete_phase(self, phase_id: int) -> dict:
        """Delete a phase by ID (permanent)."""
        return await self._pipe_config_service.delete_phase(phase_id)

    async def create_phase_field(
        self,
        phase_id: int,
        label: str,
        field_type: str,
        **attrs: Any,
    ) -> dict:
        """Create a field on a phase (`field_type` is passed through to the API)."""
        return await self._pipe_config_service.create_phase_field(
            phase_id,
            label,
            field_type,
            **attrs,
        )

    async def update_phase_field(self, field_id: str | int, **attrs: Any) -> dict:
        """Update a phase field (see Pipefy `UpdatePhaseFieldInput`)."""
        return await self._pipe_config_service.update_phase_field(field_id, **attrs)

    async def delete_phase_field(self, field_id: str | int) -> dict:
        """Delete a phase field by ID (permanent)."""
        return await self._pipe_config_service.delete_phase_field(field_id)

    async def create_label(self, pipe_id: int, name: str, color: str) -> dict:
        """Create a label on a pipe."""
        return await self._pipe_config_service.create_label(pipe_id, name, color)

    async def update_label(self, label_id: int, **attrs: Any) -> dict:
        """Update a label (see Pipefy `UpdateLabelInput`)."""
        return await self._pipe_config_service.update_label(label_id, **attrs)

    async def delete_label(self, label_id: int) -> dict:
        """Delete a label by ID (permanent)."""
        return await self._pipe_config_service.delete_label(label_id)

    async def create_field_condition(
        self,
        phase_id: str | int,
        condition: dict[str, Any],
        actions: list[dict[str, Any]],
        **attrs: Any,
    ) -> dict:
        """Create a field condition (``createFieldCondition`` / ``createFieldConditionInput``)."""
        return await self._pipe_config_service.create_field_condition(
            phase_id, condition, actions, **attrs
        )

    async def update_field_condition(self, condition_id: str, **attrs: Any) -> dict:
        """Update an existing field condition."""
        return await self._pipe_config_service.update_field_condition(
            condition_id, **attrs
        )

    async def delete_field_condition(self, condition_id: str) -> dict:
        """Delete a field condition by ID (permanent)."""
        return await self._pipe_config_service.delete_field_condition(condition_id)

    async def get_table(self, table_id: str | int) -> dict:
        """Get a database table by ID (metadata, fields, authorization)."""
        return await self._table_service.get_table(table_id)

    async def get_tables(self, table_ids: list[str | int]) -> dict:
        """Get multiple database tables by ID."""
        return await self._table_service.get_tables(table_ids)

    async def get_table_records(
        self,
        table_id: str | int,
        first: int = 50,
        after: str | None = None,
    ) -> dict:
        """List table records with cursor pagination (see `pageInfo` in the response)."""
        return await self._table_service.get_table_records(
            table_id, first=first, after=after
        )

    async def get_table_record(self, record_id: str | int) -> dict:
        """Get a single table record by ID."""
        return await self._table_service.get_table_record(record_id)

    async def find_records(
        self,
        table_id: str | int,
        field_id: str,
        field_value: str,
        first: int | None = None,
        after: str | None = None,
    ) -> dict:
        """Find table records where the given field equals the given value."""
        return await self._table_service.find_records(
            table_id,
            field_id,
            field_value,
            first=first,
            after=after,
        )

    async def create_table(self, name: str, organization_id: int, **attrs: Any) -> dict:
        """Create a database table (see Pipefy `CreateTableInput`)."""
        return await self._table_service.create_table(name, organization_id, **attrs)

    async def update_table(self, table_id: str | int, **attrs: Any) -> dict:
        """Update a database table (see Pipefy `UpdateTableInput`)."""
        return await self._table_service.update_table(table_id, **attrs)

    async def delete_table(self, table_id: str | int) -> dict:
        """Delete a database table by ID (permanent)."""
        return await self._table_service.delete_table(table_id)

    async def create_table_record(
        self,
        table_id: str | int,
        fields: dict[str, Any] | list[dict[str, Any]],
        **attrs: Any,
    ) -> dict:
        """Create a record in a database table."""
        return await self._table_service.create_table_record(table_id, fields, **attrs)

    async def update_table_record(
        self, record_id: str | int, fields: dict[str, Any]
    ) -> dict:
        """Update a table record (title, due_date, status — see `UpdateTableRecordInput`)."""
        return await self._table_service.update_table_record(record_id, fields)

    async def delete_table_record(self, record_id: str | int) -> dict:
        """Delete a table record by ID (permanent)."""
        return await self._table_service.delete_table_record(record_id)

    async def set_table_record_field_value(
        self,
        record_id: str | int,
        field_id: str | int,
        value: Any,
    ) -> dict:
        """Update a single custom field on a table record."""
        return await self._table_service.set_table_record_field_value(
            record_id, field_id, value
        )

    async def create_table_field(
        self,
        table_id: str | int,
        label: str,
        field_type: str,
        **attrs: Any,
    ) -> dict:
        """Create a field on a database table (see Pipefy `CreateTableFieldInput`)."""
        return await self._table_service.create_table_field(
            table_id, label, field_type, **attrs
        )

    async def update_table_field(
        self, field_id: str | int, table_id: str | int | None = None, **attrs: Any
    ) -> dict:
        """Update a database table field (see Pipefy `UpdateTableFieldInput`).

        Args:
            field_id: Table field ID to update.
            table_id: Table ID containing this field (required by API).
            **attrs: Other UpdateTableFieldInput attributes.
        """
        return await self._table_service.update_table_field(
            field_id, table_id=table_id, **attrs
        )

    async def delete_table_field(self, field_id: str | int) -> dict:
        """Delete a database table field by ID (permanent)."""
        return await self._table_service.delete_table_field(field_id)

    async def get_pipe_relations(self, pipe_id: str | int) -> dict:
        """Get parent and child pipe relations for a pipe."""
        return await self._relation_service.get_pipe_relations(pipe_id)

    async def get_table_relations(self, relation_ids: list[str | int]) -> dict:
        """Batch-fetch table relations by table-relation ID (see Pipefy `table_relations`)."""
        return await self._relation_service.get_table_relations(relation_ids)

    async def create_pipe_relation(
        self,
        parent_id: str | int,
        child_id: str | int,
        name: str,
        extra_input: dict[str, Any] | None = None,
    ) -> dict:
        """Create a parent-child pipe relation (optional ``extra_input`` uses CreatePipeRelationInput camelCase keys)."""
        return await self._relation_service.create_pipe_relation(
            parent_id, child_id, name, **(extra_input or {})
        )

    async def update_pipe_relation(
        self,
        relation_id: str | int,
        name: str,
        extra_input: dict[str, Any] | None = None,
    ) -> dict:
        """Update a pipe relation (optional ``extra_input`` uses UpdatePipeRelationInput camelCase keys)."""
        return await self._relation_service.update_pipe_relation(
            relation_id, name, **(extra_input or {})
        )

    async def delete_pipe_relation(self, relation_id: str | int) -> dict:
        """Delete a pipe relation by ID (permanent)."""
        return await self._relation_service.delete_pipe_relation(relation_id)

    async def create_card_relation(
        self,
        parent_id: str | int,
        child_id: str | int,
        source_id: str | int,
        extra_input: dict[str, Any] | None = None,
    ) -> dict:
        """Connect a child card to a parent card via a pipe relation (optional ``extra_input`` for CreateCardRelationInput)."""
        return await self._relation_service.create_card_relation(
            parent_id, child_id, source_id, **(extra_input or {})
        )

    async def get_automation(self, automation_id: str) -> AutomationRuleRecord:
        """Get a traditional automation rule by ID (trigger, actions, status)."""
        return await self._automation_service.get_automation(automation_id)

    async def get_automations(
        self,
        organization_id: str | None = None,
        pipe_id: str | None = None,
    ) -> list[AutomationRuleSummary]:
        """List traditional automation rules for an organization and/or pipe."""
        return await self._automation_service.get_automations(
            organization_id=organization_id,
            pipe_id=pipe_id,
        )

    async def get_automation_actions(self, pipe_id: str) -> list[AutomationActionRow]:
        """List available automation action types for a pipe (for building create/update payloads)."""
        return await self._automation_service.get_automation_actions(pipe_id)

    async def get_automation_events(self, pipe_id: str) -> list[AutomationEventRow]:
        """List available automation trigger events for a pipe (for building create/update payloads)."""
        return await self._automation_service.get_automation_events(pipe_id)

    async def create_automation(
        self,
        pipe_id: str,
        name: str,
        trigger_id: str,
        action_id: str,
        *,
        active: bool = True,
        extra_input: dict[str, Any] | None = None,
    ) -> CreateAutomationMutationResult:
        """Create a traditional automation rule (optional ``extra_input`` uses CreateAutomationInput field names).

        Args:
            pipe_id: Pipe ID.
            name: Rule name.
            trigger_id: Event ID.
            action_id: Action ID.
            active: When True (default), create the rule enabled. Set False to start disabled, or use ``extra_input`` / ``update_automation`` later.
            extra_input: Extra ``CreateAutomationInput`` keys; ``active`` here overrides the ``active`` argument when both are set.
        """
        merged: dict[str, Any] = dict(extra_input or {})
        if "active" not in merged:
            merged["active"] = active
        return await self._automation_service.create_automation(
            pipe_id,
            name,
            trigger_id,
            action_id,
            **merged,
        )

    async def update_automation(
        self,
        automation_id: str,
        extra_input: dict[str, Any] | None = None,
    ) -> UpdateAutomationMutationResult:
        """Update a traditional automation (optional ``extra_input`` uses UpdateAutomationInput field names)."""
        return await self._automation_service.update_automation(
            automation_id, **(extra_input or {})
        )

    async def delete_automation(
        self, automation_id: str
    ) -> DeleteAutomationServiceResult:
        """Delete a traditional automation rule by ID (permanent)."""
        return await self._automation_service.delete_automation(automation_id)

    async def get_ai_agent(self, agent_uuid: str) -> AiAgentGraphPayload:
        """Get an AI Agent by UUID (name, instruction, behaviors)."""
        return await self._ai_agent_service.get_agent(agent_uuid)

    async def get_ai_agents(self, repo_uuid: str) -> list[AiAgentGraphPayload]:
        """List AI Agents for a pipe UUID (`repoUuid` in the API)."""
        return await self._ai_agent_service.get_agents(repo_uuid)

    async def delete_ai_agent(self, agent_uuid: str) -> dict:
        """Delete an AI Agent by UUID (permanent)."""
        return await self._ai_agent_service.delete_agent(agent_uuid)

    async def get_pipe_members(self, pipe_id: int) -> dict:
        """Get the members of a pipe."""
        return await self._pipe_service.get_pipe_members(pipe_id)

    async def create_card(
        self, pipe_id: int, fields: dict[str, Any] | list[dict[str, Any]]
    ) -> dict:
        """Create a card in the specified pipe with the given fields."""
        return await self._card_service.create_card(pipe_id, fields)

    async def add_card_comment(self, card_id: int, text: str) -> dict:
        """Add a text comment to a card by its ID."""
        return await self._card_service.create_comment(card_id, text)

    async def update_comment(self, comment_id: int, text: str) -> dict:
        """Update an existing comment by its ID."""
        return await self._card_service.update_comment(comment_id, text)

    async def delete_comment(self, comment_id: int) -> dict:
        """Delete a comment by its ID."""
        return await self._card_service.delete_comment(comment_id)

    async def get_card(self, card_id: int, include_fields: bool = False) -> dict:
        """Get a card by its ID.

        Args:
            card_id: The ID of the card.
            include_fields: If True, include the card's custom fields (name, value) in the response.
        """
        return await self._card_service.get_card(card_id, include_fields=include_fields)

    async def get_cards(
        self,
        pipe_id: int,
        search: CardSearch | None = None,
        include_fields: bool = False,
    ) -> dict:
        """Get all cards in the pipe with optional search filters.

        Args:
            pipe_id: The ID of the pipe.
            search: Optional search filters.
            include_fields: If True, include each card's custom fields (name, value) in the response.
        """
        return await self._card_service.get_cards(
            pipe_id, search, include_fields=include_fields
        )

    async def find_cards(
        self,
        pipe_id: int,
        field_id: str,
        field_value: str,
        include_fields: bool = False,
    ) -> dict:
        """Find cards in the pipe where the given field equals the given value.

        Args:
            pipe_id: The ID of the pipe to search in.
            field_id: Pipefy field identifier (e.g. from get_start_form_fields or get_phase_fields).
            field_value: Value to match for that field (string; use format expected by field type).
            include_fields: If True, include each card's custom fields (name, value) in the response.
        """
        return await self._card_service.find_cards(
            pipe_id, field_id, field_value, include_fields=include_fields
        )

    async def move_card_to_phase(self, card_id: int, destination_phase_id: int) -> dict:
        """Move a card to a specific phase."""
        return await self._card_service.move_card_to_phase(
            card_id, destination_phase_id
        )

    async def update_card_field(
        self, card_id: int, field_id: str, new_value: Any
    ) -> dict:
        """Update a single field of a card."""
        return await self._card_service.update_card_field(card_id, field_id, new_value)

    async def update_card(
        self,
        card_id: int,
        title: str | None = None,
        assignee_ids: list[int] | None = None,
        label_ids: list[int] | None = None,
        due_date: str | None = None,
        field_updates: list[dict] | None = None,
    ) -> dict:
        """Update a card's attributes or fields with intelligent mutation selection."""
        return await self._card_service.update_card(
            card_id=card_id,
            title=title,
            assignee_ids=assignee_ids,
            label_ids=label_ids,
            due_date=due_date,
            field_updates=field_updates,
        )

    async def delete_card(self, card_id: int) -> dict:
        """Delete a card by its ID."""
        return await self._card_service.delete_card(card_id)

    async def get_start_form_fields(
        self, pipe_id: int, required_only: bool = False
    ) -> dict:
        """Get the start form fields of a pipe."""
        return await self._pipe_service.get_start_form_fields(pipe_id, required_only)

    async def search_pipes(self, pipe_name: str | None = None) -> dict:
        """Search for pipes across all organizations"""
        return await self._pipe_service.search_pipes(pipe_name)

    async def get_phase_fields(
        self, phase_id: int, required_only: bool = False
    ) -> dict:
        """Get the fields available in a specific phase."""
        return await self._pipe_service.get_phase_fields(phase_id, required_only)

    async def introspect_type(self, type_name: str) -> dict[str, Any]:
        """Introspect a GraphQL type by name (fields, inputFields, or enumValues).

        Args:
            type_name: Schema type name (e.g. Card, CreateCardInput).
        """
        return await self._introspection_service.introspect_type(type_name)

    async def introspect_mutation(self, mutation_name: str) -> dict[str, Any]:
        """Introspect a root mutation field (arguments and return type).

        Args:
            mutation_name: Mutation field name as exposed on the Mutation type.
        """
        return await self._introspection_service.introspect_mutation(mutation_name)

    async def search_schema(self, keyword: str) -> dict[str, Any]:
        """Search schema types by keyword (name or description).

        Args:
            keyword: Case-insensitive substring to match.
        """
        return await self._introspection_service.search_schema(keyword)

    async def execute_graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute arbitrary GraphQL after syntax validation (fallback / advanced use).

        Args:
            query: GraphQL document string.
            variables: Optional variables for the operation.
        """
        return await self._introspection_service.execute_graphql(query, variables)
