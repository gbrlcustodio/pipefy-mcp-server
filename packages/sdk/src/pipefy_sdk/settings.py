from __future__ import annotations

from typing import Self

from pipefy_infra import security
from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

# Canonical Pipefy production API host root.
DEFAULT_BASE_URL = "https://app.pipefy.com"


class ClientSettings(BaseModel):
    """Pipefy API connection and SDK client-behavior knobs.

    A pure value object: it validates itself but reads no env / file. The
    application edge constructs it from
    :func:`pipefy_infra.config.read_client_env` (or explicit kwargs); see that
    reader for the ``PIPEFY_*`` env-name contract. Credentials live on
    :class:`pipefy_auth.AuthSettings`, which the caller builds alongside this and
    injects ``oauth_token_url`` into.

    A single ``base_url`` drives every API endpoint via :data:`@computed_field`
    properties (``graphql_url``, ``internal_api_url``, ``interfaces_graphql_url``,
    and ``oauth_token_url`` for the auth model to consume).
    """

    base_url: str = Field(
        default=DEFAULT_BASE_URL,
        pattern=security.URL_SHAPE_PATTERN,
        description=(
            "Pipefy API host root. Drives ``graphql_url`` / ``internal_api_url`` / "
            "``interfaces_graphql_url`` and ``oauth_token_url`` (injected into "
            ":class:`pipefy_auth.AuthSettings`). Defaults to "
            f"'{DEFAULT_BASE_URL}' (canonical Pipefy production)."
        ),
    )

    allow_insecure_urls: bool = Field(
        default=False,
        description=(
            "When true, URLs may use http:// and internal hosts; local development "
            "only. Sourced from PIPEFY_ALLOW_INSECURE_URLS at the edge and shared "
            "(injected) with the auth / JWT / resource-server models so the whole "
            "deployment has one insecure-URL posture."
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

    @field_validator("base_url", mode="before")
    @classmethod
    def _strip_str(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def oauth_token_url(self) -> str:
        """OAuth 2.0 token endpoint, derived from ``base_url``.

        The application edge injects this into :class:`pipefy_auth.AuthSettings`
        as ``service_account_token_url`` so the host root is read once and the
        auth model never references the SDK type.
        """
        return f"{self.base_url.rstrip('/')}/oauth/token"

    @model_validator(mode="after")
    def _validate_pipefy_endpoint_urls(self) -> Self:
        # ``base_url`` is the host root that drives ``/graphql``,
        # ``/internal_api``, ``/graphql/interfaces``, ``/oauth/token`` via the
        # computed properties above; any non-root path/query/fragment would
        # corrupt the f-string concatenation.
        self.base_url = security.sanitize_url(
            self.base_url,
            field_label="base_url",
            allow_insecure=self.allow_insecure_urls,
            require_host_root=True,
        )
        return self


# Deprecated alias kept one release for external SDK consumers importing the old
# name; in-repo code uses ClientSettings.
PipefySettings = ClientSettings
