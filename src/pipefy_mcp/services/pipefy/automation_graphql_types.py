"""TypedDict shapes for traditional automation GraphQL responses (query-selected fields)."""

from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict


class AutomationEventRepoRef(TypedDict, total=False):
    """Nested ``event_repo`` on a full automation rule."""

    id: str
    name: str


class AutomationEventParamsRecord(TypedDict, total=False):
    """``event_params`` on ``Automation`` (trigger configuration)."""

    fromPhaseId: str | None
    inPhaseId: str | None
    kindOfSla: str | None
    to_phase_id: str | None
    triggerAutomationId: str | None
    triggerFieldIds: list[str] | None
    phase: AutomationEventRepoRef | None


class AutomationAiParamsRecord(TypedDict, total=False):
    """``aiParams`` under ``action_params``."""

    value: str | None
    fieldIds: list[str] | None
    skillsIds: list[str] | None


class AiBehaviorParamsRecord(TypedDict, total=False):
    """``aiBehaviorParams`` (subset: list/object API branches need explicit subselections)."""

    instruction: str
    providerId: str | None
    uuid: str


class AutomationFieldMapRecord(TypedDict, total=False):
    """Single ``field_map`` entry."""

    fieldId: str
    inputMode: str
    value: str


class AutomationSlaDayRecord(TypedDict, total=False):
    """Working hours row inside ``slaParams``."""

    enabled: bool
    endHour: str | None
    startHour: str | None


class AutomationSlaHolidayRecord(TypedDict, total=False):
    """Single holiday inside ``slaParams.holidays``."""

    date: str
    description: str
    recurrence: str


class AutomationSlaRulesParamsRecord(TypedDict, total=False):
    """``slaParams`` on ``AutomationActionParams``."""

    timezone: str
    holidays: list[AutomationSlaHolidayRecord] | None
    monday: AutomationSlaDayRecord | None
    tuesday: AutomationSlaDayRecord | None
    wednesday: AutomationSlaDayRecord | None
    thursday: AutomationSlaDayRecord | None
    friday: AutomationSlaDayRecord | None
    saturday: AutomationSlaDayRecord | None
    sunday: AutomationSlaDayRecord | None


class AutomationTaskParamsRecord(TypedDict, total=False):
    """``taskParams`` (send-a-task action)."""

    recipients: str
    title: str


class Oauth2ClientDataRecord(TypedDict, total=False):
    """``oauth2ClientData`` for HTTP Request actions."""

    clientId: str
    grantType: str
    name: str
    ownerId: str
    ownerType: str
    scopes: str | None
    tokenUrl: str
    uuid: str


class AutomationActionParamsRecord(TypedDict, total=False):
    """``action_params`` on ``Automation`` (subset aligned with query selection)."""

    aiParams: AutomationAiParamsRecord | None
    aiBehaviorParams: AiBehaviorParamsRecord | None
    authenticationAddTo: str | None
    authenticationKey: str | None
    authenticationType: str | None
    body: str | None
    card_id: str | None
    email_template_id: str | None
    field_map: list[AutomationFieldMapRecord] | None
    fields_map_order: list[str] | None
    hasAuthenticationValue: bool | None
    headers: str | None
    httpMethod: str | None
    oauth2ClientData: Oauth2ClientDataRecord | None
    phase: AutomationEventRepoRef | None
    slaParams: AutomationSlaRulesParamsRecord | None
    strategy: str | None
    taskParams: AutomationTaskParamsRecord | None
    to_phase_id: str | None
    url: str | None


class AutomationRuleRecord(TypedDict, total=False):
    """Single automation from ``GET_AUTOMATION_QUERY``."""

    id: str
    name: str
    active: bool
    event_id: str
    action_id: str
    actionEnabled: bool
    disabledReason: str | None
    created_at: str | None
    event_repo: AutomationEventRepoRef | None
    event_params: AutomationEventParamsRecord | None
    action_params: AutomationActionParamsRecord | None


class AutomationRuleSummary(TypedDict, total=False):
    """List node from organization/repo automation listings."""

    id: str
    name: str
    active: bool


class AutomationActionRow(TypedDict, total=False):
    """Row from ``automationActions(repoId:)``."""

    id: str
    icon: str
    enabled: bool
    acceptedParameters: list[Any]
    disabledReason: str | None
    eventsBlacklist: list[Any]
    initiallyHidden: bool
    triggerEvents: list[Any]


class AutomationEventRow(TypedDict, total=False):
    """Row from the global ``automationEvents`` catalog."""

    id: str
    icon: str
    acceptedParameters: list[Any]
    actionsBlacklist: list[Any]


class AutomationMutationSnapshot(TypedDict, total=False):
    """``automation`` object returned inside create/update mutations."""

    id: str
    name: str
    active: bool


class InternalErrorDetail(TypedDict, total=False):
    """Single ``InternalError`` row from ``error_details`` on automation mutations."""

    object_name: str
    object_key: str
    messages: list[str]


class CreateAutomationMutationBlock(TypedDict, total=False):
    automation: AutomationMutationSnapshot | None
    error_details: list[InternalErrorDetail]


class CreateAutomationMutationResult(TypedDict, total=False):
    createAutomation: CreateAutomationMutationBlock


class UpdateAutomationMutationBlock(TypedDict, total=False):
    automation: AutomationMutationSnapshot | None
    error_details: list[InternalErrorDetail]


class UpdateAutomationMutationResult(TypedDict, total=False):
    updateAutomation: UpdateAutomationMutationBlock


class DeleteAutomationServiceResult(TypedDict):
    """Normalized delete outcome exposed by ``AutomationService.delete_automation``."""

    success: bool


class CreateAutomationSimulationMutationBlock(TypedDict, total=False):
    """Payload from ``createAutomationSimulation`` (IDs only; full row comes from a follow-up query)."""

    simulationId: str
    clientMutationId: str | None


class CreateAutomationSimulationMutationResult(TypedDict, total=False):
    createAutomationSimulation: CreateAutomationSimulationMutationBlock


class AutomationSimulationLogDetails(TypedDict, total=False):
    """``details`` on ``AutomationSimulation``."""

    errorType: str | None
    message: str


class AutomationSimulationRow(TypedDict, total=False):
    """``automationSimulation`` query selection (status, details, simulationResult)."""

    status: str
    details: AutomationSimulationLogDetails | None
    simulationResult: Any


class SimulateAutomationServiceResult(TypedDict):
    """Mutation + query outcome from ``AutomationService.simulate_automation``."""

    simulation_id: str
    automation_simulation: AutomationSimulationRow
