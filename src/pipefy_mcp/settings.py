from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class PipefySettings(BaseModel):
    allow_insecure_urls: bool = Field(
        default=False,
        description=(
            "When true (env: PIPEFY_ALLOW_INSECURE_URLS), GraphQL/OAuth/internal API URLs "
            "may use http:// and internal hosts; local development only; do not enable in production."
        ),
    )

    graphql_url: str | None = Field(
        default=None,
        description="GraphQL URL for Pipefy",
    )

    internal_api_url: str = Field(
        default="https://app.pipefy.com/internal_api",
        description="Internal API URL for AI Automation endpoints",
    )

    oauth_url: str | None = Field(
        default=None,
        description="OAuth URL for Pipefy",
    )

    oauth_client: str | None = Field(
        default=None,
        description="OAuth client ID for Pipefy",
    )

    oauth_secret: str | None = Field(
        default=None,
        description="OAuth client secret for Pipefy",
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
        from pipefy_mcp.services.pipefy.utils.url_ssrf import (
            validate_https_service_endpoint_url,
        )

        allow = self.allow_insecure_urls
        if self.graphql_url is not None and (u := self.graphql_url.strip()):
            validate_https_service_endpoint_url(u, "graphql_url", allow_insecure=allow)
        if self.oauth_url is not None and (u := self.oauth_url.strip()):
            validate_https_service_endpoint_url(u, "oauth_url", allow_insecure=allow)
        if u := self.internal_api_url.strip():
            validate_https_service_endpoint_url(
                u, "internal_api_url", allow_insecure=allow
            )
        return self


class Settings(BaseSettings):
    """Application configuration via pydantic-settings.

    On import, values are read from process environment variables and from a ``.env`` file
    in the current working directory (see ``env_file`` in ``model_config``). The nested
    ``pipefy`` model uses names ``PIPEFY_*`` (e.g. ``PIPEFY_GRAPHQL_URL`` →
    ``pipefy.graphql_url``). Environment variables override values from ``.env``. See
    https://docs.pydantic.dev/latest/concepts/pydantic_settings/
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_nested_max_split=1,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    pipefy: PipefySettings = Field(default_factory=PipefySettings)


settings = Settings()
