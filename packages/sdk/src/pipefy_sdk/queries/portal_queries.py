"""GraphQL queries for Pipefy portal read operations (Interfaces schema)."""

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

__all__ = [
    "GET_PORTAL_QUERY",
    "LIST_PORTALS_QUERY",
]
