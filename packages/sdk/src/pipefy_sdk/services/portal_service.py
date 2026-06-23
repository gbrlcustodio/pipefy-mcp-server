"""Service for Pipefy portal operations (Interfaces + Internal API routing)."""

from __future__ import annotations

import json
import logging
from typing import Any

from gql.transport.exceptions import TransportQueryError
from graphql import DocumentNode

from pipefy_sdk.exceptions import PortalPermissionError
from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.models.portal import (
    CreatePortalElementInput,
    CreatePortalInput,
    PortalElementType,
    UpdatePortalElementInput,
    UpdatePortalInput,
)
from pipefy_sdk.queries.portal_internal_queries import (
    DELETE_SUB_PORTAL_ELEMENT_MUTATION,
    DELETE_SUB_PORTAL_INTERFACE_MUTATION,
    UPDATE_SUB_PORTAL_ELEMENT_MUTATION,
)
from pipefy_sdk.queries.portal_queries import (
    CREATE_ELEMENT_MUTATION,
    CREATE_PAGE_MUTATION,
    CREATE_SUB_PORTAL_MUTATION,
    DELETE_ELEMENT_MUTATION,
    DELETE_INTERFACE_MUTATION,
    DELETE_PAGE_MUTATION,
    DUPLICATE_ELEMENT_MUTATION,
    FIND_OR_CREATE_PORTAL_MUTATION,
    GET_PORTAL_QUERY,
    LIST_PORTALS_QUERY,
    SORT_PAGES_MUTATION,
    UPDATE_ELEMENT_MUTATION,
    UPDATE_INTERFACE_MUTATION,
    UPDATE_PAGE_LAYOUT_MUTATION,
    UPDATE_PAGE_MUTATION,
)
from pipefy_sdk.utils.organization_identifiers import resolve_organization_uuid
from pipefy_sdk.utils.relay import unwrap_relay_connection_nodes

logger = logging.getLogger(__name__)


def _with_uuid_alias(record: dict[str, Any]) -> dict[str, Any]:
    """Expose GraphQL ``id`` as ``uuid`` in portal payloads."""
    if "id" in record and "uuid" not in record:
        return {**record, "uuid": record["id"]}
    return record


_PORTAL_PERMISSION_MESSAGE = (
    "Permission denied. Request organization permissions such as "
    "`create_portal` or `manage_portals` from your admin."
)


def _map_portal_permission_error(
    exc: TransportQueryError,
) -> PortalPermissionError | None:
    """Return ``PortalPermissionError`` only for PERMISSION_DENIED; else ``None``."""
    for err in exc.errors or []:
        if not isinstance(err, dict):
            continue
        extensions = err.get("extensions") or {}
        if extensions.get("code") == "PERMISSION_DENIED":
            return PortalPermissionError(_PORTAL_PERMISSION_MESSAGE)
    return None


def _serialize_interfaces_json(value: dict[str, Any] | list[Any]) -> str:
    """Encode Json scalars for the Interfaces GraphQL endpoint (gql expects strings)."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _normalize_portal_data_sources(
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map agent-friendly keys to Interfaces ``DataSourceInput`` (``repoId``, ``fieldKeys``).

    Accepts ``repoId``, ``repo_uuid``, or ``repoUuid`` per entry. Invalid entries are
    skipped and logged at warning level.
    """
    normalized: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            logger.warning(
                "Skipping portal data_sources[%s]: expected object, got %s",
                index,
                type(source).__name__,
            )
            continue
        repo_id = (
            source.get("repoId") or source.get("repo_uuid") or source.get("repoUuid")
        )
        if not isinstance(repo_id, str) or not repo_id.strip():
            logger.warning(
                "Skipping portal data_sources[%s]: missing repo id "
                "(use repoId, repo_uuid, or repoUuid); keys=%s",
                index,
                sorted(source.keys()),
            )
            continue
        field_keys = source.get("fieldKeys")
        if field_keys is None:
            field_keys = source.get("field_keys", [])
        if not isinstance(field_keys, list):
            field_keys = []
        normalized.append({"repoId": repo_id.strip(), "fieldKeys": field_keys})
    return normalized


async def _execute_interfaces_query_with_portal_errors(
    execute: Any,
    query: Any,
    variables: dict[str, Any],
) -> dict[str, Any]:
    """Run an Interfaces operation and map portal permission failures."""
    try:
        return await execute(query, variables)
    except TransportQueryError as exc:
        permission_error = _map_portal_permission_error(exc)
        if permission_error is not None:
            raise permission_error from exc
        raise


_INTERNAL_API_PERMISSION_DENIED_MARKER = "[code=PERMISSION_DENIED]"


async def _execute_internal_api_query_with_portal_errors(
    execute: Any,
    query: str,
    variables: dict[str, Any],
) -> dict[str, Any]:
    """Run an Internal API operation and map portal permission failures."""
    try:
        return await execute(query, variables)
    except ValueError as exc:
        if _INTERNAL_API_PERMISSION_DENIED_MARKER in str(exc):
            raise PortalPermissionError(_PORTAL_PERMISSION_MESSAGE) from exc
        raise


def _graphql_create_element_input(
    validated: CreatePortalElementInput,
) -> dict[str, Any]:
    """Map validated create input to Interfaces ``createElement`` variables."""
    payload: dict[str, Any] = {
        "page_id": validated.page_id,
        "type": validated.type,
        "metadata": _serialize_interfaces_json(validated.metadata),
    }
    # Always send data_sources (even []). Omitting it makes Pipefy pass nil and crash
    # in UpdateElement#authorized? / CreateDependencies (pipefy-core).
    payload["data_sources"] = _normalize_portal_data_sources(validated.data_sources)
    if validated.element_id is not None:
        payload["id"] = validated.element_id
    if validated.editable is not None:
        payload["editable"] = validated.editable
    if validated.layout is not None:
        payload["layout"] = _serialize_interfaces_json(validated.layout)
    return payload


def _graphql_update_element_input(
    validated: UpdatePortalElementInput,
) -> dict[str, Any]:
    """Map validated update input to Interfaces ``updateElement`` variables."""
    payload: dict[str, Any] = {
        "element_id": validated.element_id,
        "page_id": validated.page_id,
        "metadata": _serialize_interfaces_json(validated.metadata),
    }
    payload["data_sources"] = _normalize_portal_data_sources(validated.data_sources)
    if validated.editable is not None:
        payload["editable"] = validated.editable
    return payload


def _normalize_portal_page(page: dict[str, Any]) -> dict[str, Any]:
    """Normalize a portal page payload with ``uuid`` alias and element ids."""
    page_record = _with_uuid_alias(page)
    elements = [_with_uuid_alias(element) for element in page.get("elements") or []]
    return {**page_record, "elements": elements}


def _normalize_portal_detail(portal: dict[str, Any]) -> dict[str, Any]:
    """Normalize a ``PortalInterface`` detail payload from the Interfaces schema."""
    pages = portal.get("pages") or []
    normalized_pages = []
    for page in pages:
        page_record = _with_uuid_alias(page)
        elements = [_with_uuid_alias(element) for element in page.get("elements") or []]
        normalized_pages.append({**page_record, "elements": elements})
    sub_portals = [
        _with_uuid_alias(sub_portal) for sub_portal in portal.get("subPortals") or []
    ]
    return {
        **_with_uuid_alias(portal),
        "pages": normalized_pages,
        "subPortals": sub_portals,
    }


class PortalService:
    """GraphQL operations for Pipefy portals across multiple endpoints.

    Takes three executors because portal operations span three endpoints: the
    public GraphQL schema, the Interfaces schema, and the internal_api endpoint
    for sub-portal wiring. The executors are injected, not built here; the
    composition root constructs all three over one shared ``auth`` so the OAuth
    token cache is not duplicated.
    """

    def __init__(
        self,
        *,
        public_executor: GraphQLExecutor,
        interfaces_executor: GraphQLExecutor,
        internal_executor: GraphQLExecutor,
    ) -> None:
        """Wire the public, Interfaces, and Internal API executors.

        Args:
            public_executor: Public GraphQL executor (organization-uuid resolution).
            interfaces_executor: Executor aimed at the Interfaces schema endpoint.
            internal_executor: Executor for sub-portal element wiring mutations.
        """
        self._public_executor = public_executor
        self._interfaces_executor = interfaces_executor
        self._internal_executor = internal_executor

    async def execute_interfaces_query(
        self,
        query: DocumentNode,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a GraphQL query or mutation on the Interfaces schema.

        Args:
            query: Parsed GraphQL document (``gql()`` output).
            variables: Variable map for the operation.
        """
        return await self._interfaces_executor.execute_query(query, variables)

    async def execute_internal_api_query(
        self,
        query: DocumentNode,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a GraphQL query or mutation on the Internal API endpoint.

        Args:
            query: Parsed GraphQL document (``gql()`` output).
            variables: Variable map for the operation.
        """
        return await self._internal_executor.execute_query(query, variables)

    async def list_portals(
        self,
        organization_uuid: str | int,
        search_term: str | None = None,
    ) -> list[dict[str, Any]]:
        """List portals for an organization via the Interfaces schema.

        Args:
            organization_uuid: Organization UUID, or numeric organization id.
            search_term: Optional name filter forwarded as ``searchTerm``.
        """
        resolved_org_uuid = await resolve_organization_uuid(
            self._public_executor.execute_query,
            organization_uuid,
        )
        variables: dict[str, Any] = {
            "org_uuid": resolved_org_uuid,
            "filterBySubType": "portal",
        }
        if search_term is not None:
            variables["searchTerm"] = search_term
        data = await self.execute_interfaces_query(LIST_PORTALS_QUERY, variables)
        nodes = unwrap_relay_connection_nodes(data.get("interfaces"))
        return [_with_uuid_alias(node) for node in nodes]

    async def get_portal(self, portal_uuid: str) -> dict[str, Any]:
        """Fetch a portal by UUID including pages, elements, and sub-portals.

        Args:
            portal_uuid: Portal interface UUID.

        Raises:
            ValueError: When ``portalInterface`` resolves to null.
        """
        data = await self.execute_interfaces_query(
            GET_PORTAL_QUERY, {"uuid": portal_uuid}
        )
        portal = data.get("portalInterface")
        if portal is None:
            msg = f"Portal '{portal_uuid}' was not found."
            raise ValueError(msg)
        return _normalize_portal_detail(portal)

    async def create_portal(self, organization_uuid: str | int) -> dict[str, Any]:
        """Create or fetch the organization's main portal (idempotent template flow).

        Args:
            organization_uuid: Organization UUID or numeric organization id.

        Returns:
            Portal interface summary with ``uuid`` alias for ``id``.
        """
        portal_input = CreatePortalInput.model_validate(
            {"organization_uuid": organization_uuid}
        )
        resolved_org_uuid = await resolve_organization_uuid(
            self._public_executor.execute_query,
            portal_input.organization_uuid,
        )
        data = await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            FIND_OR_CREATE_PORTAL_MUTATION,
            {"input": {"orgUuid": resolved_org_uuid, "subType": "portal"}},
        )
        interface = (data.get("findOrCreateInterfaceByTemplate") or {}).get("interface")
        if not isinstance(interface, dict):
            msg = "findOrCreateInterfaceByTemplate returned no interface."
            raise ValueError(msg)
        return _with_uuid_alias(interface)

    async def update_portal(
        self,
        interface_uuid: str,
        *,
        name: str | None = None,
        visibility: str | None = None,
        color: str | None = None,
        icon: str | None = None,
        display_pipefy_header: bool | None = None,
    ) -> dict[str, Any]:
        """Update portal metadata on the Interfaces schema.

        Args:
            interface_uuid: Portal interface UUID.
            name: Optional display name.
            visibility: ``internal``, ``private``, or ``public``.
            color: Optional theme color.
            icon: Optional icon identifier.
            display_pipefy_header: Whether to show the Pipefy header.
        """
        portal_input = UpdatePortalInput(
            interface_uuid=interface_uuid,
            name=name,
            visibility=visibility,
            color=color,
            icon=icon,
            display_pipefy_header=display_pipefy_header,
        )
        variables = {
            "input": portal_input.model_dump(
                exclude_unset=True,
                exclude_none=True,
                by_alias=True,
            )
        }
        data = await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            UPDATE_INTERFACE_MUTATION,
            variables,
        )
        interface = (data.get("updateInterface") or {}).get("interface")
        if not isinstance(interface, dict):
            msg = "updateInterface returned no interface."
            raise ValueError(msg)
        return _with_uuid_alias(interface)

    async def delete_portal(self, interface_uuid: str) -> dict[str, Any]:
        """Delete a portal interface (irreversible).

        Args:
            interface_uuid: Portal interface UUID.
        """
        return await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            DELETE_INTERFACE_MUTATION,
            {"input": {"interface_uuid": interface_uuid}},
        )

    async def create_portal_page(
        self,
        interface_uuid: str,
        title: str,
        *,
        description: str | None = None,
        index: int | None = None,
    ) -> dict[str, Any]:
        """Create a portal page on the Interfaces schema.

        On an empty main portal, ``createPage`` without ``elements`` may
        auto-provision a templated page with multiple default elements.

        Args:
            interface_uuid: Parent portal interface UUID.
            title: Page title.
            description: Optional page description.
            index: Optional sort index.
        """
        page_input: dict[str, Any] = {
            "interface_uuid": interface_uuid,
            "title": title,
        }
        if description is not None:
            page_input["description"] = description
        if index is not None:
            page_input["index"] = index
        data = await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            CREATE_PAGE_MUTATION,
            {"input": page_input},
        )
        page = (data.get("createPage") or {}).get("page")
        if not isinstance(page, dict):
            msg = "createPage returned no page."
            raise ValueError(msg)
        return _normalize_portal_page(page)

    async def update_portal_page(
        self,
        interface_uuid: str,
        page_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        index: int | None = None,
    ) -> dict[str, Any]:
        """Update portal page metadata.

        Args:
            interface_uuid: Parent portal interface UUID.
            page_id: Page UUID.
            title: Optional new title.
            description: Optional new description.
            index: Optional sort index.
        """
        page_input: dict[str, Any] = {
            "interface_uuid": interface_uuid,
            "page_id": page_id,
        }
        if title is not None:
            page_input["title"] = title
        if description is not None:
            page_input["description"] = description
        if index is not None:
            page_input["index"] = index
        data = await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            UPDATE_PAGE_MUTATION,
            {"input": page_input},
        )
        page = (data.get("updatePage") or {}).get("page")
        if not isinstance(page, dict):
            msg = "updatePage returned no page."
            raise ValueError(msg)
        return _normalize_portal_page(page)

    async def delete_portal_page(
        self, interface_uuid: str, page_id: str
    ) -> dict[str, Any]:
        """Delete a portal page (irreversible).

        Args:
            interface_uuid: Parent portal interface UUID.
            page_id: Page UUID.
        """
        return await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            DELETE_PAGE_MUTATION,
            {"input": {"interface_uuid": interface_uuid, "page_id": page_id}},
        )

    async def sort_portal_pages(
        self, interface_uuid: str, page_ids: list[str]
    ) -> dict[str, Any]:
        """Reorder portal pages by id list.

        Args:
            interface_uuid: Parent portal interface UUID.
            page_ids: Ordered list of page UUIDs.
        """
        return await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            SORT_PAGES_MUTATION,
            {"input": {"interface_uuid": interface_uuid, "page_ids": page_ids}},
        )

    async def update_portal_page_layout(
        self, page_id: str, layout: dict[str, Any]
    ) -> dict[str, Any]:
        """Update a portal page grid layout (full layout blob).

        Args:
            page_id: Page UUID (no parent ``interface_uuid`` on this mutation).
            layout: Layout JSON as required by ``updatePageLayout``.
        """
        return await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            UPDATE_PAGE_LAYOUT_MUTATION,
            {
                "input": {
                    "page_id": page_id,
                    "layout": _serialize_interfaces_json(layout),
                }
            },
        )

    async def create_portal_element(
        self,
        page_id: str,
        *,
        type: PortalElementType,
        metadata: dict[str, Any],
        data_sources: list[dict[str, Any]] | None = None,
        element_id: str | None = None,
        editable: bool | None = None,
        layout: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a portal page element on the Interfaces schema.

        Args:
            page_id: Parent page UUID.
            type: One of the 15 ``InterfacePageElementType`` values.
            metadata: Element metadata JSON (validated per ``type``).
            data_sources: Optional data source bindings (e.g. for ``forms``).
            element_id: Optional client-provided element UUID (GraphQL ``id``).
            editable: Optional editable flag.
            layout: Optional layout JSON.
        """
        validated = CreatePortalElementInput.model_validate(
            {
                "page_id": page_id,
                "type": type,
                "metadata": metadata,
                "data_sources": data_sources if data_sources is not None else [],
                "element_id": element_id,
                "editable": editable,
                "layout": layout,
            }
        )
        data = await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            CREATE_ELEMENT_MUTATION,
            {"input": _graphql_create_element_input(validated)},
        )
        element = (data.get("createElement") or {}).get("element")
        if not isinstance(element, dict):
            msg = "createElement returned no element."
            raise ValueError(msg)
        return _with_uuid_alias(element)

    async def update_portal_element(
        self,
        element_id: str,
        page_id: str,
        *,
        type: PortalElementType,
        metadata: dict[str, Any],
        data_sources: list[dict[str, Any]] | None = None,
        editable: bool | None = None,
    ) -> dict[str, Any]:
        """Update a portal page element (full ``metadata`` replace).

        The returned ``metadata`` is the validated input echo: ``updateElement`` only
        returns ``success``, not the stored element. Use ``get_portal`` for a
        read-after-write view of what Pipefy persisted.

        Args:
            element_id: Element UUID.
            page_id: Parent page UUID.
            type: Element type for client-side metadata validation only.
            metadata: Complete metadata blob (Pipefy replaces the whole object).
            data_sources: Optional data source bindings.
            editable: Optional editable flag.
        """
        validated = UpdatePortalElementInput.model_validate(
            {
                "element_id": element_id,
                "page_id": page_id,
                "type": type,
                "metadata": metadata,
                "data_sources": data_sources if data_sources is not None else [],
                "editable": editable,
            }
        )
        data = await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            UPDATE_ELEMENT_MUTATION,
            {"input": _graphql_update_element_input(validated)},
        )
        update_payload = data.get("updateElement") or {}
        if not update_payload.get("success"):
            msg = (
                f"updateElement returned success=false for element_id={element_id!r} "
                f"on page_id={page_id!r}."
            )
            raise ValueError(msg)
        return _with_uuid_alias(
            {
                "id": validated.element_id,
                "type": validated.type,
                "metadata": validated.metadata,
            }
        )

    async def delete_portal_element(
        self, element_id: str, page_id: str
    ) -> dict[str, Any]:
        """Delete a portal page element (irreversible).

        Args:
            element_id: Element UUID.
            page_id: Parent page UUID.
        """
        return await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            DELETE_ELEMENT_MUTATION,
            {"input": {"element_id": element_id, "page_id": page_id}},
        )

    async def duplicate_portal_element(
        self,
        *,
        element_id: str,
        portal_uuid: str,
        page_id: str,
    ) -> dict[str, Any]:
        """Duplicate a portal page element on the same portal page.

        ``portal_uuid`` and ``page_id`` identify where the source element lives
        (not a cross-page destination). Pipefy appends a copy on that page.

        Args:
            element_id: Element UUID to duplicate.
            portal_uuid: Portal interface UUID that owns the page.
            page_id: Page UUID that contains the element.
        """
        data = await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            DUPLICATE_ELEMENT_MUTATION,
            {
                "input": {
                    "elementUuid": element_id,
                    "interfaceUuid": portal_uuid,
                    "pageUuid": page_id,
                }
            },
        )
        element = (data.get("duplicateElement") or {}).get("element")
        if not isinstance(element, dict):
            msg = "duplicateElement returned no element."
            raise ValueError(msg)
        return _with_uuid_alias(element)

    async def create_sub_portal(
        self,
        main_portal_uuid: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Create a sub-portal attached to a main portal (Interfaces schema).

        Args:
            main_portal_uuid: Parent main portal interface UUID.
            name: Optional display name; omitted from the mutation when ``None``.
        """
        portal_input: dict[str, Any] = {"mainPortalUuid": main_portal_uuid}
        if name is not None:
            portal_input["name"] = name
        data = await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            CREATE_SUB_PORTAL_MUTATION,
            {"input": portal_input},
        )
        sub_portal = (data.get("createSubPortal") or {}).get("subPortal")
        if not isinstance(sub_portal, dict):
            msg = "createSubPortal returned no subPortal."
            raise ValueError(msg)
        return _with_uuid_alias(sub_portal)

    async def update_sub_portal_element(
        self,
        portal_uuid: str,
        element_id: str,
        sub_portal_uuid: str,
    ) -> dict[str, Any]:
        """Attach a sub-portal to a portal page element (Internal API).

        Args:
            portal_uuid: Main portal interface UUID.
            element_id: Page element UUID (e.g. templated ``forms`` slot).
            sub_portal_uuid: Sub-portal UUID to wire to the element.
        """
        return await _execute_internal_api_query_with_portal_errors(
            self.execute_internal_api_query,
            UPDATE_SUB_PORTAL_ELEMENT_MUTATION,
            {
                "input": {
                    "portalUuid": portal_uuid,
                    "elementId": element_id,
                    "subPortalUuid": sub_portal_uuid,
                }
            },
        )

    async def publish_sub_portal(
        self,
        portal_uuid: str,
        element_id: str,
        sub_portal_uuid: str,
    ) -> dict[str, Any]:
        """Publish a sub-portal on a page element via ``updateSubPortalElement``.

        Args:
            portal_uuid: Main portal interface UUID.
            element_id: Page element UUID.
            sub_portal_uuid: Sub-portal UUID to attach.
        """
        return await self.update_sub_portal_element(
            portal_uuid,
            element_id,
            sub_portal_uuid,
        )

    async def unpublish_sub_portal(
        self,
        portal_uuid: str,
        element_id: str,
    ) -> dict[str, Any]:
        """Unpublish a sub-portal from a page element via ``updateSubPortalElement``.

        Sends ``subPortalUuid: null`` to clear the link. Distinct from
        ``delete_sub_portal_element`` (removes the wiring slot) and
        ``delete_sub_portal`` (deletes the sub-portal entity).

        Args:
            portal_uuid: Main portal interface UUID.
            element_id: Page element UUID.
        """
        return await _execute_internal_api_query_with_portal_errors(
            self.execute_internal_api_query,
            UPDATE_SUB_PORTAL_ELEMENT_MUTATION,
            {
                "input": {
                    "portalUuid": portal_uuid,
                    "elementId": element_id,
                    "subPortalUuid": None,
                }
            },
        )

    async def delete_sub_portal_element(
        self,
        portal_uuid: str,
        element_id: str,
    ) -> dict[str, Any]:
        """Remove sub-portal wiring from a page element (Internal API).

        Args:
            portal_uuid: Main portal interface UUID.
            element_id: Page element UUID.
        """
        return await _execute_internal_api_query_with_portal_errors(
            self.execute_internal_api_query,
            DELETE_SUB_PORTAL_ELEMENT_MUTATION,
            {"input": {"portalUuid": portal_uuid, "elementId": element_id}},
        )

    async def delete_sub_portal(self, uuid: str) -> dict[str, Any]:
        """Delete a sub-portal entity (irreversible; Internal API).

        Args:
            uuid: Sub-portal UUID.
        """
        return await _execute_internal_api_query_with_portal_errors(
            self.execute_internal_api_query,
            DELETE_SUB_PORTAL_INTERFACE_MUTATION,
            {"input": {"uuid": uuid}},
        )
