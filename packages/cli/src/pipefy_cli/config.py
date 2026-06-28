"""Resolve Pipefy + auth settings for the CLI (the application's env edge).

This is one of the two composition roots that own env reading (the other is
``pipefy_mcp``). The library value objects (``SdkConfig`` / ``AuthConfig``) read
no env; here each concept gets a thin ``pydantic-settings`` reader that adds only
its ``env_prefix`` (and TOML section) on top of the shared
:class:`~pipefy_infra.settings_base.PipefyBaseSettings`.

``resolve_cli_settings`` is procedural: it builds ONE
:class:`~pipefy_infra.deployment.DeploymentConfig` (applying the two CLI flags as
init kwargs, the only place flags land) and injects it by reference into the SDK
and auth readers, so host topology and the insecure-URL posture cannot diverge.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipefy_auth import AuthConfig, ServiceAccountCredentials
from pipefy_infra.coerce import OPAQUE_CREDENTIAL_PATTERN, strip_if_str
from pipefy_infra.deployment import DeploymentConfig
from pipefy_infra.settings_base import PipefyBaseSettings
from pipefy_sdk import SdkConfig
from pydantic import AliasChoices, Field, ValidationError, field_validator
from pydantic_settings import SettingsConfigDict

# Pipefy organization IDs are ASCII numeric strings. ``\d`` is Unicode-aware in
# Python ``re`` (Arabic-Indic / Devanagari would pass), so pin to ``[0-9]``.
_ORG_ID_PATTERN = r"^[0-9]+$"


class DeploymentSettings(DeploymentConfig, PipefyBaseSettings):
    """Reads the deployment values under the ``PIPEFY_`` prefix / top-level TOML."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")


class SdkEnvSettings(SdkConfig, PipefyBaseSettings):
    """Reads the SDK knobs under ``PIPEFY_``; ``deployment`` is injected."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")


class AuthEnvSettings(AuthConfig, PipefyBaseSettings):
    """Reads the login-subsystem fields under ``PIPEFY_AUTH_`` / ``[auth]``.

    ``static_token`` keeps its product-root env name (``PIPEFY_TOKEN``) via a
    cross-prefix alias; ``deployment`` / ``service_account`` are injected.
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_AUTH_")
    _toml_section = "auth"

    static_token: str | None = Field(
        default=None,
        pattern=OPAQUE_CREDENTIAL_PATTERN,
        validation_alias=AliasChoices("PIPEFY_TOKEN"),
    )

    _strip_static = field_validator("static_token", mode="before")(strip_if_str)


class ServiceAccountEnvSettings(PipefyBaseSettings):
    """Reads the service-account credentials under ``PIPEFY_SERVICE_ACCOUNT_`` / ``[service_account]``.

    Fields are optional so absence is representable; ``to_credentials()`` builds
    the both-required :class:`ServiceAccountCredentials`, ``None`` when both are
    unset, and raises when exactly one is set (fail-loud on partial config).
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_SERVICE_ACCOUNT_")
    _toml_section = "service_account"

    client_id: str | None = None
    client_secret: str | None = None

    def to_credentials(self) -> ServiceAccountCredentials | None:
        if self.client_id is None and self.client_secret is None:
            return None
        return ServiceAccountCredentials(
            client_id=self.client_id,  # type: ignore[arg-type]
            client_secret=self.client_secret,  # type: ignore[arg-type]
        )


class CliEdgeSettings(PipefyBaseSettings):
    """CLI-only edge values that are not part of the SDK / auth libraries."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")

    org_id: str | None = Field(default=None, pattern=_ORG_ID_PATTERN)

    _strip_org = field_validator("org_id", mode="before")(strip_if_str)


@dataclass(frozen=True)
class CliSettings:
    """The resolved CLI configuration: SDK + auth value objects + CLI-only org_id."""

    pipefy: SdkConfig
    auth: AuthConfig
    org_id: str | None = None


def resolve_cli_settings(
    *,
    base_url_flag: str | None,
    allow_insecure_urls_flag: bool | None,
) -> CliSettings:
    """Resolve :class:`CliSettings` honoring CLI flags as init kwargs.

    Builds ONE DeploymentConfig (the only place the ``--base-url`` /
    ``--allow-insecure-urls`` flags land, outranking env) and injects it by
    reference into the SDK and auth readers.

    Raises:
        ValueError: When validation fails (e.g. SSRF guard); message is user-facing.
    """
    deploy_init: dict[str, object] = {}
    if base_url_flag is not None:
        deploy_init["base_url"] = base_url_flag.strip()
    if allow_insecure_urls_flag is not None:
        deploy_init["allow_insecure_urls"] = allow_insecure_urls_flag

    try:
        deployment = DeploymentSettings(**deploy_init)
        pipefy = SdkEnvSettings(deployment=deployment)
        service_account = ServiceAccountEnvSettings().to_credentials()
        auth = AuthEnvSettings(deployment=deployment, service_account=service_account)
        edge = CliEdgeSettings()
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    return CliSettings(pipefy=pipefy, auth=auth, org_id=edge.org_id)


__all__ = [
    "AuthEnvSettings",
    "CliEdgeSettings",
    "CliSettings",
    "DeploymentSettings",
    "SdkEnvSettings",
    "ServiceAccountEnvSettings",
    "resolve_cli_settings",
]
