"""GraphQL queries and mutations for Pipefy traditional automations."""

from __future__ import annotations

from gql import gql

GET_AUTOMATION_QUERY = gql(
    """
    query automation($id: ID!) {
        automation(id: $id) {
            id
            name
            active
            event_id
            action_id
            actionEnabled
            disabledReason
            created_at
            event_repo {
                id
                name
            }
        }
    }
    """
)

GET_PIPE_ORGANIZATION_ID_QUERY = gql(
    """
    query automationPipeOrganizationId($id: ID!) {
        pipe(id: $id) {
            organizationId
        }
    }
    """
)

GET_AUTOMATIONS_BY_ORG_QUERY = gql(
    """
    query automationsForOrganization($organizationId: ID!) {
        automations(organizationId: $organizationId) {
            nodes {
                id
                name
                active
            }
        }
    }
    """
)

GET_AUTOMATIONS_FOR_ORG_AND_REPO_QUERY = gql(
    """
    query automationsForOrgAndRepo($organizationId: ID!, $repoId: ID!) {
        automations(organizationId: $organizationId, repoId: $repoId) {
            nodes {
                id
                name
                active
            }
        }
    }
    """
)

GET_AUTOMATION_ACTIONS_QUERY = gql(
    """
    query automationActions($repoId: ID!) {
        automationActions(repoId: $repoId) {
            id
            icon
            enabled
            acceptedParameters
            disabledReason
            eventsBlacklist
            initiallyHidden
            triggerEvents
        }
    }
    """
)

GET_AUTOMATION_EVENTS_QUERY = gql(
    """
    query automationEvents {
        automationEvents {
            id
            icon
            acceptedParameters
            actionsBlacklist
        }
    }
    """
)

CREATE_AUTOMATION_MUTATION = gql(
    """
    mutation createAutomation($input: CreateAutomationInput!) {
        createAutomation(input: $input) {
            automation {
                id
                name
                active
            }
            error_details {
                object_name
                object_key
                messages
            }
        }
    }
    """
)

UPDATE_AUTOMATION_MUTATION = gql(
    """
    mutation updateAutomation($input: UpdateAutomationInput!) {
        updateAutomation(input: $input) {
            automation {
                id
                name
                active
            }
            error_details {
                object_name
                object_key
                messages
            }
        }
    }
    """
)

DELETE_AUTOMATION_MUTATION = gql(
    """
    mutation deleteAutomation($input: DeleteAutomationInput!) {
        deleteAutomation(input: $input) {
            success
        }
    }
    """
)

CREATE_AUTOMATION_SIMULATION_MUTATION = gql(
    """
    mutation createAutomationSimulation($input: CreateAutomationSimulationInput!) {
        createAutomationSimulation(input: $input) {
            simulationId
            clientMutationId
        }
    }
    """
)

AUTOMATION_SIMULATION_QUERY = gql(
    """
    query automationSimulation($simulationId: ID!) {
        automationSimulation(simulationId: $simulationId) {
            status
            details {
                errorType
                message
            }
            simulationResult
        }
    }
    """
)

__all__ = [
    "AUTOMATION_SIMULATION_QUERY",
    "CREATE_AUTOMATION_MUTATION",
    "CREATE_AUTOMATION_SIMULATION_MUTATION",
    "DELETE_AUTOMATION_MUTATION",
    "GET_AUTOMATION_ACTIONS_QUERY",
    "GET_AUTOMATION_EVENTS_QUERY",
    "GET_AUTOMATION_QUERY",
    "GET_AUTOMATIONS_BY_ORG_QUERY",
    "GET_AUTOMATIONS_FOR_ORG_AND_REPO_QUERY",
    "GET_PIPE_ORGANIZATION_ID_QUERY",
    "UPDATE_AUTOMATION_MUTATION",
]
