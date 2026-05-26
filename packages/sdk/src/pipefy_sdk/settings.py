from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import NoDecode

# Canonical Pipefy production GraphQL endpoint. Used as the default when
# ``PIPEFY_GRAPHQL_URL`` is not set in the environment — override by setting
# the env var (or passing ``graphql_url`` explicitly to ``PipefySettings``).
DEFAULT_GRAPHQL_URL = "https://app.pipefy.com/graphql"


class PipefySettings(BaseModel):
    """Pipefy API connection and shared runtime knobs (MCP, CLI, scripts).

    Endpoint configuration only — credentials live on
    :class:`pipefy_auth.AuthSettings`. Consumers compose both side by side in
    their own settings type.
    """

    allow_insecure_urls: bool = Field(
        default=False,
        description=(
            "When true (env: PIPEFY_ALLOW_INSECURE_URLS), GraphQL/auth/internal API URLs "
            "may use http:// and internal hosts; local development only; do not enable in production."
        ),
    )

    graphql_url: str | None = Field(
        default=DEFAULT_GRAPHQL_URL,
        description=(
            "Pipefy GraphQL endpoint (env: PIPEFY_GRAPHQL_URL; defaults to the "
            f"Pipefy production API at {DEFAULT_GRAPHQL_URL}). Set to an empty "
            "string to opt out on hosts that need to require an explicit value."
        ),
    )

    internal_api_url: str = Field(
        default="https://app.pipefy.com/internal_api",
        description="Internal API URL for AI Automation endpoints",
    )

    interfaces_graphql_url: str = Field(
        default="https://app.pipefy.com/graphql/interfaces",
        description="GraphQL URL for Pipefy Interfaces schema (portals, pages, elements)",
    )

    org_id: str | None = Field(
        default=None,
        description=(
            "Optional default organization id (numeric string) for CLI commands that "
            "allow an implicit org, e.g. ``pipefy org get`` when the id argument is "
            "omitted (env: PIPEFY_ORG_ID)."
        ),
    )

    service_account_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description=(
            "Pipefy user IDs for service accounts: protected from removal in member tools; "
            "used for proactive cross-pipe membership checks in validate_ai_agent_behaviors."
        ),
    )

    permission_denied_enrichment_timeout_seconds: float = Field(
        default=5.0,
        ge=0.1,
        le=120.0,
        description=(
            "Max wall time (seconds) for membership lookups when enriching GraphQL "
            "PERMISSION_DENIED errors (env: PIPEFY_PERMISSION_DENIED_ENRICHMENT_TIMEOUT_SECONDS)."
        ),
    )

    gql_reuse_fetched_graphql_schema: bool = Field(
        default=False,
        description=(
            "When true (env: PIPEFY_GQL_REUSE_FETCHED_GRAPHQL_SCHEMA), the first GraphQL "
            "request per BasePipefyClient fetches the remote schema via introspection, "
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

    mcp_unified_envelope: bool = Field(
        default=True,
        description=(
            "When true (env: PIPEFY_MCP_UNIFIED_ENVELOPE), migrated MCP tools return "
            "{success, data, message?, pagination?}. When false, legacy shapes. "
            "Read at call time, not cached at import."
        ),
    )

    @field_validator("service_account_ids", mode="before")
    @classmethod
    def _coerce_service_account_ids(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        msg = "service_account_ids must be a list or a comma-separated string"
        raise ValueError(msg)

    @model_validator(mode="after")
    def _validate_pipefy_endpoint_urls(self) -> Self:
        # Deferred import: ``url_ssrf`` validates URLs that may reference settings types (cycle if top-level).
        from pipefy_sdk.utils.url_ssrf import validate_https_service_endpoint_url

        allow = self.allow_insecure_urls
        if self.graphql_url is not None and (u := self.graphql_url.strip()):
            validate_https_service_endpoint_url(u, "graphql_url", allow_insecure=allow)
        if u := self.internal_api_url.strip():
            validate_https_service_endpoint_url(
                u, "internal_api_url", allow_insecure=allow
            )
        if u := self.interfaces_graphql_url.strip():
            validate_https_service_endpoint_url(
                u, "interfaces_graphql_url", allow_insecure=allow
            )
        return self
