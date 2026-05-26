"""GraphQL client for Pipefy's internal_api endpoint.

A thin :class:`pipefy_sdk.base_client.BasePipefyClient` subclass — the only
real difference from the public-API client is the error envelope: each GraphQL
error is decorated with ``[code=…]`` / ``[correlation_id=…]`` suffixes drawn
from ``extensions``. AI-automation MCP tools strip those suffixes via
``pipefy_mcp.tools.graphql_error_helpers.strip_internal_api_diagnostic_markers``
before surfacing the message to end users; service-layer tests assert the
fully suffixed text.
"""

from __future__ import annotations

from typing import Any

from gql import gql as parse_gql
from httpx import Auth

from pipefy_sdk.base_client import BasePipefyClient
from pipefy_sdk.settings import PipefySettings
from pipefy_sdk.utils.url_ssrf import validate_https_service_endpoint_url


def _format_internal_api_error(errors: list[dict]) -> str:
    parts: list[str] = []
    for err in errors:
        msg = err.get("message", "Unknown error")
        ext = err.get("extensions", {})
        code = ext.get("code", "")
        corr = ext.get("correlation_id", "")
        suffix = f" [code={code}]" if code else ""
        suffix += f" [correlation_id={corr}]" if corr else ""
        parts.append(f"{msg}{suffix}")
    return "; ".join(parts)


class InternalApiClient(BasePipefyClient):
    """GraphQL client for Pipefy internal API (AI Automation mutations)."""

    def __init__(
        self,
        url: str,
        *,
        auth: Auth,
        allow_insecure_urls: bool = False,
    ) -> None:
        """Create an internal API client.

        Args:
            url: URL of the internal_api endpoint (e.g. https://app.pipefy.com/internal_api).
            auth: Pre-constructed ``httpx.Auth`` (e.g. from ``pipefy_auth.resolve``).
            allow_insecure_urls: When True, allow http and internal hosts.
        """
        validate_https_service_endpoint_url(
            url.strip(), "internal_api URL", allow_insecure=allow_insecure_urls
        )
        # ``url`` already SSRF-validated above; ``allow_insecure_urls=True`` on
        # the throwaway settings skips a redundant re-check. ``url_override``
        # ships the URL without building a full purpose-specific ``PipefySettings``.
        settings = PipefySettings(allow_insecure_urls=True)
        super().__init__(
            settings,
            auth=auth,
            url_override=url.strip(),
            on_graphql_error=_format_internal_api_error,
        )

    async def execute_query(  # type: ignore[override]
        self, query: str, variables: dict[str, Any]
    ) -> dict:
        return await super().execute_query(parse_gql(query), variables)
