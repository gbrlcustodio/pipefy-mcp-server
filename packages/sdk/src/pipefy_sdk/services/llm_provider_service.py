"""Service for LLM provider discovery reads, custom-provider writes, and the probe.

Custom (BYOM) provider configuration is secret-bearing (API keys, cloud
credentials). It is read from a local JSON file rather than passed inline so it
never becomes a logged tool argument, and it is never echoed back: the create
and update mutations do not select ``configuration``, and file-read/parse errors
report only the path and a structural reason, never file contents. Value-level
validation (vendor/model membership, live credential test calls) happens
server-side; this layer treats the configuration as an opaque, non-empty JSON
object and does not couple to the vendor schema.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.graphql_problem import (
    GraphQLProblem,
    GraphQLProblemKind,
    classify_graphql_error_dicts,
)
from pipefy_sdk.queries.llm_provider_queries import (
    CREATE_LLM_PROVIDER_MUTATION,
    DELETE_LLM_PROVIDER_MUTATION,
    GET_AVAILABLE_AI_MODELS_QUERY,
    GET_DEFAULT_LLM_PROVIDER_QUERY,
    GET_LLM_PROVIDERS_QUERY,
    GET_PROVIDER_DEPENDENCIES_QUERY,
    RESET_LLM_PROVIDER_OWNER_MUTATION,
    SET_ACTIVE_LLM_PROVIDER_MUTATION,
    SET_LLM_PROVIDER_ACTIVE_STATUS_MUTATION,
    UPDATE_LLM_PROVIDER_MUTATION,
)
from pipefy_sdk.services.types import (
    ActiveLlmProviderPayload,
    LlmProviderMutationResult,
    LlmProviderPayload,
    LlmProvidersResult,
    LlmProviderWritePayload,
    ProviderAccessProbeResult,
    ProviderDependenciesResult,
)
from pipefy_sdk.utils.relay import unwrap_relay_connection_nodes

DEFAULT_PROVIDER_PAGE_SIZE = 50

# Default assignment (set/reset) is organization-scoped in this toolkit: the
# owner is always the organization (ownerId = numeric organization id, which the
# setActiveLlmProvider / resetLlmProviderOwner inputs require). set-active-status
# takes no owner/org argument by contrast because its mutation resolves the org
# server-side from the credential. The assistant/behavior owner scopes the API
# also supports are out of scope here.
_ORGANIZATION_OWNER_TYPE = "organization"

# A generous sanity cap on the configuration file; real provider configs are a
# few hundred bytes. Guards against accidentally reading a huge file.
MAX_CONFIGURATION_FILE_BYTES = 256 * 1024

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


def _read_configuration_object(configuration_file_path: str | Path) -> dict[str, Any]:
    """Read and parse the provider configuration JSON file.

    Returns the parsed top-level object. Every error reports only the file path
    and a structural reason (missing file, too large, invalid JSON, non-object)
    — never the file contents — so a secret in the file is never echoed in an
    error message, log, or traceback surfaced to the caller.

    Raises:
        ValueError: On an unreadable/oversized file, invalid JSON/encoding, or a
            top-level value that is not a non-empty JSON object.
    """
    display = str(configuration_file_path)
    path = Path(configuration_file_path).expanduser()
    try:
        # Check the size before reading so an oversized file is rejected up front
        # rather than pulled fully into memory.
        if path.stat().st_size > MAX_CONFIGURATION_FILE_BYTES:
            raise ValueError(
                f"Configuration file {display!r} exceeds "
                f"{MAX_CONFIGURATION_FILE_BYTES} bytes."
            )
        raw = path.read_bytes()
    except OSError as exc:
        reason = exc.strerror or exc.__class__.__name__
        raise ValueError(
            f"Could not read configuration file {display!r}: {reason}."
        ) from exc
    try:
        parsed = json.loads(raw)
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Configuration file {display!r} is not valid UTF-8 text."
        ) from exc
    except json.JSONDecodeError as exc:
        # exc carries only a position (line/column), never the offending value.
        raise ValueError(
            f"Configuration file {display!r} is not valid JSON "
            f"(line {exc.lineno}, column {exc.colno})."
        ) from exc
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("Provider configuration must be a non-empty JSON object.")
    return parsed


def _unwrap_llm_provider(
    response: dict[str, Any], mutation_key: str
) -> LlmProviderWritePayload:
    """Unwrap a create/update mutation's provider; a missing payload is failure.

    A write that returns no GraphQL errors but a null ``llmProvider`` must not
    read as success — the caller cannot know whether it persisted.
    """
    payload = response.get(mutation_key)
    if isinstance(payload, dict):
        provider = payload.get("llmProvider")
        if isinstance(provider, dict) and provider:
            return provider
    raise ValueError(
        f"{mutation_key} returned no provider payload; "
        "the write may not have persisted."
    )


def _unwrap_active_provider(
    response: dict[str, Any], mutation_key: str
) -> ActiveLlmProviderPayload:
    """Unwrap ``setActiveLlmProvider``'s assignment; a missing payload is failure."""
    payload = response.get(mutation_key)
    if isinstance(payload, dict):
        active = payload.get("activeLlmProvider")
        if isinstance(active, dict) and active:
            return active
    raise ValueError(
        f"{mutation_key} returned no active-provider payload; "
        "the assignment may not have persisted."
    )


def _mutation_success(
    response: dict[str, Any], mutation_key: str
) -> LlmProviderMutationResult:
    """Project a ``success``-boolean mutation payload onto the shared result.

    A null/absent ``success`` (with no GraphQL errors raised upstream) is read as
    failure, so an ambiguous response never presents as a confirmed success.
    """
    payload = response.get(mutation_key)
    payload = payload if isinstance(payload, dict) else {}
    return {"success": bool(payload.get("success"))}


class LlmProviderService:
    """LLM provider discovery reads, custom-provider writes, and the access probe."""

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

    async def create_llm_provider(
        self,
        organization_uuid: str,
        *,
        name: str,
        configuration_file_path: str | Path,
    ) -> LlmProviderWritePayload:
        """Create a custom (BYOM) LLM provider for an organization.

        Configuration is read from a local JSON file (never inline) and sent as
        the ``configuration`` object. The returned provider never includes
        configuration (secrets are never echoed). Vendor/model membership and
        credential validity are enforced server-side (the backend runs live
        credential test calls), so an invalid key or model surfaces as a backend
        rejection, not a client-side error.

        Args:
            organization_uuid: Organization UUID (not the numeric id).
            name: Display name (required, non-blank).
            configuration_file_path: Local path to a JSON file holding the
                provider configuration object (``~`` is expanded). Must contain
                a non-empty JSON object; the ``provider`` key selects the vendor.

        Returns:
            The created provider (``id``, ``name``, ``type``, ``active``,
            ``organizationDefault``).
        """
        # Validate the cheap args before the file I/O so a blank name/org fails
        # fast without reading and parsing the configuration.
        organization_uuid = _require_non_blank(organization_uuid, "organization_uuid")
        name = _require_non_blank(name, "name")
        configuration = await asyncio.to_thread(
            _read_configuration_object, configuration_file_path
        )
        input_obj = {
            "organizationUuid": organization_uuid,
            "name": name,
            "configuration": configuration,
        }
        response = await self._executor.execute_query(
            CREATE_LLM_PROVIDER_MUTATION, {"input": input_obj}
        )
        return _unwrap_llm_provider(response, "createLlmProvider")

    async def update_llm_provider(
        self,
        provider_id: str,
        organization_uuid: str,
        *,
        configuration_file_path: str | Path,
        name: str | None = None,
    ) -> LlmProviderWritePayload:
        """Update a custom (BYOM) LLM provider (full configuration replacement).

        ``configuration`` is required on every call (the API contract): read the
        complete configuration object from a local JSON file and send it. To keep
        an existing secret without re-supplying it, leave the redacted
        placeholder (as returned by ``get_llm_providers``) in place — the backend
        preserves the stored secret for any value left as the placeholder. To
        rotate a secret, put its new real value in the file.

        Args:
            provider_id: Provider id to update (custom/BYOM only).
            organization_uuid: Organization UUID (not the numeric id).
            configuration_file_path: Local path to a JSON file holding the
                complete provider configuration object (``~`` is expanded).
            name: New display name (optional; non-blank when given).

        Returns:
            The updated provider (never includes configuration).
        """
        # Validate the cheap args before the file I/O (see create_llm_provider).
        input_obj: dict[str, Any] = {
            "id": _require_non_blank(provider_id, "provider_id"),
            "organizationUuid": _require_non_blank(
                organization_uuid, "organization_uuid"
            ),
        }
        if name is not None:
            input_obj["name"] = _require_non_blank(name, "name")
        input_obj["configuration"] = await asyncio.to_thread(
            _read_configuration_object, configuration_file_path
        )
        response = await self._executor.execute_query(
            UPDATE_LLM_PROVIDER_MUTATION, {"input": input_obj}
        )
        return _unwrap_llm_provider(response, "updateLlmProvider")

    async def delete_llm_provider(
        self, provider_id: str, organization_uuid: str
    ) -> LlmProviderMutationResult:
        """Delete a custom (BYOM) LLM provider (permanent).

        Args:
            provider_id: Provider id to delete.
            organization_uuid: Organization UUID (not the numeric id).

        Returns:
            ``success`` (True when the backend confirmed the delete).
        """
        input_obj = {
            "id": _require_non_blank(provider_id, "provider_id"),
            "organizationUuid": _require_non_blank(
                organization_uuid, "organization_uuid"
            ),
        }
        response = await self._executor.execute_query(
            DELETE_LLM_PROVIDER_MUTATION, {"input": input_obj}
        )
        return _mutation_success(response, "deleteLlmProvider")

    async def set_llm_provider_active_status(
        self, provider_id: str, *, active: bool
    ) -> LlmProviderMutationResult:
        """Activate or deactivate a custom (BYOM) LLM provider.

        The provider's organization is resolved from the credential's own
        organization context, so no organization argument is needed — this
        therefore requires a service-account credential bound to that organization
        (a bare personal token is denied).

        Args:
            provider_id: Provider id whose active status to set.
            active: ``True`` to activate, ``False`` to deactivate.

        Returns:
            ``success`` (True when the backend confirmed the change).
        """
        input_obj = {
            "providerId": _require_non_blank(provider_id, "provider_id"),
            "active": bool(active),
        }
        response = await self._executor.execute_query(
            SET_LLM_PROVIDER_ACTIVE_STATUS_MUTATION, {"input": input_obj}
        )
        return _mutation_success(response, "setLlmProviderActiveStatus")

    async def set_default_llm_provider(
        self,
        organization_id: str,
        *,
        provider_id: str | None = None,
        system_provider_id: str | None = None,
    ) -> ActiveLlmProviderPayload:
        """Set the organization's default LLM provider.

        Organization-scoped: the owner is always the organization. Provide
        exactly one of ``provider_id`` (a custom/BYOM provider) or
        ``system_provider_id`` (a Pipefy-managed system provider). Authorizes
        against the credential's own organization context, so it requires a
        service-account credential bound to that organization (a bare personal
        token is denied), and ``organization_id`` must be that organization's id.

        Args:
            organization_id: Numeric organization id (not the UUID) — the owner
                id, matching the ``get_default_llm_provider`` read convention.
            provider_id: Custom provider id to make default.
            system_provider_id: System provider id to make default.

        Returns:
            The owner→provider assignment (exactly one of ``llmProviderId`` /
            ``systemLlmProviderId`` is populated).

        Raises:
            ValueError: When not exactly one of ``provider_id`` /
                ``system_provider_id`` is given.
        """
        pid = (provider_id or "").strip()
        sid = (system_provider_id or "").strip()
        if bool(pid) == bool(sid):
            raise ValueError(
                "Provide exactly one of provider_id or system_provider_id."
            )
        input_obj: dict[str, Any] = {
            "ownerId": _require_non_blank(organization_id, "organization_id"),
            "ownerType": _ORGANIZATION_OWNER_TYPE,
        }
        if pid:
            input_obj["providerId"] = pid
        else:
            input_obj["systemProviderId"] = sid
        response = await self._executor.execute_query(
            SET_ACTIVE_LLM_PROVIDER_MUTATION, {"input": input_obj}
        )
        return _unwrap_active_provider(response, "setActiveLlmProvider")

    async def reset_default_llm_provider(
        self, organization_id: str
    ) -> LlmProviderMutationResult:
        """Reset (clear) the organization's default LLM provider assignment.

        Authorizes against the credential's own organization context (like
        ``set_default_llm_provider``), so it requires a service-account credential
        bound to that organization; a bare personal token is denied.

        Args:
            organization_id: Numeric organization id (not the UUID).

        Returns:
            ``success`` (True when the backend confirmed the reset).
        """
        input_obj = {
            "ownerId": _require_non_blank(organization_id, "organization_id"),
            "ownerType": _ORGANIZATION_OWNER_TYPE,
        }
        response = await self._executor.execute_query(
            RESET_LLM_PROVIDER_OWNER_MUTATION, {"input": input_obj}
        )
        return _mutation_success(response, "resetLlmProviderOwner")
