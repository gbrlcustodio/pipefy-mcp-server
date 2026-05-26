from __future__ import annotations

from pipefy_auth import AuthSettings
from pipefy_sdk import PipefySettings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration via pydantic-settings.

    Each nested model owns its own env loading (``env_prefix="PIPEFY_"``).
    The composition deliberately does NOT set ``env_nested_delimiter`` — that
    flag splits any matching env var (e.g. ``AUTH_BASE_URL``) into a nested
    path, which would bypass each model's prefix gate and let unprefixed env
    vars hijack auth fields. Both nested models run their own SSRF / shape
    checks at construction; no parent-side ``_validate_*`` validator is needed.
    """

    model_config = SettingsConfigDict(extra="ignore")

    pipefy: PipefySettings = Field(default_factory=PipefySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)


settings = Settings()

__all__ = ["AuthSettings", "PipefySettings", "Settings", "settings"]
