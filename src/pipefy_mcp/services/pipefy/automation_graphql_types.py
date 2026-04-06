"""TypedDict shapes for traditional automation GraphQL responses (query-selected fields)."""

from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict


class AutomationEventRepoRef(TypedDict, total=False):
    """Nested ``event_repo`` on a full automation rule."""

    id: str
    name: str


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
