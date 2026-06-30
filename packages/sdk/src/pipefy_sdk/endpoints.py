"""The SDK's endpoint value object: the three Pipefy GraphQL URLs the client runs on.

:class:`PipefyEndpoints` is a frozen, refined :class:`pydantic.BaseModel`: its
construction is a witness that the three endpoint URLs are well-shaped (scheme +
host, no query or fragment that would corrupt downstream use). It carries
endpoint topology only; the insecure-URL posture travels separately as a
primitive, because that posture is a deployment-edge policy decision, not a
property of the URLs themselves.

The application edge derives a :class:`PipefyEndpoints` from the one
:class:`~pipefy_infra.deployment.DeploymentConfig` (via ``pipefy_sdk.env``), where
the host-root SSRF policy has already been parsed; the URLs here are witnesses
that the policy parse passed.
"""

from __future__ import annotations

from typing import Self

from pipefy_infra import security
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PipefyEndpoints(BaseModel):
    """The three Pipefy GraphQL endpoint URLs a :class:`PipefyClient` connects to.

    A frozen value object. Each URL is shape-validated (``URL_SHAPE_PATTERN`` plus
    no query/fragment), so a constructed instance cannot carry a malformed
    endpoint. HTTPS-vs-insecure and blocked-IP policy is a separate, context-
    dependent parse that runs at the deployment edge; it is not re-checked here.
    """

    model_config = ConfigDict(frozen=True)

    graphql_url: str = Field(
        pattern=security.URL_SHAPE_PATTERN,
        description="Pipefy public GraphQL endpoint.",
    )

    interfaces_graphql_url: str = Field(
        pattern=security.URL_SHAPE_PATTERN,
        description="Interfaces GraphQL endpoint (portals / pages / elements).",
    )

    internal_api_url: str = Field(
        pattern=security.URL_SHAPE_PATTERN,
        description="Internal API endpoint for AI Automation.",
    )

    @model_validator(mode="after")
    def _validate_url_shape(self) -> Self:
        # A stray query or fragment would land between the endpoint and any
        # suffix downstream concatenates; reject it on every construction path.
        for value, label in (
            (self.graphql_url, "graphql_url"),
            (self.interfaces_graphql_url, "interfaces_graphql_url"),
            (self.internal_api_url, "internal_api_url"),
        ):
            security.assert_url_has_no_query_or_fragment(value, field_label=label)
        return self


__all__ = ["PipefyEndpoints"]
