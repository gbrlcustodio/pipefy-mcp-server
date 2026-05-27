from __future__ import annotations

from typing import Annotated, Self

from pipefy_infra import security
from pipefy_infra.config import PipefyTomlConfigSource
from pipefy_infra.strings import strip_str
from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# Canonical Pipefy production API host root.
DEFAULT_BASE_URL = "https://app.pipefy.com"

# Pipefy organization IDs are ASCII numeric strings (matches the docstring).
# ``\d`` is Unicode-aware in Python ``re`` (Arabic-Indic ١٢٣, Devanagari १२३,
# etc. would pass), so pin to ``[0-9]`` for the wire format the API expects.
_ORG_ID_PATTERN = r"^[0-9]+$"


class PipefySettings(BaseSettings):
    """Pipefy API connection and shared runtime knobs (MCP, CLI, scripts).

    Endpoint configuration only — credentials live on
    :class:`pipefy_auth.AuthSettings`. Consumers compose both side by side in
    their own settings type; each model owns its own env loading so the parent
    composition does not need ``env_nested_delimiter`` (which routes any
    matching env var into a nested field — a credential-leak primitive when
    multiple nested models share field names).

    A single ``PIPEFY_BASE_URL`` drives every API endpoint via
    :data:`@computed_field` properties (``graphql_url``,
    ``internal_api_url``, ``interfaces_graphql_url``). Operators on
    non-prod environments set ``PIPEFY_BASE_URL=https://<api-host>``;
    operators on prod leave it unset (default Pipefy production).
    """

    model_config = SettingsConfigDict(
        env_prefix="PIPEFY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence: init_kwargs > env > dotenv > config.toml > file_secret.
        # TOML keys are bare pydantic field names; the ``PIPEFY_`` env prefix
        # does not apply to TOML lookups.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            PipefyTomlConfigSource(settings_cls),
            file_secret_settings,
        )

    allow_insecure_urls: bool = Field(
        default=False,
        description=(
            "When true (env: PIPEFY_ALLOW_INSECURE_URLS), GraphQL/auth/internal API URLs "
            "may use http:// and internal hosts; local development only; do not enable in production."
        ),
    )

    base_url: str = Field(
        default=DEFAULT_BASE_URL,
        pattern=security.URL_SHAPE_PATTERN,
        description=(
            "Pipefy API host root (env: PIPEFY_BASE_URL). Drives ``graphql_url`` / "
            "``internal_api_url`` / ``interfaces_graphql_url`` (and the OAuth "
            "token endpoint on :class:`pipefy_auth.AuthSettings`). Defaults to "
            f"'{DEFAULT_BASE_URL}' (canonical Pipefy production). Set to a "
            "different host for non-prod environments, regional / proxy "
            "deployments, or local development (with PIPEFY_ALLOW_INSECURE_URLS)."
        ),
    )

    org_id: str | None = Field(
        default=None,
        pattern=_ORG_ID_PATTERN,
        description=(
            "Optional default organization id (numeric string) for CLI commands that "
            "allow an implicit org, e.g. ``pipefy org get`` when the id argument is "
            "omitted (env: PIPEFY_ORG_ID). Must be a numeric string; empty or "
            "non-numeric values are rejected."
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

    @field_validator("base_url", "org_id", mode="before")
    @classmethod
    def _strip_str(cls, value: object) -> object:
        return strip_str(value)

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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def graphql_url(self) -> str:
        """Pipefy GraphQL endpoint, derived from ``base_url``."""
        return f"{self.base_url.rstrip('/')}/graphql"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def internal_api_url(self) -> str:
        """Internal API endpoint for AI Automation, derived from ``base_url``."""
        return f"{self.base_url.rstrip('/')}/internal_api"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def interfaces_graphql_url(self) -> str:
        """Interfaces GraphQL endpoint (portals/pages/elements), derived from ``base_url``."""
        return f"{self.base_url.rstrip('/')}/graphql/interfaces"

    @model_validator(mode="after")
    def _validate_pipefy_endpoint_urls(self) -> Self:
        from urllib.parse import urlparse

        stripped = self.base_url.strip()
        parsed = urlparse(stripped)
        # ``base_url`` must be a host root: derived endpoints (``graphql_url``,
        # ``internal_api_url``, ``interfaces_graphql_url``) append fixed paths to
        # it via f-strings. A query / fragment / non-root path would land inside
        # the resulting URL's query slot or as a path prefix, producing
        # silently-malformed endpoints rather than a loud validation error.
        if parsed.path.strip("/") or parsed.query or parsed.fragment:
            msg = (
                f"base_url must be a host root with no path, query, or fragment "
                f"(got {self.base_url!r}); the SDK appends "
                "``/graphql`` / ``/internal_api`` / ``/graphql/interfaces`` to it."
            )
            raise ValueError(msg)
        security.validate_https_url(
            stripped, "base_url", allow_insecure=self.allow_insecure_urls
        )
        return self
