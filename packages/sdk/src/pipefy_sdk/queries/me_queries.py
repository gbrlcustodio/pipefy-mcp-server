from __future__ import annotations

from gql import gql

GET_ME_QUERY = gql(
    """
    query GetMe {
        me {
            email
            name
        }
    }
    """
)

__all__ = [
    "GET_ME_QUERY",
]
