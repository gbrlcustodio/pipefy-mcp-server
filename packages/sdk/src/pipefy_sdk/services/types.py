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


class KnowledgeBasePayload(TypedDict, total=False):
    """One item from the pipe's knowledge base list (``aiKnowledgeBases``).

    ``type`` is the JSON:API resource type carried through from the backend
    (e.g. ``knowledge_base_plain_texts``, ``knowledge_base_documents``,
    ``data_lookups``); it can be null. ``id`` is the data-source UUID used to
    attach the source to an agent/behavior via ``dataSourceIds``.
    """

    id: str
    type: str | None
    name: str
    description: str | None
    updatedAt: str | None


class KnowledgeBasePlainTextPayload(TypedDict, total=False):
    """A single pipe-scoped knowledge base plain text.

    Returned by the get query and by create/update. ``content`` and ``name`` are
    always present (non-null in the schema); ``description`` may be null only on
    legacy rows — new writes always carry one (see the write validators).
    """

    id: str
    name: str
    description: str | None
    content: str
    updatedAt: str | None


class KnowledgeBaseDeleteResult(TypedDict):
    """Outcome of ``deleteAiKnowledgeBasePlainText``."""

    success: bool
    errors: list[str]


class KnowledgeBaseDocumentPayload(TypedDict, total=False):
    """A single pipe-scoped knowledge base document.

    Returned by the get query and by create/update. ``content`` is the stored
    document URL (the persistent download URL the file was uploaded to), not the
    extracted text; it may be null on legacy rows. ``description`` is required on
    write (the backing ``DataSource`` model enforces presence) but may be null on
    legacy rows.
    """

    id: str
    name: str
    description: str | None
    content: str | None
    updatedAt: str | None


class KnowledgeBaseDataLookupPayload(TypedDict, total=False):
    """A single pipe-scoped knowledge base data lookup.

    Returned by the get query and by create/update. ``conditions`` are never
    part of the payload: the API stores them but does not expose them on
    reads, so callers must keep the lookup definition client-side.
    ``sourceRepoId`` is the numeric ID of the source pipe.
    """

    id: str
    name: str
    description: str | None
    sourceRepoId: str | None
    searchQuery: str | None
    outputFields: list[str] | None
    updatedAt: str | None


KnowledgeBaseDocumentUploadStep = Literal[
    "file_read",
    "presigned_url",
    "s3_upload",
    "kb_create",
]


class KnowledgeBaseDocumentUploadError(Exception):
    """Raised on knowledge base document upload pipeline failure.

    The ``step`` attribute identifies which stage failed (``file_read`` reads and
    validates the local PDF, ``presigned_url`` resolves the org and mints the
    upload URL, ``s3_upload`` PUTs the bytes, ``kb_create`` runs the create
    mutation) so surfaces can map it to a step-aware error envelope (MCP) or
    typer message (CLI) without parsing strings.
    """

    def __init__(
        self,
        message: str,
        *,
        step: KnowledgeBaseDocumentUploadStep,
        body_snippet: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.step = step
        self.body_snippet = body_snippet
        self.status_code = status_code
        super().__init__(message)


class KnowledgeBaseAccessProbeResult(TypedDict, total=False):
    """Outcome of the knowledge-base read-access probe (pipe-scoped).

    ``ok`` is True when the list query succeeded (proves *read* access only —
    ``read_ai_agents`` on the pipe — never the ``manage_ai_agents`` entitlement
    that knowledge base create/update/delete require). ``knowledge_base_count`` is
    the number of items visible on the pipe. On failure, ``problem`` carries the
    classified GraphQL problem (kind/message/code/correlation_id).
    """

    ok: bool
    knowledge_base_count: int
    note: str
    problem: dict[str, Any]
