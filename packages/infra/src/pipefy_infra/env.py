"""Parse the environment into a :class:`DeploymentConfig` (the deployment edge).

This is the first stage of the settings parse pipeline: it turns raw env / dotenv
/ TOML into the one refined :class:`~pipefy_infra.deployment.DeploymentConfig`
value object that the SDK and auth loaders derive their endpoints and posture
from. The reader (``DeploymentSettings``) is transient parser scaffolding; the
application composition roots call :func:`load_deployment` and hold its output,
not the reader.

Importing this module pulls ``pydantic-settings``; it is the env-reading edge of
``pipefy_infra``, kept out of the env-free import path that the libraries use
(``deployment`` / ``security`` / ``coerce``).
"""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from pipefy_infra.deployment import DeploymentConfig
from pipefy_infra.settings_base import PipefyBaseSettings


class DeploymentSettings(DeploymentConfig, PipefyBaseSettings):
    """Reads the deployment values under the ``PIPEFY_`` prefix / top-level TOML."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")


def load_deployment(
    *,
    base_url: str | None = None,
    allow_insecure_urls: bool | None = None,
) -> DeploymentConfig:
    """Build the one :class:`DeploymentConfig` from env, applying flags as overrides.

    ``base_url`` and ``allow_insecure_urls`` are the two deployment flags an
    application surfaces (the CLI ``--base-url`` / ``--allow-insecure-urls``);
    passed here as init kwargs they outrank env. ``None`` means "not set on the
    command line, fall back to env / dotenv / config.toml / default". Surrounding
    whitespace on ``base_url`` is trimmed by the shared boundary validator.

    Raises:
        pydantic.ValidationError: When the resolved values fail validation (SSRF
            guard, bad URL shape). Callers that surface messages to humans wrap it.
    """
    init: dict[str, object] = {}
    if base_url is not None:
        init["base_url"] = base_url
    if allow_insecure_urls is not None:
        init["allow_insecure_urls"] = allow_insecure_urls
    return DeploymentSettings(**init)


__all__ = ["DeploymentSettings", "load_deployment"]
