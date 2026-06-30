"""Live OAuth smoke test for ``get_authenticated_client`` (requires ``PIPEFY_*``)."""

from __future__ import annotations

import asyncio

import pytest
from _shared.live_settings import (
    live_auth_config,
    live_endpoints,
    require_live_creds,
)
from pipefy_auth import CredentialSources

from pipefy_cli.auth import get_authenticated_client
from pipefy_cli.runtime import CliRuntime


@pytest.mark.integration
def test_live_oauth_round_trip_triggers_graphql_auth():
    """First GraphQL request obtains an OAuth token (same stack as MCP)."""

    require_live_creds()
    auth_settings = live_auth_config()
    runtime = CliRuntime(
        endpoints=live_endpoints(),
        allow_insecure_urls=auth_settings.allow_insecure_urls,
        reuse_schema=False,
        default_webhook_name="Pipefy Webhook",
        credentials=CredentialSources(
            static_token=None,
            service_account=auth_settings.to_service_account(),
            oidc_client=auth_settings.to_oidc_client(),
        ),
        token_source=None,
        keychain_backend=auth_settings.keychain_backend,
        org_id=None,
    )

    async def run():
        client = get_authenticated_client(runtime)
        return await client.search_schema("Card", kind="OBJECT")

    data = asyncio.run(run())
    assert isinstance(data, dict)
