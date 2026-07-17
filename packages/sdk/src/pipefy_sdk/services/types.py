from __future__ import annotations

from typing import Any, Literal

from typing_extensions import TypedDict


class CardSearch(TypedDict, total=False):
    """Type definition for card search parameters"""

    assignee_ids: list[str]
    ignore_ids: list[str]
    label_ids: list[str]
    title: str
    inbox_emails_read: bool
    include_done: bool


def copy_card_search(search: CardSearch) -> CardSearch:
    """Shallow copy containing only keys defined on :class:`CardSearch`.

    Drops any extra keys so MCP-supplied dicts match the schema expected by
    :meth:`PipefyClient.get_cards`.
    """
    return {k: search[k] for k in CardSearch.__optional_keys__ if k in search}


class AiAgentGraphPayload(TypedDict, total=False):
    """Common fields returned by Pipefy ``aiAgent`` (additional keys may be present)."""

    uuid: str
    name: str
    instruction: str
    disabledAt: str | None
    needReview: bool
    behaviors: list[dict[str, Any]]
    dataSourceIds: list[str]


class AgentServiceResult(TypedDict):
    agent_uuid: str
    message: str


class AutomationServiceResult(TypedDict):
    automation_id: str
    message: str


class ToggleAgentStatusResult(TypedDict):
    success: Literal[True]
    message: str


class MePayload(TypedDict):
    """Authenticated user identity returned by the GraphQL ``me`` query.

    ``name`` is nullable in the Pipefy schema (verified via introspection).
    """

    email: str
    name: str | None


class LlmProviderPayload(TypedDict, total=False):
    """One provider node from the LLM provider union (custom or system).

    Covers both union members: ``__typename``/``type`` discriminate (custom =
    ``LlmProvider``/``byom``, system = ``SystemLlmProvider``/``system``).
    System-only keys (``systemDefault``, ``state``, ``aiCredits``,
    ``deprecationDate``, ``description``) and the custom-only ``active`` are
    present only for their member. ``configuration`` is a JSON object with
    secret values redacted server-side (placeholders, not real secrets).
    """

    __typename: str
    id: str
    name: str | None
    type: str
    active: bool
    organizationDefault: bool
    systemDefault: bool
    state: str
    description: str | None
    aiCredits: int
    deprecationDate: str | None
    configuration: dict[str, Any]


class LlmProvidersResult(TypedDict):
    """Unwrapped page of the organization's LLM providers with paging cursor."""

    providers: list[LlmProviderPayload]
    page_info: dict[str, Any] | None


class ProviderDependencyPayload(TypedDict, total=False):
    """One dependent of a provider: an owner that references it."""

    ownerId: str
    ownerType: str


class ProviderDependenciesResult(TypedDict):
    """Unwrapped page of a provider's dependents with paging cursor and total."""

    dependencies: list[ProviderDependencyPayload]
    page_info: dict[str, Any] | None
    total_count: int | None


class ProviderAccessProbeResult(TypedDict, total=False):
    """Outcome of the LLM-provider read-access probe.

    ``ok`` is True when the list query succeeded (proves *read* access only,
    never write entitlement). On success, ``system_providers_visible`` reports
    whether any Pipefy-managed system provider was returned; when False,
    Pipefy-managed system models may simply not be enabled for the organization
    rather than access being denied. On failure, ``problem`` carries the
    classified GraphQL problem (kind/message/code/correlation_id).
    """

    ok: bool
    system_providers_visible: bool
    custom_providers_visible: bool
    provider_count: int
    note: str
    problem: dict[str, Any]
