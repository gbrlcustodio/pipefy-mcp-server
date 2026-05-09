from __future__ import annotations

from gql import gql

GET_ORGANIZATION_QUERY = gql(
    """
    query GetOrganization($id: ID!) {
        organization(id: $id) {
            id
            uuid
            name
            planName
            role
            membersCount
            pipesCount
            createdAt
        }
    }
    """
)

__all__ = [
    "GET_ORGANIZATION_QUERY",
]
