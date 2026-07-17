"""Service for LLM provider discovery reads and the read-access probe."""

from __future__ import annotations

from typing import Any

from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.graphql_problem import (
    GraphQLProblem,
    GraphQLProblemKind,
    classify_graphql_error_dicts,
)
from pipefy_sdk.queries.llm_provider_queries import (
    GET_AVAILABLE_AI_MODELS_QUERY,
    GET_DEFAULT_LLM_PROVIDER_QUERY,
    GET_LLM_PROVIDERS_QUERY,
    GET_PROVIDER_DEPENDENCIES_QUERY,
)
from pipefy_sdk.services.types import (
    LlmProviderPayload,
    LlmProvidersResult,
    ProviderAccessProbeResult,
    ProviderDependenciesResult,
)
from pipefy_sdk.utils.relay import unwrap_relay_connection_nodes

DEFAULT_PROVIDER_PAGE_SIZE = 50

_PROBE_FEATURE_NOTE = (
    "No system providers returned: the organization may not have Pipefy-managed "
    "system models enabled; this is not by itself a permission problem."
)
_PROBE_READ_ONLY_NOTE = (
    "Read access confirmed. This proves list/read access only, never write "
    "entitlement; provider mutations may still be denied."
)


def _require_non_blank(value: str, name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must be a non-empty string")
    return stripped


def _problem_dict(problem: GraphQLProblem) -> dict[str, Any]:
    """Project a classified problem onto the probe's plain-dict shape."""
    return {
        "kind": problem.kind.value,
        "message": problem.message,
        "code": problem.code,
        "correlation_id": problem.correlation_id,
    }


class LlmProviderService:
    """Read-only LLM provider discovery via GraphQL."""

    def __init__(self, *, executor: GraphQLExecutor) -> None:
        self._executor = executor

    async def get_llm_providers(
        self,
        organization_uuid: str,
        *,
        only_active: bool = False,
        first: int = DEFAULT_PROVIDER_PAGE_SIZE,
        after: str | None = None,
    ) -> LlmProvidersResult:
        """List all LLM providers available to the organization (custom + system).

        Args:
            organization_uuid: Organization UUID (not the numeric id).
            only_active: Only return active *custom* providers; system
                providers are unaffected by this filter.
            first: Page size (default 50).
            after: Cursor from the previous page's ``page_info.endCursor``.

        Returns:
            ``providers`` (union nodes; ``type`` is ``byom`` or ``system``) and
            ``page_info``. ``configuration`` comes back with secret values
            redacted server-side.
        """
        variables: dict[str, Any] = {
            "organizationUuid": _require_non_blank(
                organization_uuid, "organization_uuid"
            ),
            "onlyActiveProviders": only_active,
            "first": first,
        }
        if after is not None:
            variables["after"] = after
        response = await self._executor.execute_query(
            GET_LLM_PROVIDERS_QUERY, variables
        )
        connection = response.get("allLlmProvidersByOrganization")
        providers = unwrap_relay_connection_nodes(connection)
        page_info = connection.get("pageInfo") if isinstance(connection, dict) else None
        return {"providers": providers, "page_info": page_info}

    async def get_available_ai_models(self, provider_name: str) -> list[str]:
        """List the model names a provider vendor exposes.

        Args:
            provider_name: ProviderName enum value: ``openai``, ``azure_openai``,
                ``amazon_bedrock``, ``custom``, ``google_vertex_ai``,
                ``oracle_oci``, or ``anthropic``. The API validates membership.

        Returns:
            Model name strings (empty when the API returns null).
        """
        name = _require_non_blank(provider_name, "provider_name")
        response = await self._executor.execute_query(
            GET_AVAILABLE_AI_MODELS_QUERY, {"providerName": name}
        )
        models = response.get("availableAiModels")
        return [str(m) for m in models] if isinstance(models, list) else []

    async def get_default_llm_provider(
        self, owner_id: str, *, owner_type: str = "organization"
    ) -> LlmProviderPayload:
        """Resolve the default LLM provider for one owner.

        Args:
            owner_id: Owner identifier. For ``owner_type="organization"`` this
                is the **numeric organization id** (not the UUID).
            owner_type: OwnerProvider enum value (``organization`` (default),
                ``assistant``, or ``behavior``).

        Returns:
            The provider dict (``type`` discriminates byom/system); empty dict
            when the API resolves no default.
        """
        variables = {
            "ownerType": _require_non_blank(owner_type, "owner_type"),
            "ownerId": _require_non_blank(owner_id, "owner_id"),
        }
        response = await self._executor.execute_query(
            GET_DEFAULT_LLM_PROVIDER_QUERY, variables
        )
        provider = response.get("defaultLlmProvider")
        return provider if isinstance(provider, dict) else {}

    async def get_llm_provider_dependencies(
        self,
        provider_id: str,
        organization_uuid: str,
        *,
        first: int = DEFAULT_PROVIDER_PAGE_SIZE,
        after: str | None = None,
    ) -> ProviderDependenciesResult:
        """List the owners that depend on a provider (blockers for removal).

        Args:
            provider_id: Provider ID (as returned by ``get_llm_providers``).
            organization_uuid: Organization UUID (not the numeric id).
            first: Page size (default 50).
            after: Cursor from the previous page's ``page_info.endCursor``.

        Returns:
            ``dependencies`` (``ownerId``/``ownerType`` pairs), ``page_info``,
            and ``total_count``.
        """
        variables: dict[str, Any] = {
            "providerId": _require_non_blank(provider_id, "provider_id"),
            "organizationUuid": _require_non_blank(
                organization_uuid, "organization_uuid"
            ),
            "first": first,
        }
        if after is not None:
            variables["after"] = after
        response = await self._executor.execute_query(
            GET_PROVIDER_DEPENDENCIES_QUERY, variables
        )
        connection = response.get("providerDependencies")
        dependencies = unwrap_relay_connection_nodes(connection)
        page_info = connection.get("pageInfo") if isinstance(connection, dict) else None
        total_count = (
            connection.get("totalCount") if isinstance(connection, dict) else None
        )
        return {
            "dependencies": dependencies,
            "page_info": page_info,
            "total_count": total_count,
        }

    async def validate_llm_provider_access(
        self, organization_uuid: str
    ) -> ProviderAccessProbeResult:
        """Probe LLM provider *read* access for an organization.

        Runs the provider list query (one default-size page; the API orders
        system providers before custom ones, so the first page is authoritative
        for system-provider visibility) through the partial-success executor
        and classifies any GraphQL errors instead of raising.
        A green result proves read access only, never write entitlement, and an
        empty system-provider list can mean the feature is not enabled for the
        organization rather than a permission problem — both facts are spelled
        out in ``note``.

        Note: the list query is gated by a weaker permission than the
        models/default/dependencies reads, which require provider-management
        rights; a green probe does not guarantee those three succeed.
        """
        org_uuid = _require_non_blank(organization_uuid, "organization_uuid")
        variables = {
            "organizationUuid": org_uuid,
            "onlyActiveProviders": False,
            "first": DEFAULT_PROVIDER_PAGE_SIZE,
        }
        result = await self._executor.execute(GET_LLM_PROVIDERS_QUERY, variables)
        connection = result.data.get("allLlmProvidersByOrganization")
        if connection is None:
            problem = classify_graphql_error_dicts(result.errors)
            if problem is None:
                problem_dict: dict[str, Any] = {
                    "kind": GraphQLProblemKind.RUNTIME.value,
                    "message": "Query returned no data and no errors.",
                }
            else:
                problem_dict = _problem_dict(problem)
            return {"ok": False, "problem": problem_dict}

        providers = unwrap_relay_connection_nodes(connection)
        system_visible = any(p.get("type") == "system" for p in providers)
        custom_visible = any(p.get("type") == "byom" for p in providers)
        note = _PROBE_READ_ONLY_NOTE
        if not system_visible:
            note = f"{note} {_PROBE_FEATURE_NOTE}"
        probe: ProviderAccessProbeResult = {
            "ok": True,
            "system_providers_visible": system_visible,
            "custom_providers_visible": custom_visible,
            "provider_count": len(providers),
            "note": note,
        }
        # A response can carry readable data alongside per-node errors; a green
        # probe still surfaces them so partial denial is never read as full access.
        partial = classify_graphql_error_dicts(result.errors)
        if partial is not None:
            probe["note"] = (
                f"{probe['note']} The response also carried GraphQL errors; "
                "see problem."
            )
            probe["problem"] = _problem_dict(partial)
        return probe
