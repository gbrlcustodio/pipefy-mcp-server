from __future__ import annotations

from pipefy_sdk import PipefySettings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration via pydantic-settings.

    On import, values are read from process environment variables and from a ``.env`` file
    in the current working directory (see ``env_file`` in ``model_config``). The nested
    ``pipefy`` model uses names ``PIPEFY_*`` (e.g. ``PIPEFY_GRAPHQL_URL`` →
    ``pipefy.graphql_url``). Environment variables override values from ``.env``. See
    https://docs.pydantic.dev/latest/concepts/pydantic_settings/
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_nested_max_split=1,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    pipefy: PipefySettings = Field(default_factory=PipefySettings)


settings = Settings()

__all__ = ["PipefySettings", "Settings", "settings"]
