"""GraphQL queries and mutations for Pipefy pipe, table, and card relations."""

from __future__ import annotations

from gql import gql

# Schema: Pipe uses parentsRelations/childrenRelations (not pipe_relations); tables use root table_relations(ids: [ID!]!).

_REPO_TYPES_ID_NAME = """... on Pipe {
    id
    name
}
... on Table {
    id
    name
}"""

_PIPE_RELATION_BODY = (
    """
                id
                name
                allChildrenMustBeDoneToFinishParent
                allChildrenMustBeDoneToMoveParent
                autoFillFieldEnabled
                canConnectExistingItems
                canConnectMultipleItems
                canCreateNewItems
                childMustExistToFinishParent
                childMustExistToMoveParent
                parent {
"""
    + _REPO_TYPES_ID_NAME
    + """
                }
                child {
"""
    + _REPO_TYPES_ID_NAME
    + """
                }
                ownFieldMaps {
                    fieldId
                    inputMode
                    value
                }"""
)

GET_PIPE_RELATIONS_QUERY = gql(
    """
    query GetPipeRelations($pipeId: ID!) {
        pipe(id: $pipeId) {
            id
            parentsRelations {"""
    + _PIPE_RELATION_BODY
    + """
            }
            childrenRelations {"""
    + _PIPE_RELATION_BODY
    + """
            }
        }
    }
    """
)

GET_TABLE_RELATIONS_QUERY = gql(
    """
    query GetTableRelations($ids: [ID!]!) {
        table_relations(ids: $ids) {
            id
            name
            allChildrenMustBeDoneToFinishParent
            allChildrenMustBeDoneToMoveParent
            canConnectExistingItems
            canConnectMultipleItems
            canCreateNewItems
            childMustExistToFinishParent
            childMustExistToMoveParent
            parent {
"""
    + _REPO_TYPES_ID_NAME
    + """
            }
            child {
"""
    + _REPO_TYPES_ID_NAME
    + """
            }
        }
    }
    """
)

CREATE_PIPE_RELATION_MUTATION = gql(
    """
    mutation CreatePipeRelation($input: CreatePipeRelationInput!) {
        createPipeRelation(input: $input) {
            pipeRelation {
                id
                name
            }
        }
    }
    """
)

UPDATE_PIPE_RELATION_MUTATION = gql(
    """
    mutation UpdatePipeRelation($input: UpdatePipeRelationInput!) {
        updatePipeRelation(input: $input) {
            pipeRelation {
                id
                name
            }
        }
    }
    """
)

DELETE_PIPE_RELATION_MUTATION = gql(
    """
    mutation DeletePipeRelation($input: DeletePipeRelationInput!) {
        deletePipeRelation(input: $input) {
            success
        }
    }
    """
)

CREATE_CARD_RELATION_MUTATION = gql(
    """
    mutation CreateCardRelation($input: CreateCardRelationInput!) {
        createCardRelation(input: $input) {
            cardRelation {
                id
            }
        }
    }
    """
)

__all__ = [
    "CREATE_CARD_RELATION_MUTATION",
    "CREATE_PIPE_RELATION_MUTATION",
    "DELETE_PIPE_RELATION_MUTATION",
    "GET_PIPE_RELATIONS_QUERY",
    "GET_TABLE_RELATIONS_QUERY",
    "UPDATE_PIPE_RELATION_MUTATION",
]
