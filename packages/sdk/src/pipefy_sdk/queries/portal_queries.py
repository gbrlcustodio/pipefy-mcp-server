"""GraphQL queries for Pipefy portal read operations (Interfaces schema)."""

from __future__ import annotations

from gql import gql

LIST_PORTALS_QUERY = gql(
    """
    query ListPortals(
        $org_uuid: ID!
        $filterBySubType: InterfaceSubType!
        $searchTerm: String
    ) {
        interfaces(
            org_uuid: $org_uuid
            filterBySubType: $filterBySubType
            searchTerm: $searchTerm
        ) {
            edges {
                node {
                    uuid
                    name
                    visibility
                    published
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
            uuid
            name
            visibility
            published
            pages {
                nodes {
                    uuid
                    title
                    elements {
                        uuid
                        type
                        metadata
                    }
                }
            }
            subPortals {
                uuid
                name
            }
        }
    }
    """
)

__all__ = [
    "GET_PORTAL_QUERY",
    "LIST_PORTALS_QUERY",
]
