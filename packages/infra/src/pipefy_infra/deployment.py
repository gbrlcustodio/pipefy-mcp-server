"""The one source of Pipefy host topology and insecure-URL posture.

:class:`DeploymentConfig` is a pure :class:`pydantic.BaseModel` value object: it
validates itself but reads no env / file. A single ``base_url`` drives every
derived endpoint (``graphql_url``, ``internal_api_url``,
``interfaces_graphql_url``, ``oauth_token_url``) via computed properties, and a
single ``allow_insecure_urls`` flag sets the SSRF posture for the whole
deployment. The application edge builds one instance and injects it by reference
into the SDK / auth / jwt / resource-server configs, so those cannot structurally
diverge on host or posture.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, Field, computed_field, model_validator

from pipefy_infra import security

# Canonical Pipefy production API host root.
DEFAULT_BASE_URL = "https://app.pipefy.com"


class DeploymentConfig(BaseModel):
    """Host topology + insecure-URL posture for one Pipefy deployment.

    A pure value object. ``base_url`` is the host root that drives every
    endpoint; ``allow_insecure_urls`` is the single SSRF posture. SSRF
    validation runs inline as a ``model_validator(mode="after")`` so direct
    construction is safe and the host root is validated once for all the
    suffixes that derive from it.
    """

    allow_insecure_urls: bool = Field(
        default=False,
        description=(
            "When true (env: PIPEFY_ALLOW_INSECURE_URLS), every derived URL may "
            "use http:// and internal hosts; local development only; do not "
            "enable in production. The single insecure-URL posture for the whole "
            "deployment: injected by reference so SDK/auth/jwt/rs cannot diverge."
        ),
    )

    base_url: str = Field(
        default=DEFAULT_BASE_URL,
        pattern=security.URL_SHAPE_PATTERN,
        description=(
            "Pipefy API host root (env: PIPEFY_BASE_URL). Drives ``graphql_url`` / "
            "``internal_api_url`` / ``interfaces_graphql_url`` / ``oauth_token_url`` "
            f"via computed properties. Defaults to '{DEFAULT_BASE_URL}' (canonical "
            "Pipefy production). Set to a different host for non-prod environments, "
            "regional / proxy deployments, or local development (with "
            "PIPEFY_ALLOW_INSECURE_URLS)."
        ),
    )

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
        """OAuth 2.0 token endpoint for the service-account tier, derived from ``base_url``."""
        return f"{self.base_url.rstrip('/')}/oauth/token"

    @model_validator(mode="after")
    def _validate_base_url(self) -> Self:
        # ``base_url`` is the host root that drives ``/graphql``,
        # ``/internal_api``, ``/graphql/interfaces``, ``/oauth/token`` via the
        # computed properties above; any non-root path/query/fragment would
        # corrupt the f-string concatenation. Host-root is strictly stronger
        # than no-query/fragment, so the derived URLs need no separate gate.
        security.assert_url_is_host_root(self.base_url, field_label="base_url")
        security.validate_https_url(
            self.base_url, "base_url", allow_insecure=self.allow_insecure_urls
        )
        return self


__all__ = ["DEFAULT_BASE_URL", "DeploymentConfig"]
