"""MCP tools for LLM provider discovery, custom-provider writes, and the probe.

Writes (create/update/delete a custom provider, toggle active status, set/reset
the organization default) require the ``manage_ai_providers`` organization
permission and an eligible plan — a stronger entitlement than the read probe
proves. Configuration is secret-bearing and is supplied only via a local JSON
file path (never inline), so it never becomes a logged tool argument, and it is
never returned. Deletes require a two-step confirm; CLI write-gating (not these
tools) runs the probe first.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pipefy_sdk import classify_exception

from pipefy_mcp.core.tool_error_envelope import (
    is_unified_envelope_enabled,
    tool_error,
    tool_success,
)
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.graphql_error_helpers import ensure_non_empty_error_message
from pipefy_mcp.tools.pagination_helpers import (
    build_pagination_info,
    validate_page_size,
)
from pipefy_mcp.tools.remote_profile import REMOTE
from pipefy_mcp.tools.tool_context import get_pipefy_client
from pipefy_mcp.tools.validation_helpers import validate_tool_id

_PROVIDER_ID_DISCOVERY_HINT = (
    "Use 'get_llm_providers' to list provider IDs for the organization."
)

_PROVIDER_REQUEST_FAILED = (
    "LLM provider request failed. Re-read provider state before retrying; "
    "do not blind-retry."
)


def _provider_tool_error_from_exception(
    exc: BaseException, *, not_found_hint: bool = True
) -> dict[str, Any]:
    """Map an SDK/GraphQL exception onto the canonical tool failure envelope.

    Uses the shared SDK classifier (``pipefy_sdk.classify_exception``) so the
    kind/code the CLI and probes see is the same one reported here. A
    transport-level failure with no GraphQL errors falls back to ``str(exc)``
    (or a stable non-empty fallback when blank). ``not_found_hint`` scopes the
    id-discovery hint to the per-id tools; the list tool passes False so its
    own failure never tells the caller to retry the call that just failed.
    """
    problem = classify_exception(exc)
    if problem is None:
        return tool_error(
            ensure_non_empty_error_message(str(exc), _PROVIDER_REQUEST_FAILED)
        )
    message = problem.message
    if not_found_hint and problem.kind.value == "not_found":
        message = f"{message} {_PROVIDER_ID_DISCOVERY_HINT}"
    details: dict[str, Any] = {"kind": problem.kind.value}
    if problem.correlation_id:
        details["correlation_id"] = problem.correlation_id
    return tool_error(
        ensure_non_empty_error_message(message, _PROVIDER_REQUEST_FAILED),
        code=problem.code,
        details=details,
    )


def _blank_error(value: str, field: str) -> dict[str, Any] | None:
    if not value.strip():
        return tool_error(f"'{field}' must be non-empty.")
    return None


def _provider_success(
    data: dict[str, Any],
    *,
    message: str,
    page_info: dict[str, Any] | None = None,
    page_size: int | None = None,
) -> dict[str, Any]:
    """Unified-envelope success (legacy flat payload when the flag is off).

    The legacy path keeps ``page_info`` in the payload so flag-off clients can
    still page (the unified path carries it as the ``pagination`` block).
    """
    if is_unified_envelope_enabled():
        pagination = (
            build_pagination_info(page_info=page_info, page_size=page_size)
            if page_size is not None
            else None
        )
        return tool_success(data=data, message=message, pagination=pagination)
    legacy: dict[str, Any] = {"success": True, **data}
    if page_size is not None:
        legacy["page_info"] = page_info
    return legacy


class LlmProviderTools:
    """Declares MCP tools for LLM provider discovery, writes, and the access probe."""

    @staticmethod
    def register(mcp: MCPServer) -> None:
        """Register LLM provider tools on the MCP server."""

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), meta=REMOTE)
        async def get_llm_providers(
            ctx: Context,
            organization_uuid: str,
            only_active: bool = False,
            first: int = 50,
            after: str | None = None,
        ) -> dict[str, Any]:
            """List all LLM providers available to an organization: custom (BYOM) and Pipefy-managed system providers in one surface. Use this to discover the `providerId` / `systemProviderId` values that AI agent behaviors accept.

            Each provider carries `type` (`byom` = custom, `system` = Pipefy-managed)
            and `configuration`; the API redacts secret values server-side, so
            placeholders come back instead of secrets. An empty system-provider list
            can mean Pipefy-managed system models are not enabled for the
            organization, not that access was denied.

            Args:
                organization_uuid: Organization UUID (not the numeric ID; `get_organization` returns both).
                only_active: Only return active custom providers (system providers are unaffected).
                first: Page size (default 50).
                after: Cursor from a previous page's pagination `end_cursor`.
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(organization_uuid, "organization_uuid")
            if err is not None:
                return err
            nfirst, page_err = validate_page_size(first)
            if page_err is not None:
                return page_err
            try:
                result = await client.get_llm_providers(
                    organization_uuid.strip(),
                    only_active=only_active,
                    first=nfirst,
                    after=after,
                )
            except Exception as exc:  # noqa: BLE001
                return _provider_tool_error_from_exception(exc, not_found_hint=False)
            return _provider_success(
                {"providers": result["providers"]},
                message="LLM providers retrieved.",
                page_info=result["page_info"],
                page_size=nfirst,
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), meta=REMOTE)
        async def get_available_ai_models(
            ctx: Context,
            provider_name: str,
        ) -> dict[str, Any]:
            """List the model names an LLM provider vendor exposes (for configuring custom providers).

            Args:
                provider_name: Provider vendor enum value: `openai`, `azure_openai`,
                    `amazon_bedrock`, `custom`, `google_vertex_ai`, `oracle_oci`,
                    or `anthropic`. The API validates membership. Snake_case here; the
                    `configuration.provider` key for `create_llm_provider` / `update_llm_provider`
                    uses the hyphenated form (`amazon-bedrock`) — not interchangeable.
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(provider_name, "provider_name")
            if err is not None:
                return err
            try:
                models = await client.get_available_ai_models(provider_name.strip())
            except Exception as exc:  # noqa: BLE001
                return _provider_tool_error_from_exception(exc)
            return _provider_success(
                {"models": models}, message="Available AI models retrieved."
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), meta=REMOTE)
        async def get_default_llm_provider(
            ctx: Context,
            owner_id: str,
            owner_type: str = "organization",
        ) -> dict[str, Any]:
            """Resolve the default LLM provider for an owner (organization by default).

            The returned provider's `type` field says whether the default is a
            custom (`byom`) or Pipefy-managed (`system`) provider. `configuration`
            comes back with secret values redacted server-side.

            Args:
                owner_id: Owner identifier. For `owner_type="organization"` pass the
                    **numeric organization ID** (not the UUID; `get_organization`
                    returns both).
                owner_type: One of `organization` (default), `assistant`, `behavior`.
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(owner_id, "owner_id") or _blank_error(
                owner_type, "owner_type"
            )
            if err is not None:
                return err
            try:
                provider = await client.get_default_llm_provider(
                    owner_id.strip(), owner_type=owner_type.strip()
                )
            except Exception as exc:  # noqa: BLE001
                return _provider_tool_error_from_exception(exc)
            return _provider_success(
                {"provider": provider}, message="Default LLM provider retrieved."
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), meta=REMOTE)
        async def get_llm_provider_dependencies(
            ctx: Context,
            provider_id: str,
            organization_uuid: str,
            first: int = 50,
            after: str | None = None,
        ) -> dict[str, Any]:
            """List the owners (organization or assistants) that depend on an LLM provider. Check this before deactivating or removing a provider.

            Args:
                provider_id: Provider ID (from `get_llm_providers`).
                organization_uuid: Organization UUID (not the numeric ID).
                first: Page size (default 50).
                after: Cursor from a previous page's pagination `end_cursor`.
            """
            client = get_pipefy_client(ctx)
            provider_id, id_err = validate_tool_id(provider_id, "provider_id")
            if id_err is not None:
                return id_err
            err = _blank_error(organization_uuid, "organization_uuid")
            if err is not None:
                return err
            nfirst, page_err = validate_page_size(first)
            if page_err is not None:
                return page_err
            try:
                result = await client.get_llm_provider_dependencies(
                    provider_id,
                    organization_uuid.strip(),
                    first=nfirst,
                    after=after,
                )
            except Exception as exc:  # noqa: BLE001
                return _provider_tool_error_from_exception(exc)
            return _provider_success(
                {
                    "dependencies": result["dependencies"],
                    "total_count": result["total_count"],
                },
                message="LLM provider dependencies retrieved.",
                page_info=result["page_info"],
                page_size=nfirst,
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), meta=REMOTE)
        async def validate_llm_provider_access(
            ctx: Context,
            organization_uuid: str,
        ) -> dict[str, Any]:
            """Probe whether the current credential can read the organization's LLM providers. A green result proves READ access only, never write entitlement; provider mutations may still be denied.

            On success, reports whether system and custom providers are visible.
            No system providers can mean Pipefy-managed system models are not
            enabled for the organization rather than a permission problem. On a
            classified failure, returns the structured problem (permission denied /
            not found / invalid arguments) instead of an opaque error.

            Clean-gate contract: a success can still carry a `problem` when the
            API returns partial data alongside GraphQL errors — the probe surfaces
            the classified error rather than discarding it and does not flip `ok`.
            Treat the gate as clean only when it is a success **and** carries no
            `problem`; a present `problem` is partial denial and must not be read
            as full access.

            Args:
                organization_uuid: Organization UUID (not the numeric ID).
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(organization_uuid, "organization_uuid")
            if err is not None:
                return err
            try:
                probe = await client.validate_llm_provider_access(
                    organization_uuid.strip()
                )
            except Exception as exc:  # noqa: BLE001
                return _provider_tool_error_from_exception(exc)
            if probe.get("ok"):
                return _provider_success(
                    dict(probe), message="LLM provider read access confirmed."
                )
            problem = probe.get("problem") or {}
            return tool_error(
                str(problem.get("message") or "LLM provider access probe failed."),
                code=problem.get("code"),
                details={
                    k: v
                    for k, v in (
                        ("kind", problem.get("kind")),
                        ("correlation_id", problem.get("correlation_id")),
                    )
                    if v
                },
            )

        # Left unmarked for the remote profile: create reads a local
        # configuration_file_path, which has no meaning on a hosted server
        # (mirrors the attachment / knowledge base document tools).
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
        )
        async def create_llm_provider(
            ctx: Context,
            organization_uuid: str,
            name: str,
            configuration_file_path: str,
        ) -> dict[str, Any]:
            """Create a custom (BYOM) LLM provider for an organization. Requires the manage_ai_providers organization permission and an eligible plan; run `validate_llm_provider_access` first (it proves read access only, so a write may still be denied).

            Configuration is read from a local JSON file — never inline — so secrets
            never become a logged argument, and the created provider is returned
            without its configuration. The `provider` key in the file selects the
            vendor (e.g. `openai`, `anthropic`, `amazon-bedrock`, `azure-openai`,
            `google-vertex-ai`, `oracle-oci`, `custom`); vendor/model validity and
            credentials are checked server-side (the backend runs a live credential
            test), so a bad key or model surfaces as a backend rejection.

            These hyphenated vendor strings are specific to this file. `get_available_ai_models`
            takes the same vendors as `provider_name` in snake_case (`amazon_bedrock`,
            `azure_openai`, `google_vertex_ai`, `oracle_oci`); do not copy a value across the
            two surfaces — a snake_case `provider` here is rejected as an invalid adapter.

            Args:
                organization_uuid: Organization UUID (not the numeric ID; `get_organization` returns both).
                name: Display name (required, non-blank).
                configuration_file_path: Local path to a JSON file holding the provider configuration object. Supports `~` expansion.
            """
            client = get_pipefy_client(ctx)
            err = (
                _blank_error(organization_uuid, "organization_uuid")
                or _blank_error(name, "name")
                or _blank_error(configuration_file_path, "configuration_file_path")
            )
            if err is not None:
                return err
            try:
                provider = await client.create_llm_provider(
                    organization_uuid.strip(),
                    name=name,
                    configuration_file_path=configuration_file_path.strip(),
                )
            except ValueError as exc:
                return tool_error(
                    ensure_non_empty_error_message(str(exc), _PROVIDER_REQUEST_FAILED)
                )
            except Exception as exc:  # noqa: BLE001
                return _provider_tool_error_from_exception(exc)
            return _provider_success(
                {"provider": provider}, message="LLM provider created."
            )

        # Left unmarked for the remote profile: update reads a local
        # configuration_file_path (see create_llm_provider).
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
        )
        async def update_llm_provider(
            ctx: Context,
            provider_id: str,
            organization_uuid: str,
            configuration_file_path: str,
            name: str | None = None,
        ) -> dict[str, Any]:
            """Update a custom (BYOM) LLM provider (full configuration replacement). Requires manage_ai_providers and an eligible plan; run `validate_llm_provider_access` first.

            `configuration` is required on every call: read the complete provider
            configuration object from a local JSON file and pass its path. To keep
            an existing secret without re-supplying it, leave the redaction
            placeholder that `get_llm_providers` returned in place — the backend
            preserves the stored secret for any value left as the placeholder. To
            rotate a secret, put its new real value in the file. The updated
            provider is returned without its configuration.

            Args:
                provider_id: Provider ID to update (custom/BYOM; from `get_llm_providers`).
                organization_uuid: Organization UUID (not the numeric ID).
                configuration_file_path: Local path to a JSON file holding the complete configuration object. Supports `~` expansion.
                name: New display name (optional; non-blank when given).
            """
            client = get_pipefy_client(ctx)
            provider_id, id_err = validate_tool_id(provider_id, "provider_id")
            if id_err is not None:
                return id_err
            err = _blank_error(organization_uuid, "organization_uuid") or _blank_error(
                configuration_file_path, "configuration_file_path"
            )
            if err is not None:
                return err
            try:
                provider = await client.update_llm_provider(
                    provider_id,
                    organization_uuid.strip(),
                    configuration_file_path=configuration_file_path.strip(),
                    name=name,
                )
            except ValueError as exc:
                return tool_error(
                    ensure_non_empty_error_message(str(exc), _PROVIDER_REQUEST_FAILED)
                )
            except Exception as exc:  # noqa: BLE001
                return _provider_tool_error_from_exception(exc)
            return _provider_success(
                {"provider": provider}, message="LLM provider updated."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
            meta=REMOTE,
        )
        async def delete_llm_provider(
            ctx: Context,
            provider_id: str,
            organization_uuid: str,
            confirm: bool = False,
        ) -> dict[str, Any]:
            """Delete a custom (BYOM) LLM provider permanently. This action is irreversible. Requires manage_ai_providers and an eligible plan.

            Two-step operation: preview with `confirm=False` (default), then execute
            with `confirm=True` after explicit human approval. Elicitation does not
            authorize deletion (only `confirm=True` does). Check
            `get_llm_provider_dependencies` first — owners that still reference the
            provider are blockers.

            Args:
                provider_id: Provider ID to delete (from `get_llm_providers`).
                organization_uuid: Organization UUID (not the numeric ID).
                confirm: Must be `True` to run the delete mutation.
            """
            client = get_pipefy_client(ctx)
            provider_id, id_err = validate_tool_id(provider_id, "provider_id")
            if id_err is not None:
                return id_err
            err = _blank_error(organization_uuid, "organization_uuid")
            if err is not None:
                return err

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"LLM provider (ID: {provider_id})",
            )
            if guard is not None:
                return guard

            try:
                result = await client.delete_llm_provider(
                    provider_id, organization_uuid.strip()
                )
            except Exception as exc:  # noqa: BLE001
                return _provider_tool_error_from_exception(exc)
            if not result.get("success"):
                return tool_error(
                    "delete_llm_provider failed: the API did not confirm the delete."
                )
            return _provider_success(
                {"deleted_id": provider_id}, message="LLM provider deleted."
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
            meta=REMOTE,
        )
        async def set_llm_provider_active_status(
            ctx: Context,
            provider_id: str,
            active: bool,
        ) -> dict[str, Any]:
            """Activate or deactivate a custom (BYOM) LLM provider. Requires manage_ai_providers and an eligible plan.

            The provider's organization is resolved from the credential's own
            organization context, so no organization argument is needed — which
            means this needs a **service-account** credential bound to that
            organization; a bare personal token is denied. Deactivating a provider
            that owners still depend on can break those owners — check
            `get_llm_provider_dependencies` first.

            Args:
                provider_id: Provider ID whose active status to set (from `get_llm_providers`).
                active: `True` to activate, `False` to deactivate.
            """
            client = get_pipefy_client(ctx)
            provider_id, id_err = validate_tool_id(provider_id, "provider_id")
            if id_err is not None:
                return id_err
            try:
                result = await client.set_llm_provider_active_status(
                    provider_id, active=active
                )
            except Exception as exc:  # noqa: BLE001
                return _provider_tool_error_from_exception(exc)
            if not result.get("success"):
                return tool_error(
                    "set_llm_provider_active_status failed: the API did not confirm "
                    "the change."
                )
            return _provider_success(
                {"provider_id": provider_id, "active": active},
                message="LLM provider active status set.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
            meta=REMOTE,
        )
        async def set_default_llm_provider(
            ctx: Context,
            organization_id: str,
            provider_id: str | None = None,
            system_provider_id: str | None = None,
        ) -> dict[str, Any]:
            """Set the organization's default LLM provider. Requires manage_ai_providers and an eligible plan.

            Organization-scoped: provide exactly one of `provider_id` (a custom/BYOM
            provider) or `system_provider_id` (a Pipefy-managed system provider) —
            passing both or neither is rejected. Authorizes against the credential's
            own organization context, so it needs a **service-account** credential
            bound to that organization (a bare personal token is denied); pass that
            same organization's numeric id.

            Args:
                organization_id: Numeric organization ID of the credential's organization (not the UUID; `get_organization` returns both).
                provider_id: Custom provider ID to make the default.
                system_provider_id: System provider ID to make the default.
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(organization_id, "organization_id")
            if err is not None:
                return err
            try:
                result = await client.set_default_llm_provider(
                    organization_id.strip(),
                    provider_id=provider_id,
                    system_provider_id=system_provider_id,
                )
            except ValueError as exc:
                return tool_error(
                    ensure_non_empty_error_message(str(exc), _PROVIDER_REQUEST_FAILED)
                )
            except Exception as exc:  # noqa: BLE001
                return _provider_tool_error_from_exception(exc)
            return _provider_success(
                {"active_provider": result},
                message="Organization default LLM provider set.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
            meta=REMOTE,
        )
        async def reset_default_llm_provider(
            ctx: Context,
            organization_id: str,
        ) -> dict[str, Any]:
            """Reset (clear) the organization's default LLM provider. Requires manage_ai_providers and an eligible plan.

            Removes the organization's default assignment; owners fall back to
            whatever default resolution applies when none is set. Reversible via
            `set_default_llm_provider`. Like `set_default_llm_provider`, this
            authorizes against the credential's own organization context, so it
            needs a **service-account** credential bound to that organization (a
            bare personal token is denied).

            Args:
                organization_id: Numeric organization ID of the credential's organization (not the UUID).
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(organization_id, "organization_id")
            if err is not None:
                return err
            try:
                result = await client.reset_default_llm_provider(
                    organization_id.strip()
                )
            except Exception as exc:  # noqa: BLE001
                return _provider_tool_error_from_exception(exc)
            if not result.get("success"):
                return tool_error(
                    "reset_default_llm_provider failed: the API did not confirm the "
                    "reset."
                )
            return _provider_success(
                {"organization_id": organization_id.strip()},
                message="Organization default LLM provider reset.",
            )
