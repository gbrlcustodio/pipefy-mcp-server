from gql import gql

# NOTE: Keep this module free of runtime logic. Only GraphQL operation constants.

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

DELETE_CARD_MUTATION = gql(
    """
    mutation ($input: DeleteCardInput!) {
        deleteCard(input: $input) {
            success
        }
    }
    """
)

GET_CARD_QUERY = gql(
    """
    query ($card_id: ID!) {
        card(id: $card_id) {
            id
            title
            pipe {
                id
                name
            }
            current_phase {
                id
                name
            }
        }
    }
    """
)

GET_CARDS_QUERY = gql(
    """
    query ($pipe_id: ID!, $search: CardSearch) {
        cards(pipe_id: $pipe_id, search: $search) {
            edges {
                node {
                    id
                    title
                    current_phase {
                        id
                        name
                    }
                }
            }
        }
    }
    """
)

MOVE_CARD_TO_PHASE_MUTATION = gql(
    """
    mutation ($input: MoveCardToPhaseInput!) {
        moveCardToPhase (input: $input) {
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
