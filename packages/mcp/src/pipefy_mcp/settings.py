from __future__ import annotations

from typing import Self

from pipefy_auth import AuthSettings
from pipefy_sdk import PipefySettings
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration via pydantic-settings.

    On import, values are read from process environment variables and from a ``.env`` file
    in the current working directory (see ``env_file`` in ``model_config``). The nested
    ``pipefy`` model uses names ``PIPEFY_*`` (e.g. ``PIPEFY_GRAPHQL_URL`` →
    ``pipefy.graphql_url``); the nested ``auth`` model owns
    ``PIPEFY_SERVICE_ACCOUNT_*``, ``PIPEFY_AUTH_URL``, and
    ``PIPEFY_AUTH_CLIENT_ID``. See
    https://docs.pydantic.dev/latest/concepts/pydantic_settings/
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_nested_max_split=1,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    pipefy: PipefySettings = Field(default_factory=PipefySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)

    @model_validator(mode="after")
    def _validate_auth_urls(self) -> Self:
        # PipefySettings validates its own endpoint URLs on construction; mirror
        # that for AuthSettings here so unsafe service-account / OIDC URLs fail
        # fast at settings load (matches CliSettings.resolve_cli_settings).
        self.auth.validate_urls(allow_insecure=self.pipefy.allow_insecure_urls)
        return self


settings = Settings()

__all__ = ["AuthSettings", "PipefySettings", "Settings", "settings"]
