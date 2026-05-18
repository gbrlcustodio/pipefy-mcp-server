"""OAuth 2.0 Authorization Code + PKCE login flow for the Pipefy CLI."""

from __future__ import annotations

from pipefy_cli.oauth.discovery import ProviderMetadata, fetch_provider_metadata
from pipefy_cli.oauth.flow import LoginError, LoginResult, run_login
from pipefy_cli.oauth.storage import (
    StoredSession,
    delete_session,
    keychain_backend_name,
    keychain_key,
    load_session,
    store_session,
)

__all__ = [
    "LoginError",
    "LoginResult",
    "ProviderMetadata",
    "StoredSession",
    "delete_session",
    "fetch_provider_metadata",
    "keychain_backend_name",
    "keychain_key",
    "load_session",
    "run_login",
    "store_session",
]
