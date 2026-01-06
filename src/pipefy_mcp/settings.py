from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PipefySettings(BaseModel):
    graphql_url: str | None = Field(
        default=None,
        description="GraphQL URL for Pipefy",
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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="_", env_nested_max_split=1)

    pipefy: PipefySettings


settings = Settings(_env_file=".env", _env_file_encoding="utf-8")
