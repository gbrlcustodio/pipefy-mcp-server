from __future__ import annotations

from pipefy_auth import AuthSettings
from pipefy_sdk import PipefySettings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration via pydantic-settings.

    Precedence: init kwargs > ``PIPEFY_*`` env > ``.env`` > defaults.

    The nested ``pipefy`` model uses names ``PIPEFY_*`` (e.g.
    ``PIPEFY_BASE_URL`` → ``pipefy.base_url``); the nested ``auth`` model
    owns ``PIPEFY_SERVICE_ACCOUNT_CLIENT_ID`` / ``_SECRET``,
    ``PIPEFY_AUTH_URL``, ``PIPEFY_AUTH_CLIENT_ID``, and a mirror of
    ``PIPEFY_BASE_URL``. Both nested models run their own SSRF / shape checks
    at construction; no parent-side ``_validate_*`` validator is required.
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_nested_max_split=1,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    pipefy: PipefySettings = Field(default_factory=PipefySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)


settings = Settings()

__all__ = ["AuthSettings", "PipefySettings", "Settings", "settings"]
