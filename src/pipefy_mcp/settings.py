from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    pipefy_oauth_client: str | None = Field(
        default=None,
        description="OAuth client ID for Pipefy",
        alias="PIPEFY_OAUTH_CLIENT",
    )


settings = Settings(_env_file=".env", _env_file_encoding="utf-8")
