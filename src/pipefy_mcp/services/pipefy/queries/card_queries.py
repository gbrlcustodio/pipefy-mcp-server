from __future__ import annotations

from gql import gql

CREATE_CARD_MUTATION = gql(
    """
    mutation ($pipe_id: ID!, $fields: [FieldValueInput!]!) {
        createCard(input: {pipe_id: $pipe_id, fields_attributes: $fields}) {
            card {
                id
            }
        }
    }
    """
)

CREATE_COMMENT_MUTATION = gql(
    """
    mutation ($input: CreateCommentInput!) {
        createComment(input: $input) {
            comment {
                id
            }
        }
    }
    """
)

UPDATE_COMMENT_MUTATION = gql(
    """
    mutation ($input: UpdateCommentInput!) {
        updateComment(input: $input) {
            comment {
                id
            }
        }
    }
    """
)

DELETE_COMMENT_MUTATION = gql(
    """
    mutation ($input: DeleteCommentInput!) {
        deleteComment(input: $input) {
            success
        }
    }
    """
)

DELETE_CARD_MUTATION = gql(
    """
    mutation ($input: DeleteCardInput!) {
        deleteCard(input: $input) {
            success
        }
    }
    """
)

DELETE_CARD_RELATION_MUTATION = gql(
    """
    mutation ($childId: ID!, $parentId: ID!, $sourceId: ID!) {
        deleteCardRelation(
            input: { childId: $childId, parentId: $parentId, sourceId: $sourceId }
        ) {
            success
        }
    }
    """
)
# NOTE: As of live public schema introspection, ``deleteCardRelation`` may be absent
# (only ``createCardRelation`` is guaranteed). The MCP tool still sends this
# operation for tenants that expose it; otherwise GraphQL returns an error.

GET_CARD_QUERY = gql(
    """
    query ($card_id: ID!, $includeFields: Boolean!) {
        card(id: $card_id) {
            id
            uuid
            title
            pipe {
                id
                name
            }
            current_phase {
                id
                name
            }
            fields @include(if: $includeFields) {
                name
                value
            }
        }
    }
    """
)

GET_CARDS_QUERY = gql(
    """
    query ($pipe_id: ID!, $search: CardSearch, $first: Int, $after: String, $includeFields: Boolean!) {
        cards(pipe_id: $pipe_id, search: $search, first: $first, after: $after) {
            edges {
                node {
                    id
                    title
                    current_phase {
                        id
                        name
                    }
                    fields @include(if: $includeFields) {
                        name
                        value
                    }
                }
            }
            pageInfo {
                hasNextPage
                endCursor
            }
        }
    }
    """
)

GET_CARD_RELATIONS_QUERY = gql(
    """
    query ($cardId: ID!) {
        card(id: $cardId) {
            child_relations {
                name
                pipe {
                    id
                    name
                }
                cards {
                    id
                    title
                }
            }
            parent_relations {
                name
                pipe {
                    id
                    name
                }
                cards {
                    id
                    title
                }
            }
        }
    }
    """
)

FIND_CARDS_QUERY = gql(
    """
    query ($pipeId: ID!, $search: FindCards!, $includeFields: Boolean!, $first: Int, $after: String) {
        findCards(pipeId: $pipeId, search: $search, first: $first, after: $after) {
            edges {
                node {
                    id
                    title
                    current_phase {
                        id
                        name
                    }
                    fields @include(if: $includeFields) {
                        name
                        value
                    }
                }
            }
            pageInfo {
                hasNextPage
                endCursor
            }
        }
    }
    """
)

MOVE_CARD_TO_PHASE_MUTATION = gql(
    """
    mutation ($input: MoveCardToPhaseInput!) {
        moveCardToPhase(input: $input) {
            clientMutationId
        }
    }
    """
)

UPDATE_CARD_FIELD_MUTATION = gql(
    """
    mutation ($input: UpdateCardFieldInput!) {
        updateCardField(input: $input) {
            card {
                id
                title
                fields {
                    field {
                        id
                        label
                    }
                    value
                }
                updated_at
            }
            success
            clientMutationId
        }
    }
    """
)

UPDATE_CARD_MUTATION = gql(
    """
    mutation ($input: UpdateCardInput!) {
        updateCard(input: $input) {
            card {
                id
                title
                current_phase {
                    id
                    name
                }
                assignees {
                    id
                    name
                    email
                }
                labels {
                    id
                    name
                }
                due_date
                updated_at
            }
            clientMutationId
        }
    }
    """
)

UPDATE_FIELDS_VALUES_MUTATION = gql(
    """
    mutation ($input: UpdateFieldsValuesInput!) {
        updateFieldsValues(input: $input) {
            success
            userErrors {
                field
                message
            }
            updatedNode {
                ... on Card {
                    id
                    title
                    fields {
                        name
                        value
                        filled_at
                        updated_at
                    }
                    assignees {
                        id
                        name
                    }
                    labels {
                        id
                        name
                    }
                    updated_at
                }
            }
        }
    }
    """
)

__all__ = [
    "CREATE_CARD_MUTATION",
    "CREATE_COMMENT_MUTATION",
    "DELETE_CARD_MUTATION",
    "DELETE_CARD_RELATION_MUTATION",
    "DELETE_COMMENT_MUTATION",
    "FIND_CARDS_QUERY",
    "GET_CARD_QUERY",
    "GET_CARD_RELATIONS_QUERY",
    "GET_CARDS_QUERY",
    "MOVE_CARD_TO_PHASE_MUTATION",
    "UPDATE_CARD_FIELD_MUTATION",
    "UPDATE_CARD_MUTATION",
    "UPDATE_COMMENT_MUTATION",
    "UPDATE_FIELDS_VALUES_MUTATION",
]
