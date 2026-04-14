from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class PipefySettings(BaseModel):
    graphql_url: str | None = Field(
        default=None,
        description="GraphQL URL for Pipefy",
    )

    internal_api_url: str = Field(
        default="https://app.pipefy.com/internal_api",
        description="Internal API URL for AI Automation endpoints",
    )

    oauth_url: str | None = Field(
        default=None,
        description="OAuth URL for Pipefy",
    )

    oauth_client: str | None = Field(
        default=None,
        description="OAuth client ID for Pipefy",
    )

    oauth_secret: str | None = Field(
        default=None,
        description="OAuth client secret for Pipefy",
    )

    service_account_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Comma-separated user IDs protected from removal via MCP tools.",
    )

    @field_validator("service_account_ids", mode="before")
    @classmethod
    def _coerce_service_account_ids(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        msg = "service_account_ids must be a list or a comma-separated string"
        raise ValueError(msg)


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
