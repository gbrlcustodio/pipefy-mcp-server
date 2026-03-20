"""GraphQL queries and mutations for AI Agent operations."""

from gql import gql

# NOTE: Keep this module free of runtime logic. Only GraphQL operation constants.

GET_AI_AGENT_QUERY = gql(
    """
    query aiAgent($uuid: ID!) {
        aiAgent(uuid: $uuid) {
            uuid
            name
            instruction
            repoUuid
            dataSourceIds
            disabledAt
            needReview
            behaviors {
                id
                name
                active
            }
        }
    }
    """
)

GET_AI_AGENTS_QUERY = gql(
    """
    query aiAgents($repoUuid: ID!) {
        aiAgents(repoUuid: $repoUuid) {
            edges {
                node {
                    uuid
                    name
                    instruction
                    repoUuid
                    disabledAt
                }
            }
        }
    }
    """
)

DELETE_AI_AGENT_MUTATION = gql(
    """
    mutation deleteAiAgent($uuid: ID!) {
        deleteAiAgent(input: { uuid: $uuid }) {
            success
        }
    }
    """
)

CREATE_AI_AGENT_MUTATION = gql(
    """
    mutation createAiAgent($agent: AiAgentInput!) {
        createAiAgent(input: { agent: $agent }) {
            agent {
                uuid
                name
                repoUuid
                instruction
                dataSourceIds
            }
        }
    }
    """
)

TOGGLE_AI_AGENT_STATUS_MUTATION = gql(
    """
    mutation updateAiAgentStatus($uuid: ID!, $active: Boolean!) {
        updateAiAgentStatus(input: { uuid: $uuid, active: $active }) {
            success
        }
    }
    """
)

UPDATE_AI_AGENT_MUTATION = gql(
    """
    mutation updateAiAgent($agent: AiAgentInput!, $uuid: ID!) {
        updateAiAgent(input: { agent: $agent, uuid: $uuid }) {
            agent {
                uuid
                name
                repoUuid
                instruction
                dataSourceIds
                behaviors {
                    id
                    name
                    active
                    eventId: event_id
                    actionId: action_id
                    condition {
                        expressions_structure
                        expressions {
                            id
                            field_address
                            operation
                            value
                            structure_id
                        }
                    }
                    actionParams: action_params {
                        aiBehaviorParams {
                            instruction
                            dataSourceIds
                            referencedFieldIds
                            actionsAttributes {
                                id
                                name
                                actionType
                                referenceId
                                metadata {
                                    destinationPhaseId
                                    pipeId
                                    tableId
                                    fieldsAttributes {
                                        fieldId
                                        inputMode
                                        value
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    """
)
