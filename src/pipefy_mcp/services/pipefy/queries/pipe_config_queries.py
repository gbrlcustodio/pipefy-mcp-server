from __future__ import annotations

from gql import gql

CREATE_PIPE_MUTATION = gql(
    """
    mutation ($input: CreatePipeInput!) {
        createPipe(input: $input) {
            pipe {
                id
                name
                startFormPhaseId
            }
        }
    }
    """
)

UPDATE_PIPE_MUTATION = gql(
    """
    mutation ($input: UpdatePipeInput!) {
        updatePipe(input: $input) {
            pipe {
                id
                name
            }
        }
    }
    """
)

DELETE_PIPE_MUTATION = gql(
    """
    mutation ($input: DeletePipeInput!) {
        deletePipe(input: $input) {
            success
        }
    }
    """
)

CLONE_PIPE_MUTATION = gql(
    """
    mutation ($input: ClonePipesInput!) {
        clonePipes(input: $input) {
            pipes {
                id
                name
                phases {
                    id
                    name
                }
            }
        }
    }
    """
)

CREATE_PHASE_MUTATION = gql(
    """
    mutation ($input: CreatePhaseInput!) {
        createPhase(input: $input) {
            phase {
                id
                name
                done
            }
        }
    }
    """
)

UPDATE_PHASE_MUTATION = gql(
    """
    mutation ($input: UpdatePhaseInput!) {
        updatePhase(input: $input) {
            phase {
                id
                name
                done
            }
        }
    }
    """
)

DELETE_PHASE_MUTATION = gql(
    """
    mutation ($input: DeletePhaseInput!) {
        deletePhase(input: $input) {
            success
        }
    }
    """
)

CREATE_PHASE_FIELD_MUTATION = gql(
    """
    mutation ($input: CreatePhaseFieldInput!) {
        createPhaseField(input: $input) {
            phase_field {
                id
                internal_id
                uuid
                label
                type
            }
        }
    }
    """
)

UPDATE_PHASE_FIELD_MUTATION = gql(
    """
    mutation ($input: UpdatePhaseFieldInput!) {
        updatePhaseField(input: $input) {
            phase_field {
                id
                label
                type
            }
        }
    }
    """
)

DELETE_PHASE_FIELD_MUTATION = gql(
    """
    mutation ($input: DeletePhaseFieldInput!) {
        deletePhaseField(input: $input) {
            success
        }
    }
    """
)

CREATE_LABEL_MUTATION = gql(
    """
    mutation ($input: CreateLabelInput!) {
        createLabel(input: $input) {
            label {
                id
                name
                color
            }
        }
    }
    """
)

UPDATE_LABEL_MUTATION = gql(
    """
    mutation ($input: UpdateLabelInput!) {
        updateLabel(input: $input) {
            label {
                id
                name
                color
            }
        }
    }
    """
)

DELETE_LABEL_MUTATION = gql(
    """
    mutation ($input: DeleteLabelInput!) {
        deleteLabel(input: $input) {
            success
        }
    }
    """
)

CREATE_FIELD_CONDITION_MUTATION = gql(
    """
    mutation ($input: createFieldConditionInput!) {
        createFieldCondition(input: $input) {
            fieldCondition {
                id
            }
        }
    }
    """
)

UPDATE_FIELD_CONDITION_MUTATION = gql(
    """
    mutation ($input: UpdateFieldConditionInput!) {
        updateFieldCondition(input: $input) {
            fieldCondition {
                id
            }
        }
    }
    """
)

DELETE_FIELD_CONDITION_MUTATION = gql(
    """
    mutation ($input: DeleteFieldConditionInput!) {
        deleteFieldCondition(input: $input) {
            success
        }
    }
    """
)

GET_FIELD_CONDITIONS_QUERY = gql(
    """
    query ($phaseId: ID!) {
        phase(id: $phaseId) {
            fieldConditions {
                id
                name
                condition {
                    expressions {
                        field_address
                        operation
                        value
                    }
                }
                actions {
                    phaseFieldId
                }
            }
        }
    }
    """
)

GET_FIELD_CONDITION_QUERY = gql(
    """
    query ($id: ID!) {
        fieldCondition(id: $id) {
            id
            name
            phase {
                id
                name
            }
            condition {
                expressions {
                    field_address
                    operation
                    value
                }
            }
            actions {
                phaseFieldId
            }
        }
    }
    """
)

__all__ = [
    "CLONE_PIPE_MUTATION",
    "CREATE_FIELD_CONDITION_MUTATION",
    "CREATE_LABEL_MUTATION",
    "CREATE_PHASE_FIELD_MUTATION",
    "CREATE_PHASE_MUTATION",
    "CREATE_PIPE_MUTATION",
    "DELETE_FIELD_CONDITION_MUTATION",
    "DELETE_LABEL_MUTATION",
    "DELETE_PHASE_FIELD_MUTATION",
    "DELETE_PHASE_MUTATION",
    "DELETE_PIPE_MUTATION",
    "GET_FIELD_CONDITION_QUERY",
    "GET_FIELD_CONDITIONS_QUERY",
    "UPDATE_FIELD_CONDITION_MUTATION",
    "UPDATE_LABEL_MUTATION",
    "UPDATE_PHASE_FIELD_MUTATION",
    "UPDATE_PHASE_MUTATION",
    "UPDATE_PIPE_MUTATION",
]
