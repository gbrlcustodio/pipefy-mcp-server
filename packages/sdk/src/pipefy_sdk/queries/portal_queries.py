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

__all__ = [
    "DELETE_INTERFACE_MUTATION",
    "FIND_OR_CREATE_PORTAL_MUTATION",
    "GET_PORTAL_QUERY",
    "LIST_PORTALS_QUERY",
    "UPDATE_INTERFACE_MUTATION",
]
