"""GraphQL client for Pipefy's internal_api endpoint.

A thin :class:`pipefy_sdk.base_client.BasePipefyClient` subclass. The only real
difference from the public-API client is the error envelope: each GraphQL error
is decorated with ``[code=...]`` / ``[correlation_id=...]`` suffixes drawn from
``extensions``. Service-layer tests assert the fully suffixed text.
"""

from __future__ import annotations

from httpx import Auth

from pipefy_sdk.base_client import BasePipefyClient
from pipefy_sdk.settings import PipefySettings


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
    """GraphQL client for Pipefy's internal_api endpoint.

    Used for mutations only available on the internal schema (card-relation
    deletion, portal sub-portals). Accepts already-parsed ``gql()``
    ``DocumentNode`` queries like every other client; the only behavioral
    difference from the public-API client is the error envelope built by
    ``_format_internal_api_error``.
    """

    def __init__(self, settings: PipefySettings, *, auth: Auth) -> None:
        """Create an internal API client.

        Args:
            settings: Pipefy endpoints and credentials, shared with the other
                endpoint clients. ``settings.internal_api_url`` (derived from
                ``base_url``, which the settings model validated for HTTPS and
                host-root shape at construction) targets the internal_api
                endpoint, so no per-client URL re-validation is needed here.
            auth: Pre-constructed ``httpx.Auth`` (e.g. from ``pipefy_auth.resolve``).
        """
        super().__init__(
            settings,
            auth=auth,
            url_override=settings.internal_api_url,
            on_graphql_error=_format_internal_api_error,
        )
