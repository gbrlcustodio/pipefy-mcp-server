"""Test-only env readers that mirror the application edge (pipefy_cli / pipefy_mcp).

The auth library is env-free; these readers stand in for the edge so the auth
test-suite can exercise env / dotenv / sectioned-TOML loading and the
``to_credentials()`` both-or-neither rule against the real auth models. The
library SRC ban on ``pydantic_settings`` does not apply to this test-only
stand-in.
"""

from __future__ import annotations

from pipefy_infra.coerce import OPAQUE_CREDENTIAL_PATTERN
from pipefy_infra.deployment import DeploymentConfig
from pipefy_infra.settings_base import PipefyBaseSettings
from pydantic import AliasChoices, Field
from pydantic_settings import SettingsConfigDict  # noqa: TID251

from pipefy_auth.settings import (
    AuthConfig,
    JwtValidationConfig,
    ServiceAccountCredentials,
)


class DeploymentEnv(DeploymentConfig, PipefyBaseSettings):
    """Reads the deployment values under the ``PIPEFY_`` prefix / top-level TOML."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")


class AuthEnv(AuthConfig, PipefyBaseSettings):
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


class JwtEnv(JwtValidationConfig, PipefyBaseSettings):
    """Reads the inbound-validation fields under ``PIPEFY_JWT_`` / ``[jwt]``."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_JWT_")
    _toml_section = "jwt"


class ServiceAccountEnv(PipefyBaseSettings):
    """Reads the service-account credentials under ``PIPEFY_SERVICE_ACCOUNT_`` / ``[service_account]``.

    Fields are optional so absence is representable; ``to_credentials()`` builds
    the both-required library value object, or ``None`` when both are unset, and
    raises when exactly one is set (fail-loud on partial config).
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


__all__ = ["AuthEnv", "DeploymentEnv", "JwtEnv", "ServiceAccountEnv"]
