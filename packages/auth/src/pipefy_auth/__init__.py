"""Shared OAuth + keychain helpers for Pipefy CLI and MCP server.

Owns the keychain-backed user session (``StoredSession``), the OIDC discovery /
authorization-code-with-PKCE login flow, the refresh-token grant, and the OIDC
client identity (``OidcClient``, ``DEFAULT_AUTH_CLIENT_ID``). Consumers
(``pipefy_cli`` and ``pipefy_mcp``) build an authenticated client by passing the
artifacts surfaced here to the SDK.
"""

from __future__ import annotations

__version__ = "0.3.0-alpha.1"

from pipefy_auth.bearer import (
    RefreshableBearerAuth,
    StaticBearerAuth,
)
from pipefy_auth.discovery import (
    DiscoveryPolicy,
    ProviderMetadata,
    fetch_provider_metadata,
)
from pipefy_auth.flow import LoginError, LoginResult, run_login
from pipefy_auth.identity import DEFAULT_AUTH_CLIENT_ID, OidcClient
from pipefy_auth.refresh import (
    RefreshError,
    ensure_fresh_session,
    refresh_access_token,
)
from pipefy_auth.resolver import (
    ResolvedAuth,
    ServiceAccount,
    ServiceAccountAuth,
    StaticTokenAuth,
    StoredSessionAuth,
    build_httpx_auth,
    detect_pipefy_auth_methods,
    missing_auth_message,
    resolve_pipefy_auth,
)
from pipefy_auth.responses import OAuthErrorResponse, TokenResponse
from pipefy_auth.revoke import (
    RevocationError,
    RevocationUnsupportedError,
    revoke_session,
)
from pipefy_auth.settings import AuthSettings, JwtValidationSettings
from pipefy_auth.storage import (
    SessionDeleteError,
    StoredSession,
    configure_keychain_backend,
    delete_session,
    keychain_backend_name,
    keychain_key,
    load_session,
    store_session,
)
from pipefy_auth.verification import (
    AudiencePolicy,
    JwtValidator,
    RequireAudience,
    SkipAudience,
    TokenValidationError,
)

__all__ = [
    "AudiencePolicy",
    "AuthSettings",
    "JwtValidationSettings",
    "RequireAudience",
    "SkipAudience",
    "DEFAULT_AUTH_CLIENT_ID",
    "DiscoveryPolicy",
    "JwtValidator",
    "LoginError",
    "LoginResult",
    "OAuthErrorResponse",
    "OidcClient",
    "ProviderMetadata",
    "RefreshError",
    "RefreshableBearerAuth",
    "RevocationError",
    "RevocationUnsupportedError",
    "ResolvedAuth",
    "ServiceAccount",
    "ServiceAccountAuth",
    "SessionDeleteError",
    "StaticBearerAuth",
    "StaticTokenAuth",
    "StoredSession",
    "StoredSessionAuth",
    "TokenResponse",
    "TokenValidationError",
    "__version__",
    "build_httpx_auth",
    "configure_keychain_backend",
    "delete_session",
    "detect_pipefy_auth_methods",
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
]
