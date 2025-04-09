from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    pipefy_graphql_url: str | None = Field(
        default=None,
        description="GraphQL URL for Pipefy",
        alias="PIPEFY_GRAPHQL_URL",
    )

    pipefy_oauth_url: str | None = Field(
        default=None,
        description="OAuth URL for Pipefy",
        alias="PIPEFY_OAUTH_URL",
    )

    pipefy_oauth_client: str | None = Field(
        default=None,
        description="OAuth client ID for Pipefy",
        alias="PIPEFY_OAUTH_CLIENT",
    )

    pipefy_oauth_secret: str | None = Field(
        default=None,
        description="OAuth client secret for Pipefy",
        alias="PIPEFY_OAUTH_SECRET",
    )


settings = Settings(_env_file=".env", _env_file_encoding="utf-8")
