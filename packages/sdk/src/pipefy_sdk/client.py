"""Facade that wires Pipefy domain services for MCP tools (delegation only)."""

from __future__ import annotations

from typing import Any

from httpx import Auth

from pipefy_sdk.ai_pipe_validation import resolve_and_populate_field_refs
from pipefy_sdk.attachment_upload import (
    AttachmentUploadResult,
    upload_attachment_to_card_field,
    upload_attachment_to_table_record_field,
)
from pipefy_sdk.automation_preflight import (
    validate_traditional_automation_move_transition,
)
from pipefy_sdk.models.ai_agent import (
    BehaviorInput,
    CreateAiAgentInput,
    UpdateAiAgentInput,
)
from pipefy_sdk.models.ai_automation import (
    CreateAiAutomationInput,
    UpdateAiAutomationInput,
)
from pipefy_sdk.queries.card_queries import (
    INTERNAL_DELETE_CARD_RELATION_MUTATION,
)
from pipefy_sdk.services.ai_agent_service import AiAgentService
from pipefy_sdk.services.ai_automation_service import AiAutomationService
from pipefy_sdk.services.attachment_service import AttachmentService
from pipefy_sdk.services.automation_graphql_types import (
    AutomationActionRow,
    AutomationEventRow,
    AutomationRuleRecord,
    AutomationRuleSummary,
    CreateAutomationMutationResult,
    DeleteAutomationServiceResult,
    SimulateAutomationServiceResult,
    UpdateAutomationMutationResult,
)
from pipefy_sdk.services.automation_service import AutomationService
from pipefy_sdk.services.card_service import CardService
from pipefy_sdk.services.internal_api_client import InternalApiClient
from pipefy_sdk.services.member_service import MemberService
from pipefy_sdk.services.observability_service import ObservabilityService
from pipefy_sdk.services.organization_service import OrganizationService
from pipefy_sdk.services.pipe_config_service import PipeConfigService
from pipefy_sdk.services.pipe_service import (
    SEARCH_PIPES_MAX_PER_ORG_CAP,
    PipeService,
)
from pipefy_sdk.services.portal_service import PortalService
from pipefy_sdk.services.relation_service import RelationService
from pipefy_sdk.services.report_service import ReportService
from pipefy_sdk.services.schema_introspection_service import (
    SchemaIntrospectionService,
)
from pipefy_sdk.services.table_service import (
    SEARCH_TABLES_FIRST_DEFAULT,
    TableService,
)
from pipefy_sdk.services.types import (
    AgentServiceResult,
    AiAgentGraphPayload,
    AutomationServiceResult,
    CardSearch,
    MePayload,
    ToggleAgentStatusResult,
)
from pipefy_sdk.services.user_service import UserService
from pipefy_sdk.services.webhook_service import WebhookService
from pipefy_sdk.settings import PipefySettings


class PipefyClient:
    """Facade client for Pipefy API operations (pure delegation)."""

    def __init__(
        self,
        settings: PipefySettings,
        *,
        auth: Auth,
    ) -> None:
        """Build a facade wired with a pre-constructed ``httpx.Auth``.

        Args:
            settings: Pipefy endpoint configuration.
            auth: ``httpx.Auth`` that supplies the credentials for every GraphQL
                call (construct via ``pipefy_auth.resolve`` or one of the bearer
                adapters from ``pipefy_auth``).
        """
        self._pipe_service = PipeService(settings=settings, auth=auth)
        self._card_service = CardService(settings=settings, auth=auth)
        self._pipe_config_service = PipeConfigService(
            settings=settings, auth=auth, pipe_service=self._pipe_service
        )
        self._table_service = TableService(settings=settings, auth=auth)
        self._relation_service = RelationService(settings=settings, auth=auth)
        self._member_service = MemberService(
            settings=settings,
            auth=auth,
            pipe_service=self._pipe_service,
        )
        self._webhook_service = WebhookService(
            settings=settings,
            auth=auth,
            card_service=self._card_service,
        )
        self._automation_service = AutomationService(settings=settings, auth=auth)
        self._ai_agent_service = AiAgentService(settings=settings, auth=auth)
        self._observability_service = ObservabilityService(settings=settings, auth=auth)
        self._report_service = ReportService(settings=settings, auth=auth)
        self._organization_service = OrganizationService(settings=settings, auth=auth)
        self._user_service = UserService(settings=settings, auth=auth)
        self._attachment_service = AttachmentService(settings=settings, auth=auth)
        self._introspection_service = SchemaIntrospectionService(
            settings=settings, auth=auth
        )
        self._ai_automation_service: AiAutomationService | None = None
        self._internal_api_client: InternalApiClient | None = None
        self._portal_service = PortalService(settings=settings, auth=auth)

    @property
    def ai_automation_available(self) -> bool:
        """Whether the AI Automation service is configured (OAuth credentials present)."""
        return self._ai_automation_service is not None

    @property
    def internal_api_available(self) -> bool:
        """Whether the internal API client is configured (OAuth credentials present)."""
        return self._internal_api_client is not None

    def set_ai_automation_service(self, service: AiAutomationService) -> None:
        """Attach an AI automation service (requires OAuth credentials).

        Args:
            service: Configured :class:`AiAutomationService` instance.
        """
        self._ai_automation_service = service

    def set_internal_api_client(self, client: InternalApiClient) -> None:
        """Attach the internal API client (requires OAuth credentials).

        Args:
            client: Configured :class:`InternalApiClient` instance.
        """
        self._internal_api_client = client

    async def get_pipe(self, pipe_id: str | int) -> dict:
        """Get a pipe by ID, including phases, labels, and start form fields."""
        return await self._pipe_service.get_pipe(pipe_id)

    async def get_pipe_with_preferences(self, pipe_id: str | int) -> dict:
        """Get a pipe with AI preferences, phases with fields, and start form fields."""
        return await self._pipe_service.get_pipe_with_preferences(pipe_id)

    async def create_pipe(self, name: str, organization_id: str | int) -> dict:
        """Create a new pipe in the organization."""
        return await self._pipe_config_service.create_pipe(name, organization_id)

    async def update_pipe(self, pipe_id: str | int, **attrs: Any) -> dict:
        """Update pipe attributes (see Pipefy `UpdatePipeInput`)."""
        return await self._pipe_config_service.update_pipe(pipe_id, **attrs)

    async def delete_pipe(self, pipe_id: str | int) -> dict:
        """Delete a pipe by ID (permanent)."""
        return await self._pipe_config_service.delete_pipe(pipe_id)

    async def clone_pipe(
        self,
        pipe_template_id: str | int,
        organization_id: str | int | None = None,
    ) -> dict:
        """Clone a pipe from a template pipe ID."""
        return await self._pipe_config_service.clone_pipe(
            pipe_template_id,
            organization_id=organization_id,
        )

    async def create_phase(
        self,
        pipe_id: str | int,
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

    async def update_phase(self, phase_id: str | int, **attrs: Any) -> dict:
        """Update phase attributes (see Pipefy `UpdatePhaseInput`)."""
        return await self._pipe_config_service.update_phase(phase_id, **attrs)

    async def delete_phase(self, phase_id: str | int) -> dict:
        """Delete a phase by ID (permanent)."""
        return await self._pipe_config_service.delete_phase(phase_id)

    async def create_phase_field(
        self,
        phase_id: str | int,
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

    async def delete_phase_field(
        self,
        field_id: str | int,
        *,
        pipe_uuid: str | None = None,
    ) -> dict:
        """Delete a phase field by ID (permanent)."""
        return await self._pipe_config_service.delete_phase_field(
            field_id, pipe_uuid=pipe_uuid
        )

    async def create_label(self, pipe_id: str | int, name: str, color: str) -> dict:
        """Create a label on a pipe."""
        return await self._pipe_config_service.create_label(pipe_id, name, color)

    async def update_label(self, label_id: str | int, **attrs: Any) -> dict:
        """Update a label (see Pipefy `UpdateLabelInput`)."""
        return await self._pipe_config_service.update_label(label_id, **attrs)

    async def delete_label(self, label_id: str | int) -> dict:
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

    async def get_field_conditions(self, phase_id: str | int) -> dict:
        """List field conditions defined on a phase."""
        return await self._pipe_config_service.get_field_conditions(phase_id)

    async def get_field_condition(self, condition_id: str | int) -> dict:
        """Get one field condition by ID (rule, expressions, actions)."""
        return await self._pipe_config_service.get_field_condition(condition_id)

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

    async def create_table(
        self, name: str, organization_id: str | int, **attrs: Any
    ) -> dict:
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

    async def delete_table_field(
        self, field_id: str | int, table_id: str | int
    ) -> dict:
        """Delete a database table field by ID (permanent)."""
        return await self._table_service.delete_table_field(field_id, table_id)

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

    async def invite_members(
        self, pipe_id: str, members: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Invite one or more users to a pipe by email.

        Args:
            pipe_id: ID of the pipe.
            members: List of dicts with at least `email` and `role_name`.
        """
        return await self._member_service.invite_members(pipe_id, members)

    async def remove_members_from_pipe(
        self, pipe_id: str, user_ids: list[str]
    ) -> dict[str, Any]:
        """Remove one or more users from a pipe.

        Args:
            pipe_id: ID or UUID of the pipe.
            user_ids: List of user IDs or UUIDs to remove.
        """
        return await self._member_service.remove_members_from_pipe(pipe_id, user_ids)

    async def set_role(
        self, pipe_id: str, member_id: str, role_name: str
    ) -> dict[str, Any]:
        """Set a member's role on a pipe.

        Args:
            pipe_id: ID of the pipe.
            member_id: User ID of the member.
            role_name: New role name (e.g. 'member', 'admin').
        """
        return await self._member_service.set_role(pipe_id, member_id, role_name)

    async def send_inbox_email(
        self,
        card_id: str,
        to: list[str],
        subject: str,
        body: str,
        *,
        from_: str,
        **attrs: Any,
    ) -> dict[str, Any]:
        """Send an email from a card's inbox.

        Args:
            card_id: ID of the card with inbox.
            to: List of recipient email addresses.
            subject: Email subject.
            body: Email body (plain text).
            from_: Sender email address (required by API).
            **attrs: Extra CreateAndSendInboxEmailInput fields (html, cc, bcc, repoId, etc.).
        """
        return await self._webhook_service.send_inbox_email(
            card_id, to, subject, body, from_=from_, **attrs
        )

    async def get_card_inbox_emails(
        self,
        card_id: str,
        *,
        email_type: str | None = None,
    ) -> dict[str, Any]:
        """List emails (sent and received) for a card's inbox.

        Args:
            card_id: ID of the card with inbox.
            email_type: Optional filter: 'sent' | 'received'. When omitted, returns all.
        """
        return await self._webhook_service.get_card_inbox_emails(
            card_id, email_type=email_type
        )

    async def get_email_templates(
        self,
        repo_id: str,
        *,
        filter_by_name: str | None = None,
        first: int = 50,
    ) -> dict[str, Any]:
        """List email templates for a pipe or table."""
        return await self._webhook_service.get_email_templates(
            repo_id,
            filter_by_name=filter_by_name,
            first=first,
        )

    async def get_parsed_email_template(
        self,
        email_template_id: str,
        *,
        card_uuid: str | None = None,
    ) -> dict[str, Any]:
        """Get an email template with placeholders resolved for a card."""
        return await self._webhook_service.get_parsed_email_template(
            email_template_id,
            card_uuid=card_uuid,
        )

    async def send_email_with_template(
        self,
        card_id: str,
        email_template_id: str,
        *,
        to: list[str] | None = None,
        from_: str | None = None,
        **attrs: Any,
    ) -> dict[str, Any]:
        """Send an email from a card's inbox using an existing email template.

        Args:
            card_id: Numeric ID of the card with inbox.
            email_template_id: ID of the email template.
            to: Optional override for recipients; if omitted, uses template's toEmail.
            from_: Optional override for sender; if omitted, uses template's fromEmail.
            **attrs: Extra CreateAndSendInboxEmailInput fields (cc, bcc, repoId, etc.).
        """
        return await self._webhook_service.send_email_with_template(
            card_id,
            email_template_id,
            to=to,
            from_=from_,
            **attrs,
        )

    async def create_webhook(
        self,
        pipe_id: str,
        url: str,
        actions: list[str],
        **attrs: Any,
    ) -> dict[str, Any]:
        """Create a webhook for pipe events. URL must be HTTPS.

        Args:
            pipe_id: ID of the pipe.
            url: HTTPS URL to receive events.
            actions: List of event action strings (e.g. ['card.create', 'card.move']).
            **attrs: Extra CreateWebhookInput fields (name, filters, headers, etc.).
        """
        return await self._webhook_service.create_webhook(
            pipe_id, url, actions, **attrs
        )

    async def get_webhooks(self, pipe_id: str) -> dict[str, Any]:
        """List webhooks configured on a pipe."""
        return await self._webhook_service.get_webhooks(pipe_id)

    async def update_webhook(self, webhook_id: str, **attrs: Any) -> dict[str, Any]:
        """Update a webhook (see Pipefy ``UpdateWebhookInput``)."""
        return await self._webhook_service.update_webhook(webhook_id, **attrs)

    async def delete_webhook(self, webhook_id: str) -> dict[str, Any]:
        """Delete a webhook by ID (permanent).

        Args:
            webhook_id: ID of the webhook to delete.
        """
        return await self._webhook_service.delete_webhook(webhook_id)

    async def get_automation(self, automation_id: str) -> AutomationRuleRecord | None:
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
        action_repo_id: str | None = None,
        extra_input: dict[str, Any] | None = None,
    ) -> CreateAutomationMutationResult:
        """Create a traditional automation rule (optional ``extra_input`` uses CreateAutomationInput field names).

        Runs :func:`pipefy_sdk.automation_preflight.validate_traditional_automation_move_transition`
        before the API call so callers receive a clear message when a ``card_moved → move_single_card``
        rule references an unreachable destination phase. The check is a no-op for other
        trigger/action combinations.

        Args:
            pipe_id: Pipe ID (event source).
            name: Rule name.
            trigger_id: Event ID.
            action_id: Action ID.
            active: When True (default), create the rule enabled. Set False to start disabled.
            action_repo_id: Pipe ID where the action executes. Defaults to ``pipe_id``.
                For cross-pipe actions (``create_connected_card``, ``move_card_to_pipe``),
                pass the **destination** pipe ID.
            extra_input: Extra ``CreateAutomationInput`` keys; ``active`` here overrides the ``active`` argument.

        Raises:
            AutomationPreflightError: When the move-card transition is invalid.
        """
        await validate_traditional_automation_move_transition(
            self, trigger_id, action_id, extra_input
        )
        return await self._automation_service.create_automation(
            pipe_id,
            name,
            trigger_id,
            action_id,
            action_repo_id=action_repo_id,
            active=active,
            **(extra_input or {}),
        )

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
        """Create a ``send_a_task`` traditional automation (delegates to AutomationService)."""
        return await self._automation_service.create_send_task_automation(
            pipe_id,
            name,
            event_id,
            task_title,
            recipients,
            active=active,
            event_params=event_params,
            condition=condition,
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
        """Dry-run a traditional automation action against a sample card (simulation mutation + query)."""
        return await self._automation_service.simulate_automation(
            pipe_id=pipe_id,
            action_id=action_id,
            sample_card_id=sample_card_id,
            event_id=event_id,
            event_params=event_params,
            action_params=action_params,
            condition=condition,
            name=name,
            extra_input=extra_input,
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

    async def create_ai_agent(
        self, agent_input: CreateAiAgentInput
    ) -> AgentServiceResult:
        """Create an AI Agent (empty, no behaviors).

        Callers are still responsible for pre-Pydantic prep (``normalize_pipefy_ai_instruction_tokens``
        / ``expand_behaviors_placeholders``) where applicable because those run before
        :class:`CreateAiAgentInput` validation at the tool/CLI boundary.
        """
        return await self._ai_agent_service.create_agent(agent_input)

    async def update_ai_agent(
        self, agent_input: UpdateAiAgentInput
    ) -> AgentServiceResult:
        """Replace an AI Agent configuration (instruction and behaviors).

        Resolves field-slug references inside behaviors to numeric IDs and
        populates ``referencedFieldIds`` before calling the service, so
        callers do not need to remember the prep step. Callers are still
        responsible for pre-Pydantic prep (``normalize_pipefy_ai_instruction_tokens``
        / ``expand_behaviors_placeholders``) because those run before
        :class:`UpdateAiAgentInput` validation.
        """
        raw_behaviors = [b.model_dump(by_alias=True) for b in agent_input.behaviors]
        resolved_dicts = await resolve_and_populate_field_refs(self, raw_behaviors)
        resolved_behaviors = [BehaviorInput.model_validate(d) for d in resolved_dicts]
        prepared = agent_input.model_copy(update={"behaviors": resolved_behaviors})
        return await self._ai_agent_service.update_agent(prepared)

    async def toggle_ai_agent_status(
        self, agent_uuid: str, *, active: bool
    ) -> ToggleAgentStatusResult:
        """Enable or disable an AI Agent."""
        return await self._ai_agent_service.toggle_agent_status(
            agent_uuid=agent_uuid, active=active
        )

    async def create_ai_automation(
        self, automation_input: CreateAiAutomationInput
    ) -> AutomationServiceResult:
        """Create an AI Automation (generate_with_ai action via internal API)."""
        assert self._ai_automation_service is not None  # noqa: S101
        return await self._ai_automation_service.create_automation(automation_input)

    async def update_ai_automation(
        self, automation_input: UpdateAiAutomationInput
    ) -> AutomationServiceResult:
        """Update an existing AI Automation via internal API."""
        assert self._ai_automation_service is not None  # noqa: S101
        return await self._ai_automation_service.update_automation(automation_input)

    async def get_pipe_members(self, pipe_id: str | int) -> dict:
        """Get the members of a pipe."""
        return await self._pipe_service.get_pipe_members(pipe_id)

    async def create_card(
        self, pipe_id: str | int, fields: dict[str, Any] | list[dict[str, Any]]
    ) -> dict:
        """Create a card in the specified pipe with the given fields."""
        return await self._card_service.create_card(pipe_id, fields)

    async def add_card_comment(self, card_id: str | int, text: str) -> dict:
        """Add a text comment to a card by its ID."""
        return await self._card_service.create_comment(card_id, text)

    async def update_comment(self, comment_id: str | int, text: str) -> dict:
        """Update an existing comment by its ID."""
        return await self._card_service.update_comment(comment_id, text)

    async def delete_comment(self, comment_id: str | int) -> dict:
        """Delete a comment by its ID."""
        return await self._card_service.delete_comment(comment_id)

    async def get_card(self, card_id: str | int, include_fields: bool = False) -> dict:
        """Get a card by its ID.

        Args:
            card_id: The ID of the card.
            include_fields: If True, include the card's custom fields (name, value) in the response.
        """
        return await self._card_service.get_card(card_id, include_fields=include_fields)

    async def get_cards(
        self,
        pipe_id: str | int,
        search: CardSearch | None = None,
        include_fields: bool = False,
        *,
        first: int | None = None,
        after: str | None = None,
    ) -> dict:
        """Get cards in the pipe with optional search filters and pagination.

        Args:
            pipe_id: The ID of the pipe.
            search: Optional search filters.
            include_fields: If True, include each card's custom fields (name, value) in the response.
            first: Max cards to return per page.
            after: Cursor for fetching the next page (from ``pageInfo.endCursor``).
        """
        return await self._card_service.get_cards(
            pipe_id, search, include_fields=include_fields, first=first, after=after
        )

    async def find_cards(
        self,
        pipe_id: str | int,
        field_id: str,
        field_value: str,
        include_fields: bool = False,
        *,
        first: int | None = None,
        after: str | None = None,
    ) -> dict:
        """Find cards in the pipe where the given field equals the given value.

        Args:
            pipe_id: The ID of the pipe to search in.
            field_id: Pipefy field identifier (e.g. from get_start_form_fields or get_phase_fields).
            field_value: Value to match for that field (string; use format expected by field type).
            include_fields: If True, include each card's custom fields (name, value) in the response.
            first: Max cards per page (optional).
            after: Cursor from ``pageInfo.endCursor`` for the next page (optional).
        """
        return await self._card_service.find_cards(
            pipe_id,
            field_id,
            field_value,
            include_fields=include_fields,
            first=first,
            after=after,
        )

    async def move_card_to_phase(
        self, card_id: str | int, destination_phase_id: str | int
    ) -> dict:
        """Move a card to a specific phase."""
        return await self._card_service.move_card_to_phase(
            card_id, destination_phase_id
        )

    async def update_card_field(
        self, card_id: str | int, field_id: str, new_value: Any
    ) -> dict:
        """Update a single field of a card."""
        return await self._card_service.update_card_field(card_id, field_id, new_value)

    async def update_card(
        self,
        card_id: str | int,
        title: str | None = None,
        assignee_ids: list[str | int] | None = None,
        label_ids: list[str | int] | None = None,
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

    async def delete_card(self, card_id: str | int) -> dict:
        """Delete a card by its ID."""
        return await self._card_service.delete_card(card_id)

    async def get_card_relations(self, card_id: str | int) -> dict:
        """Get parent and child card relations for a card."""
        return await self._card_service.get_card_relations(card_id)

    async def delete_card_relation(
        self,
        child_id: str | int,
        parent_id: str | int,
        source_id: str | int,
    ) -> dict:
        """Delete a relation link between two cards (internal API, requires OAuth).

        The ``deleteCardRelation`` mutation is not exposed on the public GraphQL
        schema — only on the internal API (core_api / internal_v1).
        """
        assert self._internal_api_client is not None  # noqa: S101
        return await self._internal_api_client.execute_query(
            INTERNAL_DELETE_CARD_RELATION_MUTATION,
            {
                "childId": str(child_id),
                "parentId": str(parent_id),
                "sourceId": str(source_id),
            },
        )

    async def get_start_form_fields(
        self, pipe_id: str | int, required_only: bool = False
    ) -> dict:
        """Get the start form fields of a pipe."""
        return await self._pipe_service.get_start_form_fields(pipe_id, required_only)

    async def search_pipes(
        self,
        pipe_name: str | None = None,
        *,
        max_pipes_per_org: int = SEARCH_PIPES_MAX_PER_ORG_CAP,
    ) -> dict:
        """Search for pipes across all organizations"""
        return await self._pipe_service.search_pipes(
            pipe_name,
            max_pipes_per_org=max_pipes_per_org,
        )

    async def search_tables(
        self,
        table_name: str | None = None,
        *,
        first: int = SEARCH_TABLES_FIRST_DEFAULT,
    ) -> dict:
        """Search for databases (tables) across all organizations"""
        return await self._table_service.search_tables(table_name, first=first)

    async def get_phase_fields(
        self, phase_id: str | int, required_only: bool = False
    ) -> dict:
        """Get the fields available in a specific phase."""
        return await self._pipe_service.get_phase_fields(phase_id, required_only)

    async def get_phase_allowed_move_targets(self, phase_id: str | int) -> dict:
        """Phases reachable from ``phase_id`` per Pipefy transition rules (read-only)."""
        return await self._pipe_service.get_phase_allowed_move_targets(phase_id)

    async def get_phase_cards_count(self, phase_id: str | int) -> int:
        """Total card count for ``phase_id`` via native ``Phase.cards_count``."""
        return await self._pipe_service.get_phase_cards_count(phase_id)

    async def get_pipe_reports(
        self,
        pipe_uuid: str,
        *,
        first: int = 30,
        after: str | None = None,
        search: str | None = None,
        report_id: str | None = None,
        order: dict | None = None,
    ) -> dict:
        """List pipe reports with pagination and optional search/filter."""
        return await self._report_service.get_pipe_reports(
            pipe_uuid,
            first=first,
            after=after,
            search=search,
            report_id=report_id,
            order=order,
        )

    async def get_pipe_report_columns(self, pipe_uuid: str) -> dict:
        """Get available columns for a pipe report."""
        return await self._report_service.get_pipe_report_columns(pipe_uuid)

    async def get_pipe_report_filterable_fields(self, pipe_uuid: str) -> dict:
        """Get filterable fields for a pipe report."""
        return await self._report_service.get_pipe_report_filterable_fields(pipe_uuid)

    async def get_organization_report(self, report_id: str) -> dict:
        """Get a single organization report by ID."""
        return await self._report_service.get_organization_report(report_id)

    async def get_organization_reports(
        self,
        organization_id: str,
        *,
        first: int = 30,
        after: str | None = None,
    ) -> dict:
        """List organization reports with pagination."""
        return await self._report_service.get_organization_reports(
            organization_id, first=first, after=after
        )

    async def get_pipe_report_export(self, export_id: str) -> dict:
        """Check the status of a pipe report export."""
        return await self._report_service.get_pipe_report_export(export_id)

    async def get_organization_report_export(self, export_id: str) -> dict:
        """Check the status of an organization report export."""
        return await self._report_service.get_organization_report_export(export_id)

    async def create_pipe_report(
        self,
        pipe_id: str,
        name: str,
        *,
        fields: list[str] | None = None,
        filter: dict | None = None,
        formulas: list[list[str]] | None = None,
    ) -> dict:
        """Create a pipe report with name, fields, and optional filter."""
        return await self._report_service.create_pipe_report(
            pipe_id, name, fields=fields, filter=filter, formulas=formulas
        )

    async def update_pipe_report(
        self,
        report_id: str,
        *,
        name: str | None = None,
        color: str | None = None,
        fields: list[str] | None = None,
        filter: dict | None = None,
        formulas: list[list[str]] | None = None,
        featured_field: str | None = None,
    ) -> dict:
        """Update a pipe report. Only provided values are changed."""
        return await self._report_service.update_pipe_report(
            report_id,
            name=name,
            color=color,
            fields=fields,
            filter=filter,
            formulas=formulas,
            featured_field=featured_field,
        )

    async def delete_pipe_report(self, report_id: str) -> dict:
        """Delete a pipe report by ID (permanent)."""
        return await self._report_service.delete_pipe_report(report_id)

    async def create_organization_report(
        self,
        organization_id: str,
        name: str,
        pipe_ids: list[str],
        *,
        fields: list[str] | None = None,
        filter: dict | None = None,
    ) -> dict:
        """Create an org-wide report spanning multiple pipes."""
        return await self._report_service.create_organization_report(
            organization_id, name, pipe_ids, fields=fields, filter=filter
        )

    async def update_organization_report(
        self,
        report_id: str,
        *,
        name: str | None = None,
        color: str | None = None,
        fields: list[str] | None = None,
        filter: dict | None = None,
        pipe_ids: list[str] | None = None,
    ) -> dict:
        """Update an organization report. Only provided values are changed."""
        return await self._report_service.update_organization_report(
            report_id,
            name=name,
            color=color,
            fields=fields,
            filter=filter,
            pipe_ids=pipe_ids,
        )

    async def delete_organization_report(self, report_id: str) -> dict:
        """Delete an organization report by ID (permanent)."""
        return await self._report_service.delete_organization_report(report_id)

    async def export_pipe_report(
        self,
        pipe_id: str,
        pipe_report_id: str,
        *,
        sort_by: dict | None = None,
        filter: dict | None = None,
        columns: list[str] | None = None,
    ) -> dict:
        """Trigger an async pipe report export."""
        return await self._report_service.export_pipe_report(
            pipe_id,
            pipe_report_id,
            sort_by=sort_by,
            filter=filter,
            columns=columns,
        )

    async def export_organization_report(
        self,
        organization_id: str | int,
        *,
        organization_report_id: str | int | None = None,
        pipe_ids: list[str | int] | None = None,
        sort_by: dict | None = None,
        filter: dict | None = None,
        columns: list[str] | None = None,
    ) -> dict:
        """Trigger an async organization report export."""
        return await self._report_service.export_organization_report(
            organization_id,
            organization_report_id=organization_report_id,
            pipe_ids=pipe_ids,
            sort_by=sort_by,
            filter=filter,
            columns=columns,
        )

    async def export_pipe_audit_logs(
        self,
        pipe_uuid: str,
        *,
        search_term: str | None = None,
    ) -> dict:
        """Trigger an async pipe audit logs export."""
        return await self._report_service.export_pipe_audit_logs(
            pipe_uuid,
            search_term=search_term,
        )

    async def get_organization(self, organization_id: str) -> dict[str, Any]:
        """Fetch organization details by ID.

        Args:
            organization_id: Numeric organization ID.
        """
        return await self._organization_service.get_organization(organization_id)

    async def list_portals(
        self,
        organization_uuid: str | int,
        search_term: str | None = None,
    ) -> list[dict[str, Any]]:
        """List portals for an organization.

        Args:
            organization_uuid: Organization UUID, or numeric organization id.
            search_term: Optional name filter.
        """
        return await self._portal_service.list_portals(
            organization_uuid, search_term=search_term
        )

    async def get_portal(self, portal_uuid: str) -> dict[str, Any]:
        """Fetch a portal by UUID.

        Args:
            portal_uuid: Portal interface UUID.
        """
        return await self._portal_service.get_portal(portal_uuid)

    async def create_portal(self, organization_uuid: str | int) -> dict[str, Any]:
        """Create or fetch the organization's main portal (idempotent).

        Args:
            organization_uuid: Organization UUID or numeric organization id.
        """
        return await self._portal_service.create_portal(organization_uuid)

    async def update_portal(
        self,
        interface_uuid: str,
        *,
        name: str | None = None,
        visibility: str | None = None,
        color: str | None = None,
        icon: str | None = None,
        display_pipefy_header: bool | None = None,
    ) -> dict[str, Any]:
        """Update portal metadata.

        Args:
            interface_uuid: Portal interface UUID.
            name: Optional display name.
            visibility: ``internal``, ``private``, or ``public``.
            color: Optional theme color.
            icon: Optional icon identifier.
            display_pipefy_header: Whether to show the Pipefy header.
        """
        return await self._portal_service.update_portal(
            interface_uuid,
            name=name,
            visibility=visibility,
            color=color,
            icon=icon,
            display_pipefy_header=display_pipefy_header,
        )

    async def delete_portal(self, interface_uuid: str) -> dict[str, Any]:
        """Delete a portal interface (irreversible).

        Args:
            interface_uuid: Portal interface UUID.
        """
        return await self._portal_service.delete_portal(interface_uuid)

    async def create_portal_page(
        self,
        interface_uuid: str,
        title: str,
        *,
        description: str | None = None,
        index: int | None = None,
    ) -> dict[str, Any]:
        """Create a portal page.

        Args:
            interface_uuid: Parent portal interface UUID.
            title: Page title.
            description: Optional page description.
            index: Optional sort index.
        """
        return await self._portal_service.create_portal_page(
            interface_uuid,
            title,
            description=description,
            index=index,
        )

    async def update_portal_page(
        self,
        interface_uuid: str,
        page_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        index: int | None = None,
    ) -> dict[str, Any]:
        """Update portal page metadata.

        Args:
            interface_uuid: Parent portal interface UUID.
            page_id: Page UUID.
            title: Optional new title.
            description: Optional new description.
            index: Optional sort index.
        """
        return await self._portal_service.update_portal_page(
            interface_uuid,
            page_id,
            title=title,
            description=description,
            index=index,
        )

    async def delete_portal_page(
        self, interface_uuid: str, page_id: str
    ) -> dict[str, Any]:
        """Delete a portal page (irreversible).

        Args:
            interface_uuid: Parent portal interface UUID.
            page_id: Page UUID.
        """
        return await self._portal_service.delete_portal_page(interface_uuid, page_id)

    async def sort_portal_pages(
        self, interface_uuid: str, page_ids: list[str]
    ) -> dict[str, Any]:
        """Reorder portal pages.

        Args:
            interface_uuid: Parent portal interface UUID.
            page_ids: Ordered list of page UUIDs.
        """
        return await self._portal_service.sort_portal_pages(interface_uuid, page_ids)

    async def update_portal_page_layout(
        self, page_id: str, layout: dict[str, Any]
    ) -> dict[str, Any]:
        """Update a portal page grid layout.

        Args:
            page_id: Page UUID.
            layout: Layout JSON for ``updatePageLayout``.
        """
        return await self._portal_service.update_portal_page_layout(page_id, layout)

    async def create_portal_element(
        self,
        page_id: str,
        *,
        type: str,
        metadata: dict[str, Any],
        data_sources: list[dict[str, Any]] | None = None,
        element_id: str | None = None,
        editable: bool | None = None,
        layout: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a portal page element.

        Args:
            page_id: Parent page UUID.
            type: ``InterfacePageElementType`` value (e.g. ``forms``, ``link``).
            metadata: Element metadata JSON.
            data_sources: Optional data source bindings.
            element_id: Optional client-provided element UUID.
            editable: Optional editable flag.
            layout: Optional layout JSON.
        """
        return await self._portal_service.create_portal_element(
            page_id,
            type=type,
            metadata=metadata,
            data_sources=data_sources,
            element_id=element_id,
            editable=editable,
            layout=layout,
        )

    async def update_portal_element(
        self,
        element_id: str,
        page_id: str,
        *,
        type: str,
        metadata: dict[str, Any],
        data_sources: list[dict[str, Any]] | None = None,
        editable: bool | None = None,
    ) -> dict[str, Any]:
        """Update a portal page element (full metadata replace).

        Returned ``metadata`` is the validated input echo (``updateElement`` does not
        return stored element data). Use ``get_portal`` after update when you need
        server-side state.

        Args:
            element_id: Element UUID.
            page_id: Parent page UUID.
            type: Element type for metadata validation.
            metadata: Complete metadata blob.
            data_sources: Optional data source bindings.
            editable: Optional editable flag.
        """
        return await self._portal_service.update_portal_element(
            element_id,
            page_id,
            type=type,
            metadata=metadata,
            data_sources=data_sources,
            editable=editable,
        )

    async def delete_portal_element(
        self, element_id: str, page_id: str
    ) -> dict[str, Any]:
        """Delete a portal page element (irreversible).

        Args:
            element_id: Element UUID.
            page_id: Parent page UUID.
        """
        return await self._portal_service.delete_portal_element(element_id, page_id)

    async def duplicate_portal_element(
        self,
        *,
        element_id: str,
        portal_uuid: str,
        page_id: str,
    ) -> dict[str, Any]:
        """Duplicate a portal page element on the same page.

        ``portal_uuid`` and ``page_id`` identify where the source element lives.

        Args:
            element_id: Element UUID to duplicate.
            portal_uuid: Portal interface UUID that owns the page.
            page_id: Page UUID that contains the element.
        """
        return await self._portal_service.duplicate_portal_element(
            element_id=element_id,
            portal_uuid=portal_uuid,
            page_id=page_id,
        )

    async def create_sub_portal(
        self,
        main_portal_uuid: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Create a sub-portal on a main portal.

        Args:
            main_portal_uuid: Parent main portal interface UUID.
            name: Optional display name.
        """
        return await self._portal_service.create_sub_portal(main_portal_uuid, name)

    async def update_sub_portal_element(
        self,
        portal_uuid: str,
        element_id: str,
        sub_portal_uuid: str,
    ) -> dict[str, Any]:
        """Attach a sub-portal to a portal page element.

        Args:
            portal_uuid: Main portal interface UUID.
            element_id: Page element UUID.
            sub_portal_uuid: Sub-portal UUID.
        """
        return await self._portal_service.update_sub_portal_element(
            portal_uuid,
            element_id,
            sub_portal_uuid,
        )

    async def publish_sub_portal(
        self,
        portal_uuid: str,
        element_id: str,
        sub_portal_uuid: str,
    ) -> dict[str, Any]:
        """Publish a sub-portal on a page element.

        Args:
            portal_uuid: Main portal interface UUID.
            element_id: Page element UUID.
            sub_portal_uuid: Sub-portal UUID.
        """
        return await self._portal_service.publish_sub_portal(
            portal_uuid,
            element_id,
            sub_portal_uuid,
        )

    async def unpublish_sub_portal(
        self,
        portal_uuid: str,
        element_id: str,
    ) -> dict[str, Any]:
        """Unpublish a sub-portal from a page element via ``updateSubPortalElement``.

        Sends ``subPortalUuid: null`` to clear the link. Distinct from
        ``delete_sub_portal_element`` (removes the wiring slot) and
        ``delete_sub_portal`` (deletes the sub-portal entity).

        Args:
            portal_uuid: Main portal interface UUID.
            element_id: Page element UUID.
        """
        return await self._portal_service.unpublish_sub_portal(
            portal_uuid,
            element_id,
        )

    async def delete_sub_portal_element(
        self,
        portal_uuid: str,
        element_id: str,
    ) -> dict[str, Any]:
        """Remove sub-portal wiring from a page element.

        Args:
            portal_uuid: Main portal interface UUID.
            element_id: Page element UUID.
        """
        return await self._portal_service.delete_sub_portal_element(
            portal_uuid,
            element_id,
        )

    async def delete_sub_portal(self, uuid: str) -> dict[str, Any]:
        """Delete a sub-portal entity (irreversible).

        Args:
            uuid: Sub-portal UUID.
        """
        return await self._portal_service.delete_sub_portal(uuid)

    async def get_me(self) -> MePayload | None:
        """Return the authenticated user's identity, or ``None`` when ``me`` resolves null."""
        return await self._user_service.get_me()

    async def create_presigned_url(
        self,
        organization_id: str,
        file_name: str,
        content_type: str | None = None,
        content_length: int | None = None,
    ) -> dict[str, Any]:
        """Request a presigned upload URL from Pipefy.

        Args:
            organization_id: Organization ID.
            file_name: Target file name for the upload.
            content_type: Optional MIME type for the object.
            content_length: Optional size in bytes.
        """
        return await self._attachment_service.create_presigned_url(
            organization_id,
            file_name,
            content_type=content_type,
            content_length=content_length,
        )

    async def upload_file_to_s3(
        self,
        presigned_url: str,
        file_bytes: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """PUT file bytes to a presigned object storage URL.

        Args:
            presigned_url: Full presigned destination URL.
            file_bytes: Raw file content.
            content_type: Optional ``Content-Type`` header for the PUT.
        """
        return await self._attachment_service.upload_file_to_s3(
            presigned_url, file_bytes, content_type=content_type
        )

    async def upload_attachment_to_card_field(
        self,
        *,
        organization_id: str,
        card_id: str,
        field_id: str,
        file_name: str,
        file_bytes: bytes,
        content_type: str | None = None,
    ) -> AttachmentUploadResult:
        """Upload ``file_bytes`` to a card attachment field via the standard pipeline.

        Wraps presigned URL → S3 PUT → ``update_card_field`` in one call so MCP
        and CLI surfaces do not duplicate the orchestration. Raises
        :class:`AttachmentUploadError` on any step failure (with ``step`` attribute).
        """
        return await upload_attachment_to_card_field(
            self,
            organization_id=organization_id,
            card_id=card_id,
            field_id=field_id,
            file_name=file_name,
            file_bytes=file_bytes,
            content_type=content_type,
        )

    async def upload_attachment_to_table_record_field(
        self,
        *,
        organization_id: str,
        table_record_id: str,
        field_id: str,
        file_name: str,
        file_bytes: bytes,
        content_type: str | None = None,
    ) -> AttachmentUploadResult:
        """Upload ``file_bytes`` to a table record attachment field via the standard pipeline."""
        return await upload_attachment_to_table_record_field(
            self,
            organization_id=organization_id,
            table_record_id=table_record_id,
            field_id=field_id,
            file_name=file_name,
            file_bytes=file_bytes,
            content_type=content_type,
        )

    def extract_storage_path(self, presigned_url: str) -> str:
        """Return the object key path embedded in a presigned URL (no host or query string).

        Args:
            presigned_url: Full HTTPS URL including path and optional query string.
        """
        return self._attachment_service.extract_storage_path(presigned_url)

    async def introspect_type(
        self, type_name: str, *, max_depth: int = 1
    ) -> dict[str, Any]:
        """Introspect a GraphQL type by name (fields, inputFields, or enumValues).

        Args:
            type_name: Schema type name (e.g. Card, CreateCardInput).
            max_depth: How many levels of referenced types to resolve (default 1).
        """
        return await self._introspection_service.introspect_type(
            type_name, max_depth=max_depth
        )

    async def introspect_mutation(
        self, mutation_name: str, *, max_depth: int = 1
    ) -> dict[str, Any]:
        """Introspect a root mutation field (arguments and return type).

        Args:
            mutation_name: Mutation field name as exposed on the Mutation type.
            max_depth: How many levels of referenced types to resolve (default 1).
        """
        return await self._introspection_service.introspect_mutation(
            mutation_name, max_depth=max_depth
        )

    async def introspect_query(
        self, query_name: str, *, max_depth: int = 1
    ) -> dict[str, Any]:
        """Introspect a root query field (arguments and return type).

        Args:
            query_name: Query field name as exposed on the Query type.
            max_depth: How many levels of referenced types to resolve (default 1).
        """
        return await self._introspection_service.introspect_query(
            query_name, max_depth=max_depth
        )

    async def search_schema(
        self, keyword: str, *, kind: str | None = None
    ) -> dict[str, Any]:
        """Search schema types by keyword (name or description).

        Args:
            keyword: Case-insensitive substring to match.
            kind: Optional GraphQL type kind filter (e.g. OBJECT, INPUT_OBJECT, ENUM).
        """
        return await self._introspection_service.search_schema(keyword, kind=kind)

    async def execute_graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute arbitrary GraphQL after syntax validation (fallback / advanced use).

        Args:
            query: GraphQL document string.
            variables: Optional variables for the operation.
        """
        return await self._introspection_service.execute_graphql(query, variables)

    async def get_ai_agent_logs(
        self,
        repo_uuid: str,
        *,
        first: int = 30,
        after: str | None = None,
        status: str | None = None,
        search_term: str | None = None,
    ) -> dict[str, Any]:
        """List AI agent execution logs for a pipe (paginated).

        Args:
            repo_uuid: Pipe UUID.
            first: Page size.
            after: Cursor for next page.
            status: AiAgentLogStatus filter (processing, failed, success).
            search_term: Free-text search.
        """
        return await self._observability_service.get_ai_agent_logs(
            repo_uuid, first=first, after=after, status=status, search_term=search_term
        )

    async def get_ai_agent_log_details(self, log_uuid: str) -> dict[str, Any]:
        """Get detailed AI agent execution log with tracing nodes.

        Args:
            log_uuid: UUID of the AI agent log entry.
        """
        return await self._observability_service.get_ai_agent_log_details(log_uuid)

    async def get_automation_logs(
        self,
        automation_id: str,
        *,
        first: int = 30,
        after: str | None = None,
        status: str | None = None,
        search_term: str | None = None,
    ) -> dict[str, Any]:
        """List execution logs for a specific automation (paginated).

        Args:
            automation_id: Automation ID.
            first: Page size.
            after: Cursor for next page.
            status: AutomationLogStatus filter (processing, failed, success).
            search_term: Free-text search.
        """
        return await self._observability_service.get_automation_logs(
            automation_id,
            first=first,
            after=after,
            status=status,
            search_term=search_term,
        )

    async def get_automation_logs_by_repo(
        self,
        repo_id: str,
        *,
        first: int = 30,
        after: str | None = None,
        status: str | None = None,
        search_term: str | None = None,
    ) -> dict[str, Any]:
        """List automation logs for all automations in a pipe/repo (paginated).

        Args:
            repo_id: Pipe/repo ID.
            first: Page size.
            after: Cursor for next page.
            status: AutomationLogStatus filter (processing, failed, success).
            search_term: Free-text search.
        """
        rules = await self.get_automations(pipe_id=str(repo_id))
        if not rules:
            return {
                "automationLogsByRepo": {
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "totalCount": 0,
                }
            }
        return await self._observability_service.get_automation_logs_by_repo(
            repo_id, first=first, after=after, status=status, search_term=search_term
        )

    async def get_agents_usage(
        self,
        organization_uuid: str,
        filter_date: dict[str, str],
        *,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        sort: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get AI agent usage stats for an org within a date range.

        Args:
            organization_uuid: Organization UUID.
            filter_date: DateRange dict with ``from`` and ``to`` ISO8601 strings.
            filters: Optional FilterParams (action, event, pipe, status).
            search: Free-text search.
            sort: SortCriteria (field + direction).
        """
        return await self._observability_service.get_agents_usage(
            organization_uuid, filter_date, filters=filters, search=search, sort=sort
        )

    async def get_automations_usage(
        self,
        organization_uuid: str,
        filter_date: dict[str, str],
        *,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        sort: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get automation usage stats for an org within a date range.

        Args:
            organization_uuid: Organization UUID.
            filter_date: DateRange dict with ``from`` and ``to`` ISO8601 strings.
            filters: Optional FilterParams (action, event, pipe, status).
            search: Free-text search.
            sort: SortCriteria (field + direction).
        """
        return await self._observability_service.get_automations_usage(
            organization_uuid, filter_date, filters=filters, search=search, sort=sort
        )

    async def get_ai_credit_usage(
        self,
        organization_uuid: str,
        period: str,
    ) -> dict[str, Any]:
        """Get AI credit usage dashboard for an org.

        Args:
            organization_uuid: Organization UUID, or numeric organization id as a string (resolved
                to UUID before calling the API).
            period: PeriodFilter (current_month, last_month, last_3_months).
        """
        return await self._observability_service.get_ai_credit_usage(
            organization_uuid, period
        )

    async def export_automation_jobs(
        self,
        organization_id: str,
        period: str,
    ) -> dict[str, Any]:
        """Trigger async export of automation job history.

        Args:
            organization_id: Organization ID.
            period: PeriodFilter (current_month, last_month, last_3_months); mapped to GraphQL ``filter``.
        """
        return await self._observability_service.export_automation_jobs(
            organization_id, period
        )

    async def get_automation_jobs_export(self, export_id: str) -> dict[str, Any]:
        """Get automation jobs export status and signed file URL when ready.

        Args:
            export_id: Id from ``export_automation_jobs`` / ``createAutomationJobsExport`` response.
        """
        return await self._observability_service.get_automation_jobs_export(export_id)

    async def get_automation_jobs_export_csv(
        self,
        export_id: str,
        *,
        max_output_chars: int = 400_000,
        max_download_bytes: int = 50 * 1024 * 1024,
    ) -> dict[str, Any]:
        """Download a finished automation jobs export xlsx and return the first sheet as CSV.

        Args:
            export_id: Id from ``export_automation_jobs`` when status is ``finished``.
            max_output_chars: Truncate CSV text beyond this length (UTF-8 characters).
            max_download_bytes: Refuse larger downloads.
        """
        return await self._observability_service.get_automation_jobs_export_csv(
            export_id,
            max_output_chars=max_output_chars,
            max_download_bytes=max_download_bytes,
        )
