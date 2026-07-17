"""MCP tools for LLM provider discovery (read-only) and the access probe."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pipefy_sdk import classify_exception

from pipefy_mcp.core.tool_error_envelope import (
    is_unified_envelope_enabled,
    tool_error,
    tool_success,
)
from pipefy_mcp.tools.pagination_helpers import (
    build_pagination_info,
    validate_page_size,
)
from pipefy_mcp.tools.tool_context import get_pipefy_client
from pipefy_mcp.tools.validation_helpers import validate_tool_id

_PROVIDER_ID_DISCOVERY_HINT = (
    "Use 'get_llm_providers' to list provider IDs for the organization."
)


def _provider_tool_error_from_exception(exc: BaseException) -> dict[str, Any]:
    """Map an SDK/GraphQL exception onto the canonical tool failure envelope.

    Uses the shared SDK classifier (``pipefy_sdk.classify_exception``) so the
    kind/code the CLI and probes see is the same one reported here. A
    transport-level failure with no GraphQL errors falls back to ``str(exc)``.
    """
    problem = classify_exception(exc)
    if problem is None:
        return tool_error(str(exc))
    message = problem.message
    if problem.kind.value == "not_found":
        message = f"{message} {_PROVIDER_ID_DISCOVERY_HINT}"
    details: dict[str, Any] = {"kind": problem.kind.value}
    if problem.correlation_id:
        details["correlation_id"] = problem.correlation_id
    return tool_error(message, code=problem.code, details=details)


def _blank_error(value: str, field: str) -> dict[str, Any] | None:
    if not value.strip():
        return tool_error(f"'{field}' must be non-empty.")
    return None


def _read_success(
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
    """Declares MCP tools for LLM provider discovery reads and the access probe."""

    @staticmethod
    def register(mcp: FastMCP) -> None:
        """Register LLM provider tools on the MCP server."""

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
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
                return _provider_tool_error_from_exception(exc)
            return _read_success(
                {"providers": result["providers"]},
                message="LLM providers retrieved.",
                page_info=result["page_info"],
                page_size=nfirst,
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
        async def get_available_ai_models(
            ctx: Context,
            provider_name: str,
        ) -> dict[str, Any]:
            """List the model names an LLM provider vendor exposes (for configuring custom providers).

            Args:
                provider_name: Provider vendor enum value: `openai`, `azure_openai`,
                    `amazon_bedrock`, `custom`, `google_vertex_ai`, `oracle_oci`,
                    or `anthropic`. The API validates membership.
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(provider_name, "provider_name")
            if err is not None:
                return err
            try:
                models = await client.get_available_ai_models(provider_name.strip())
            except Exception as exc:  # noqa: BLE001
                return _provider_tool_error_from_exception(exc)
            return _read_success(
                {"models": models}, message="Available AI models retrieved."
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
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
            return _read_success(
                {"provider": provider}, message="Default LLM provider retrieved."
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
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
            return _read_success(
                {
                    "dependencies": result["dependencies"],
                    "total_count": result["total_count"],
                },
                message="LLM provider dependencies retrieved.",
                page_info=result["page_info"],
                page_size=nfirst,
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
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
                return _read_success(
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
