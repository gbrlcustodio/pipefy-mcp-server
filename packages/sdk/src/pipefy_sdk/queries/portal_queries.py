"""GraphQL queries and mutations for Pipefy portals (Interfaces schema)."""

from __future__ import annotations

from gql import gql

LIST_PORTALS_QUERY = gql(
    """
    query ListPortals(
        $org_uuid: ID!
        $filterBySubType: InterfaceSubTypeFilter!
        $searchTerm: String
    ) {
        interfaces(
            org_uuid: $org_uuid
            filterBySubType: $filterBySubType
            searchTerm: $searchTerm
        ) {
            edges {
                node {
                    id
                    name
                    visibility
                    subType
                }
            }
        }
    }
    """
)

GET_PORTAL_QUERY = gql(
    """
    query GetPortal($uuid: ID!) {
        portalInterface(uuid: $uuid) {
            id
            name
            visibility
            published
            pages {
                id
                title
                elements {
                    id
                    type
                    metadata
                }
            }
            subPortals {
                id
                name
                published
            }
        }
    }
    """
)

FIND_OR_CREATE_PORTAL_MUTATION = gql(
    """
    mutation FindOrCreatePortal($input: InterfaceCreateByTemplateMutationInput!) {
        findOrCreateInterfaceByTemplate(input: $input) {
            interface {
                id
                name
                visibility
                subType
            }
        }
    }
    """
)

UPDATE_INTERFACE_MUTATION = gql(
    """
    mutation UpdatePortal($input: InterfaceUpdateMutationInput!) {
        updateInterface(input: $input) {
            interface {
                id
                name
                visibility
                subType
            }
        }
    }
    """
)

DELETE_INTERFACE_MUTATION = gql(
    """
    mutation DeletePortal($input: InterfaceDeleteMutationInput!) {
        deleteInterface(input: $input) {
            success
        }
    }
    """
)

CREATE_PAGE_MUTATION = gql(
    """
    mutation CreatePortalPage($input: InterfacePageCreateMutationInput!) {
        createPage(input: $input) {
            page {
                id
                title
                elements {
                    id
                    type
                }
            }
        }
    }
    """
)

UPDATE_PAGE_MUTATION = gql(
    """
    mutation UpdatePortalPage($input: InterfacePageUpdateMutationInput!) {
        updatePage(input: $input) {
            page {
                id
                title
                elements {
                    id
                    type
                }
            }
        }
    }
    """
)

DELETE_PAGE_MUTATION = gql(
    """
    mutation DeletePortalPage($input: InterfacePageDeleteMutationInput!) {
        deletePage(input: $input) {
            success
        }
    }
    """
)

SORT_PAGES_MUTATION = gql(
    """
    mutation SortPortalPages($input: InterfacePageSortMutationInput!) {
        sortPages(input: $input) {
            success
        }
    }
    """
)

UPDATE_PAGE_LAYOUT_MUTATION = gql(
    """
    mutation UpdatePortalPageLayout($input: InterfacePageLayoutUpdateMutationInput!) {
        updatePageLayout(input: $input) {
            success
        }
    }
    """
)

CREATE_ELEMENT_MUTATION = gql(
    """
    mutation CreatePortalElement($input: InterfacePageElementCreateMutationInput!) {
        createElement(input: $input) {
            element {
                id
                type
                metadata
            }
        }
    }
    """
)

UPDATE_ELEMENT_MUTATION = gql(
    """
    mutation UpdatePortalElement($input: InterfacePageElementUpdateMutationInput!) {
        updateElement(input: $input) {
            success
        }
    }
    """
)

DELETE_ELEMENT_MUTATION = gql(
    """
    mutation DeletePortalElement($input: InterfacePageElementDeleteMutationInput!) {
        deleteElement(input: $input) {
            success
        }
    }
    """
)

DUPLICATE_ELEMENT_MUTATION = gql(
    """
    mutation DuplicatePortalElement($input: DuplicateInterfaceElementInput!) {
        duplicateElement(input: $input) {
            element {
                id
                type
                metadata
            }
        }
    }
    """
)

__all__ = [
    "CREATE_ELEMENT_MUTATION",
    "CREATE_PAGE_MUTATION",
    "DELETE_ELEMENT_MUTATION",
    "DELETE_INTERFACE_MUTATION",
    "DELETE_PAGE_MUTATION",
    "DUPLICATE_ELEMENT_MUTATION",
    "FIND_OR_CREATE_PORTAL_MUTATION",
    "GET_PORTAL_QUERY",
    "LIST_PORTALS_QUERY",
    "SORT_PAGES_MUTATION",
    "UPDATE_ELEMENT_MUTATION",
    "UPDATE_INTERFACE_MUTATION",
    "UPDATE_PAGE_LAYOUT_MUTATION",
    "UPDATE_PAGE_MUTATION",
]
