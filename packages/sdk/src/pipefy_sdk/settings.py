"""Pure value object for SDK runtime configuration.

:class:`SdkConfig` is a plain :class:`pydantic.BaseModel`: it validates itself
but reads no env / file. Endpoint topology and insecure-URL posture live on the
injected :class:`~pipefy_infra.deployment.DeploymentConfig` (the one instance the
application edge shares across SDK and auth); the URLs and posture are forwarded
off it so consumers (``build_executors``, ``WebhookService``) read them off the
SDK config unchanged. ``gql_reuse_fetched_graphql_schema`` and
``default_webhook_name`` are the SDK's own runtime knobs.

The application edge owns env reading (it subclasses this model into a
``pydantic-settings`` reader and injects ``deployment``); this module imports no
``pydantic-settings`` so the SDK stays env-free.
"""

from __future__ import annotations

from pipefy_infra.deployment import DeploymentConfig
from pydantic import BaseModel, Field


class SdkConfig(BaseModel):
    """Pipefy API connection (injected) plus shared SDK runtime knobs.

    ``deployment`` is required and injected by the application edge; the
    forwarding properties keep the prior ``settings.graphql_url`` /
    ``settings.allow_insecure_urls`` call sites working without those consumers
    reaching into ``settings.deployment``.
    """

    deployment: DeploymentConfig = Field(
        description=(
            "Host topology + insecure-URL posture, injected by reference from the "
            "one DeploymentConfig the application edge builds (shared with auth)."
        ),
    )

    gql_reuse_fetched_graphql_schema: bool = Field(
        default=False,
        description=(
            "When true (env: PIPEFY_GQL_REUSE_FETCHED_GRAPHQL_SCHEMA), the first GraphQL "
            "request per HttpxGraphQLExecutor fetches the remote schema via introspection, "
            "caches the GraphQLSchema in memory, and later requests reuse it so gql does "
            "not repeat the introspection round-trip. Default false avoids extra work and "
            "keeps a cold process fast; enable if profiling shows significant duplicate "
            "introspection (unlikely while fetch_schema_from_transport is off by default). "
            "Restart the process after a breaking Pipefy schema change."
        ),
    )

    default_webhook_name: str = Field(
        default="Pipefy Webhook",
        min_length=1,
        max_length=255,
        description=(
            "Default ``name`` for create_webhook when the caller does not set one "
            "(env: PIPEFY_DEFAULT_WEBHOOK_NAME)."
        ),
    )

    @property
    def graphql_url(self) -> str:
        """Pipefy GraphQL endpoint (forwarded from ``deployment``)."""
        return self.deployment.graphql_url

    @property
    def internal_api_url(self) -> str:
        """Internal API endpoint for AI Automation (forwarded from ``deployment``)."""
        return self.deployment.internal_api_url

    @property
    def interfaces_graphql_url(self) -> str:
        """Interfaces GraphQL endpoint (forwarded from ``deployment``)."""
        return self.deployment.interfaces_graphql_url

    @property
    def allow_insecure_urls(self) -> bool:
        """Shared insecure-URL posture (forwarded from ``deployment``)."""
        return self.deployment.allow_insecure_urls


__all__ = ["SdkConfig"]
