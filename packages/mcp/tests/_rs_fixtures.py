"""Shared resource-server test fixtures for the remote MCP profile.

The ``remote`` profile's inbound-auth tests (``test_server`` and
``core/test_runtime``) each need one fully-configured resource-server deployment.
The issuer/resource literals and the settings shape live here so the two suites
cannot drift. The explicit ``jwks_uri`` skips OIDC discovery, so building the
resource server does no network I/O.
"""

from __future__ import annotations

from mcp.server.auth.middleware.auth_context import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from pipefy_auth import AuthSettings, JwtValidationSettings
from pipefy_sdk import PipefySettings
from starlette.requests import Request

from pipefy_mcp.settings import McpSettings, ResourceServerSettings, Settings

RS_ISSUER = "https://idp.example.com/realms/x"
RS_RESOURCE = "https://mcp.example.com/mcp"
RS_JWKS_URI = f"{RS_ISSUER}/jwks"


def remote_rs_settings() -> Settings:
    """The remote profile plus a configured resource server and JWT validation."""
    return Settings(
        pipefy=PipefySettings(base_url="https://api.pipefy.com"),
        auth=AuthSettings(),
        mcp=McpSettings(profile="remote"),
        rs=ResourceServerSettings(resource_server_url=RS_RESOURCE),
        jwt=JwtValidationSettings(issuer_url=RS_ISSUER, jwks_uri=RS_JWKS_URI),
    )


def authenticated_user(token: str) -> AuthenticatedUser:
    """The RS-validated user the resource-server middleware leaves on a request."""
    return AuthenticatedUser(AccessToken(token=token, client_id=token, scopes=[]))


def request_with_user(user: AuthenticatedUser | None) -> Request:
    """A Starlette request whose ``scope["user"]`` is what the RS validated.

    Mirrors what the resource-server middleware leaves on each message's request:
    an ``AuthenticatedUser`` when a bearer validated, or ``None`` otherwise.
    """
    return Request({"type": "http", "headers": [], "user": user})
