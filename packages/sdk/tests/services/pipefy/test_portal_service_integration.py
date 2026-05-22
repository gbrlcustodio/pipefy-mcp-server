"""Live portal read scenarios for PortalService.

Requires valid Pipefy credentials (``.env`` with ``PIPEFY_*``). Skips when
credentials or optional org UUID are missing so CI stays green.

Optional smoke (set ``PIPEFY_PORTAL_ORG_UUID`` to an org with a main portal):

    uv run pytest packages/sdk/tests/services/pipefy/test_portal_service_integration.py -m integration -v

Full publish-cycle coverage is deferred to task 6.7.
"""

from __future__ import annotations

import os

import pytest
from _shared.live_settings import live_pipefy_settings, require_live_creds
from httpx_auth import OAuth2ClientCredentials

from pipefy_sdk.services.portal_service import PortalService


@pytest.fixture
def live_portal_service() -> PortalService:
    """PortalService wired against live Interfaces schema credentials."""
    require_live_creds()
    settings = live_pipefy_settings()
    auth = OAuth2ClientCredentials(
        token_url=settings.oauth_url,
        client_id=settings.oauth_client,
        client_secret=settings.oauth_secret,
    )
    return PortalService(settings=settings, auth=auth)


def _portal_org_uuid() -> str | None:
    value = os.environ.get("PIPEFY_PORTAL_ORG_UUID", "").strip()
    return value or None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_list_portals_returns_list_shape(
    live_portal_service: PortalService,
) -> None:
    """Smoke: list_portals returns a list; nodes include uuid and name when present."""
    org_uuid = _portal_org_uuid()
    if org_uuid is None:
        pytest.skip("Set PIPEFY_PORTAL_ORG_UUID for live portal list smoke")

    portals = await live_portal_service.list_portals(org_uuid)

    assert isinstance(portals, list)
    if portals:
        portal = portals[0]
        assert "uuid" in portal
        assert "name" in portal


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_get_portal_round_trip_from_list(
    live_portal_service: PortalService,
) -> None:
    """Smoke: get_portal returns pages and published when a main portal exists."""
    org_uuid = _portal_org_uuid()
    if org_uuid is None:
        pytest.skip("Set PIPEFY_PORTAL_ORG_UUID for live portal get smoke")

    portals = await live_portal_service.list_portals(org_uuid)
    if not portals:
        pytest.skip(f"No main portal found for org {org_uuid}")

    portal_uuid = portals[0]["uuid"]
    detail = await live_portal_service.get_portal(portal_uuid)

    assert detail["uuid"] == portal_uuid
    assert "published" in detail
    assert "pages" in detail
