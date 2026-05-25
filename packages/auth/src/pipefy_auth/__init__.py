"""Shared OAuth + keychain helpers for Pipefy CLI and MCP server.

Owns the keychain-backed user session (``StoredSession``), the OIDC discovery /
authorization-code-with-PKCE login flow, the refresh-token grant, and the OIDC
client identity (``OidcClient``, ``DEFAULT_AUTH_CLIENT_ID``). Consumers
(``pipefy_cli`` and ``pipefy_mcp``) build an authenticated client by passing the
artifacts surfaced here to the SDK.
"""

from __future__ import annotations

__version__ = "0.2.0-beta.1"

from pipefy_auth.bearer import CallableBearerAuth, StaticBearerAuth
from pipefy_auth.discovery import (
    DiscoveryPolicy,
    ProviderMetadata,
    fetch_provider_metadata,
)
from pipefy_auth.flow import LoginError, LoginResult, run_login
from pipefy_auth.identity import DEFAULT_AUTH_CLIENT_ID, DEFAULT_AUTH_URL, OidcClient
from pipefy_auth.refresh import (
    RefreshError,
    ensure_fresh_session,
    refresh_access_token,
)
from pipefy_auth.resolver import (
    SERVICE_ACCOUNT_TIER,
    STATIC_TOKEN_TIER,
    STORED_SESSION_TIER,
    ServiceAccount,
    detect_pipefy_tiers,
    missing_auth_message,
    resolve_pipefy_auth,
    tier_for,
)
from pipefy_auth.revoke import (
    RevocationError,
    RevocationUnsupportedError,
    revoke_session,
)
from pipefy_auth.settings import AuthSettings
from pipefy_auth.storage import (
    SessionDeleteError,
    StoredSession,
    delete_session,
    keychain_backend_name,
    keychain_key,
    load_session,
    store_session,
)

__all__ = [
    "AuthSettings",
    "CallableBearerAuth",
    "DEFAULT_AUTH_CLIENT_ID",
    "DEFAULT_AUTH_URL",
    "DiscoveryPolicy",
    "LoginError",
    "LoginResult",
    "OidcClient",
    "ProviderMetadata",
    "RefreshError",
    "RevocationError",
    "RevocationUnsupportedError",
    "SERVICE_ACCOUNT_TIER",
    "STATIC_TOKEN_TIER",
    "STORED_SESSION_TIER",
    "ServiceAccount",
    "SessionDeleteError",
    "StaticBearerAuth",
    "StoredSession",
    "__version__",
    "delete_session",
    "detect_pipefy_tiers",
    "ensure_fresh_session",
    "fetch_provider_metadata",
    "keychain_backend_name",
    "keychain_key",
    "load_session",
    "missing_auth_message",
    "refresh_access_token",
    "resolve_pipefy_auth",
    "revoke_session",
    "run_login",
    "store_session",
    "tier_for",
]
