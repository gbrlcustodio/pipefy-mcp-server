"""Live portal read scenarios for PortalService.

Requires valid Pipefy credentials in repo-root **``.env``** (``PIPEFY_*``). All tests
require ``PIPEFY_PORTAL_ORG_UUID`` (org where the token has ``manage_portals``).
Unit tests use fictional ids in ``_shared.fixture_ids`` — never commit real org ids
into test source. See ``docs/setup.md`` and ``.env.example``.

Optional smoke:

    # PIPEFY_PORTAL_ORG_UUID in .env (local only)
    uv run pytest packages/sdk/tests/services/pipefy/test_portal_service_integration.py -m integration -v

    uv run pytest packages/sdk/tests/services/pipefy/test_portal_service_integration.py -m integration -k portal_element -v

Full publish-cycle coverage is deferred to a follow-up integration suite.
"""

from __future__ import annotations

import os
import uuid

import pytest
from _shared.live_settings import (
    live_pipefy_settings,
    live_resolved_auth,
    require_live_creds,
)
from gql.transport.exceptions import TransportQueryError

from pipefy_sdk.exceptions import PortalPermissionError
from pipefy_sdk.services.portal_service import PortalService

_PORTAL_ORG_SKIP = (
    "Set PIPEFY_PORTAL_ORG_UUID to an org where the token has manage_portals."
)


@pytest.fixture
def live_portal_service() -> PortalService:
    """PortalService wired against live Interfaces schema credentials."""
    require_live_creds()
    return PortalService(settings=live_pipefy_settings(), auth=live_resolved_auth())


def _portal_org_uuid() -> str | None:
    value = os.environ.get("PIPEFY_PORTAL_ORG_UUID", "").strip()
    return value or None


def _require_portal_org_uuid() -> str:
    org_uuid = _portal_org_uuid()
    if org_uuid is None:
        pytest.skip(_PORTAL_ORG_SKIP)
    return org_uuid


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_list_portals_returns_list_shape(
    live_portal_service: PortalService,
) -> None:
    """Smoke: list_portals returns a list; nodes include uuid and name when present."""
    org_uuid = _require_portal_org_uuid()

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
    org_uuid = _require_portal_org_uuid()

    portals = await live_portal_service.list_portals(org_uuid)
    if not portals:
        pytest.skip(f"No main portal found for org {org_uuid}")

    portal_uuid = portals[0]["uuid"]
    detail = await live_portal_service.get_portal(portal_uuid)

    assert detail["uuid"] == portal_uuid
    assert "published" in detail
    assert "pages" in detail


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_create_portal_idempotent_returns_same_uuid(
    live_portal_service: PortalService,
) -> None:
    """Smoke: create_portal called twice returns the same portal uuid (idempotent)."""
    org_uuid = _require_portal_org_uuid()

    first = await live_portal_service.create_portal(org_uuid)
    second = await live_portal_service.create_portal(org_uuid)

    assert first["uuid"] == second["uuid"]
    assert first["uuid"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_update_portal_page_layout_on_bootstrapped_page(
    live_portal_service: PortalService,
) -> None:
    """Smoke: Json layout must be serialized; updatePageLayout returns success."""
    org_uuid = _require_portal_org_uuid()
    portal = await live_portal_service.create_portal(org_uuid)
    portal_uuid = portal["uuid"]
    page_title = f"mcp-layout-smoke-{uuid.uuid4().hex[:8]}"

    try:
        page = await live_portal_service.create_portal_page(portal_uuid, page_title)
    except PortalPermissionError:
        pytest.skip(f"Token lacks manage_portals on org {org_uuid}")

    page_id = page.get("uuid") or page.get("id")
    assert page_id

    # Interfaces layout is an array of row objects (not `{rows: [...]}`). Invalid layout
    # JSON breaks the portal UI with HTTP 500.
    element_ids = [
        element.get("uuid") or element.get("id")
        for element in page.get("elements", [])
        if element.get("uuid") or element.get("id")
    ]
    layout = [
        {
            "id": str(uuid.uuid4()),
            "type": "row",
            "children": [element_id],
        }
        for element_id in element_ids
    ]
    try:
        result = await live_portal_service.update_portal_page_layout(page_id, layout)
        assert result.get("updatePageLayout", {}).get("success") is True
    finally:
        await live_portal_service.delete_portal_page(portal_uuid, page_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_update_portal_element_on_bootstrapped_page(
    live_portal_service: PortalService,
) -> None:
    """Smoke: updateElement returns success (payload has no element field)."""
    org_uuid = _require_portal_org_uuid()
    portal = await live_portal_service.create_portal(org_uuid)
    portal_uuid = portal["uuid"]
    page_title = f"mcp-update-el-smoke-{uuid.uuid4().hex[:8]}"

    try:
        page = await live_portal_service.create_portal_page(portal_uuid, page_title)
    except PortalPermissionError:
        pytest.skip(f"Token lacks manage_portals on org {org_uuid}")

    page_id = page.get("uuid") or page.get("id")
    link = next(
        (
            element
            for element in page.get("elements", [])
            if element.get("type") == "link"
        ),
        None,
    )
    if link is None:
        pytest.skip("Bootstrapped page has no link element to update")

    element_id = link.get("uuid") or link.get("id")
    metadata = {
        "gridMap": {"height": 64, "columns": 4, "minColumns": 4},
        "linkName": "MCP integration updated link",
    }

    try:
        updated = await live_portal_service.update_portal_element(
            element_id,
            page_id,
            type="link",
            metadata=metadata,
        )
    except TransportQueryError as exc:
        pytest.skip(
            f"updateElement failed on org {org_uuid} (Interfaces API): {exc.errors}"
        )

    assert updated["uuid"] == element_id
    assert updated["metadata"]["linkName"] == "MCP integration updated link"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_create_portal_element_on_bootstrapped_page(
    live_portal_service: PortalService,
) -> None:
    """Smoke: createElement on a templated page (may fail with Interfaces INTERNAL_SERVER_ERROR)."""
    org_uuid = _require_portal_org_uuid()
    portal = await live_portal_service.create_portal(org_uuid)
    portal_uuid = portal["uuid"]
    page_title = f"mcp-create-el-smoke-{uuid.uuid4().hex[:8]}"

    try:
        page = await live_portal_service.create_portal_page(portal_uuid, page_title)
    except PortalPermissionError:
        pytest.skip(f"Token lacks manage_portals on org {org_uuid}")

    page_id = page.get("uuid") or page.get("id")
    link_metadata = {
        "gridMap": {"height": 64, "columns": 4, "minColumns": 4},
        "linkUrl": "https://pipefy.com",
        "linkName": "Pipefy MCP smoke",
    }

    try:
        element = await live_portal_service.create_portal_element(
            page_id,
            type="link",
            metadata=link_metadata,
        )
    except PortalPermissionError:
        pytest.skip(f"Token lacks manage_portals on org {org_uuid}")
    except TransportQueryError as exc:
        codes = [
            (err.get("extensions") or {}).get("code")
            for err in (exc.errors or [])
            if isinstance(err, dict)
        ]
        if "INTERNAL_SERVER_ERROR" in codes:
            pytest.skip(
                "createElement returned INTERNAL_SERVER_ERROR on live org "
                "(API-side; SDK sends data_sources: [] on the wire)."
            )
        raise

    element_id = element.get("uuid") or element.get("id")
    assert element_id
    assert element.get("type") == "link"

    try:
        await live_portal_service.delete_portal_element(element_id, page_id)
        await live_portal_service.delete_portal_page(portal_uuid, page_id)
    except (PortalPermissionError, TransportQueryError, ValueError) as exc:
        pytest.fail(
            f"Failed to clean up portal element/page after create smoke: {exc}",
            pytrace=False,
        )
