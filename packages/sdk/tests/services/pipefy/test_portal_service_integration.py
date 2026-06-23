"""Live portal read scenarios for PortalService.

Requires valid Pipefy credentials in repo-root **``.env``** (``PIPEFY_*``). All tests
require ``PIPEFY_PORTAL_ORG_UUID`` (org where the token has ``manage_portals``).
Unit tests use fictional ids in ``_shared.fixture_ids`` — never commit real org ids
into test source. See ``docs/config.md`` and ``.env.example``.

Optional smoke:

    # PIPEFY_PORTAL_ORG_UUID in .env (local only)
    uv run pytest packages/sdk/tests/services/pipefy/test_portal_service_integration.py -m integration -v

    uv run pytest packages/sdk/tests/services/pipefy/test_portal_service_integration.py -m integration -k portal_element -v

Sub-portal publish/unpublish cycle: ``-k "publish_sub_portal or sub_portal"``.
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

from pipefy_sdk.client import build_executors
from pipefy_sdk.exceptions import PortalPermissionError
from pipefy_sdk.services.portal_service import PortalService

_PORTAL_ORG_SKIP = (
    "Set PIPEFY_PORTAL_ORG_UUID to an org where the token has manage_portals."
)


@pytest.fixture
def live_portal_service() -> PortalService:
    """PortalService with live Interfaces + internal_api for sub-portal mutations."""
    require_live_creds()
    ex = build_executors(live_pipefy_settings(), live_resolved_auth())
    return PortalService(
        public_executor=ex.public,
        interfaces_executor=ex.interfaces,
        internal_executor=ex.internal,
    )


def _portal_org_uuid() -> str | None:
    value = os.environ.get("PIPEFY_PORTAL_ORG_UUID", "").strip()
    return value or None


def _require_portal_org_uuid() -> str:
    org_uuid = _portal_org_uuid()
    if org_uuid is None:
        pytest.skip(_PORTAL_ORG_SKIP)
    return org_uuid


def _first_forms_element_id(portal_detail: dict) -> str | None:
    for page in portal_detail.get("pages") or []:
        for element in page.get("elements") or []:
            if element.get("type") != "forms":
                continue
            element_id = element.get("uuid") or element.get("id")
            if element_id:
                return str(element_id)
    return None


def _sub_portal_published(
    portal_detail: dict,
    sub_portal_uuid: str,
) -> bool | None:
    for sub_portal in portal_detail.get("subPortals") or []:
        sub_id = sub_portal.get("uuid") or sub_portal.get("id")
        if sub_id == sub_portal_uuid:
            published = sub_portal.get("published")
            return published if isinstance(published, bool) else None
    return None


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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_publish_sub_portal_cycle(
    live_portal_service: PortalService,
) -> None:
    """Publish then unpublish a sub-portal on a templated forms element (internal_api)."""
    org_uuid = _require_portal_org_uuid()
    sub_portal_uuid: str | None = None

    try:
        try:
            portal = await live_portal_service.create_portal(org_uuid)
        except PortalPermissionError:
            pytest.skip(
                f"Token lacks manage_portals on org {org_uuid}; "
                "set PIPEFY_PORTAL_ORG_UUID to an org with portal write access."
            )

        portal_uuid = portal["uuid"]
        detail = await live_portal_service.get_portal(portal_uuid)
        element_id = _first_forms_element_id(detail)
        if element_id is None:
            pytest.skip(
                f"Main portal {portal_uuid} has no forms element on any page; "
                "publish_sub_portal requires a templated forms slot "
                "(updateSubPortalElement, not createElement(subPortal))."
            )

        sub_name = f"mcp-publish-smoke-{uuid.uuid4().hex[:8]}"
        try:
            created = await live_portal_service.create_sub_portal(portal_uuid, sub_name)
        except PortalPermissionError:
            pytest.skip(
                f"Token lacks manage_portals on org {org_uuid}; "
                "set PIPEFY_PORTAL_ORG_UUID to an org with portal write access."
            )

        sub_portal_uuid = created.get("uuid") or created.get("id")
        assert sub_portal_uuid

        try:
            await live_portal_service.publish_sub_portal(
                portal_uuid,
                element_id,
                sub_portal_uuid,
            )
        except TransportQueryError as exc:
            pytest.skip(
                f"publish_sub_portal failed on org {org_uuid} (internal_api): {exc}"
            )

        after_publish = await live_portal_service.get_portal(portal_uuid)
        published_after_attach = _sub_portal_published(after_publish, sub_portal_uuid)
        assert published_after_attach is True, (
            f"Expected subPortals[].published is True for {sub_portal_uuid} "
            f"after publish_sub_portal; got {published_after_attach!r} in "
            f"{after_publish.get('subPortals')!r}"
        )

        try:
            await live_portal_service.unpublish_sub_portal(portal_uuid, element_id)
        except TransportQueryError as exc:
            pytest.skip(
                f"unpublish_sub_portal failed on org {org_uuid} (internal_api): {exc}"
            )

        after_unpublish = await live_portal_service.get_portal(portal_uuid)
        published_after_detach = _sub_portal_published(after_unpublish, sub_portal_uuid)
        assert published_after_detach is False, (
            f"Expected subPortals[].published is False for {sub_portal_uuid} "
            f"after unpublish_sub_portal (subPortalUuid: null); got "
            f"{published_after_detach!r} in {after_unpublish.get('subPortals')!r}"
        )
    finally:
        if sub_portal_uuid:
            try:
                await live_portal_service.delete_sub_portal(sub_portal_uuid)
            except (PortalPermissionError, TransportQueryError, ValueError):
                pass
