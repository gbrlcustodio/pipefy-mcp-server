"""Parse the environment into the SDK's refined inputs (the SDK's env edge).

The second stage of the settings parse pipeline for the SDK: given the one
:class:`~pipefy_infra.deployment.DeploymentConfig` (already parsed by
``pipefy_infra.env``), derive the :class:`~pipefy_sdk.endpoints.PipefyEndpoints`
value object and read the SDK's own runtime knobs. The thin reader is transient
parser scaffolding; the application holds the returned value object + primitives,
not a config instance.

Importing this module pulls ``pydantic-settings``; it is the SDK's env-reading
edge, deliberately kept out of the env-free ``import pipefy_sdk`` path.
"""

from __future__ import annotations

from pipefy_infra.deployment import DeploymentConfig
from pipefy_infra.settings_base import PipefyBaseSettings
from pydantic import Field
from pydantic_settings import SettingsConfigDict  # noqa: TID251

from pipefy_sdk.endpoints import PipefyEndpoints


class _SdkKnobs(PipefyBaseSettings):
    """Reads the SDK's own runtime knobs under ``PIPEFY_`` / top-level TOML."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")

    gql_reuse_fetched_graphql_schema: bool = Field(default=False)

    default_webhook_name: str = Field(
        default="Pipefy Webhook", min_length=1, max_length=255
    )


def load_sdk(
    deployment: DeploymentConfig,
) -> tuple[PipefyEndpoints, bool, bool, str]:
    """Derive the SDK inputs from the shared ``deployment`` plus env-read knobs.

    Returns the endpoint value object alongside the three primitives the SDK
    surface takes: ``allow_insecure_urls`` (the shared posture, read off the
    deployment so it cannot diverge), ``reuse_schema``, and
    ``default_webhook_name``.

    Returns:
        ``(endpoints, allow_insecure_urls, reuse_schema, default_webhook_name)``.

    Raises:
        pydantic.ValidationError: When a knob fails validation.
    """
    knobs = _SdkKnobs()
    endpoints = PipefyEndpoints(
        graphql_url=deployment.graphql_url,
        interfaces_graphql_url=deployment.interfaces_graphql_url,
        internal_api_url=deployment.internal_api_url,
    )
    return (
        endpoints,
        deployment.allow_insecure_urls,
        knobs.gql_reuse_fetched_graphql_schema,
        knobs.default_webhook_name,
    )


__all__ = ["load_sdk"]
