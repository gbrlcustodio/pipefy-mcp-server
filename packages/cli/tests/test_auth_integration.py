"""Live OAuth smoke test for ``get_authenticated_client`` (requires ``PIPEFY_*``)."""

from __future__ import annotations

import asyncio

import pytest
from _shared.live_settings import (
    live_auth_config,
    live_pipefy_config,
    require_live_creds,
)

from pipefy_cli.auth import AuthContext, get_authenticated_client


@pytest.mark.integration
def test_live_oauth_round_trip_triggers_graphql_auth():
    """First GraphQL request obtains an OAuth token (same stack as MCP)."""

    require_live_creds()
    settings = live_pipefy_config()
    auth_settings = live_auth_config()

    async def run():
        client = get_authenticated_client(
            settings,
            AuthContext(
                bearer_token=None,
                service_account=auth_settings.to_service_account(),
                oidc_client=auth_settings.to_oidc_client(),
            ),
        )
        return await client.search_schema("Card", kind="OBJECT")

    data = asyncio.run(run())
    assert isinstance(data, dict)
