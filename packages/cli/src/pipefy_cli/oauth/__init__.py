"""OAuth 2.0 Authorization Code + PKCE login flow for the Pipefy CLI."""

from __future__ import annotations

from pipefy_cli.oauth.discovery import (
    DiscoveryPolicy,
    ProviderMetadata,
    fetch_provider_metadata,
)
from pipefy_cli.oauth.flow import LoginError, LoginResult, run_login
from pipefy_cli.oauth.refresh import (
    RefreshError,
    ensure_fresh_session,
    refresh_access_token,
)
from pipefy_cli.oauth.revoke import (
    RevocationError,
    RevocationUnsupportedError,
    revoke_session,
)
from pipefy_cli.oauth.storage import (
    SessionDeleteError,
    StoredSession,
    delete_session,
    keychain_backend_name,
    keychain_key,
    load_session,
    store_session,
)

__all__ = [
    "DiscoveryPolicy",
    "LoginError",
    "LoginResult",
    "ProviderMetadata",
    "RefreshError",
    "RevocationError",
    "RevocationUnsupportedError",
    "SessionDeleteError",
    "StoredSession",
    "delete_session",
    "ensure_fresh_session",
    "fetch_provider_metadata",
    "keychain_backend_name",
    "keychain_key",
    "load_session",
    "refresh_access_token",
    "revoke_session",
    "run_login",
    "store_session",
]
