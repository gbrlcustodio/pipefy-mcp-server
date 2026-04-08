"""Shared helpers for integration tests that require live Pipefy credentials."""

import pytest

from pipefy_mcp.settings import settings


def pipefy_live_configured():
    """Return True when all OAuth + GraphQL credentials are present."""
    p = settings.pipefy
    return bool(
        p.graphql_url
        and str(p.graphql_url).startswith(("http://", "https://"))
        and p.oauth_url
        and str(p.oauth_url).startswith(("http://", "https://"))
        and p.oauth_client
        and p.oauth_secret
    )


def require_live_creds():
    """Skip the current test if live credentials are not configured."""
    if not pipefy_live_configured():
        pytest.skip(
            "Pipefy credentials not configured (PIPEFY_GRAPHQL_URL + OAuth in .env)"
        )
