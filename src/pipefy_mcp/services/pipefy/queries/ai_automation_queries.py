"""GraphQL mutation strings for AI Automation (internal_api endpoint).

Mutations are plain strings (not ``gql()``) because ``InternalApiClient``
sends raw GraphQL text via JSON POST — the internal_api endpoint does not
support schema validation that ``gql()`` provides via graphql-core. All
other query files use ``gql()`` constants.
"""

from __future__ import annotations

AI_CREATE_AUTOMATION_MUTATION = """
mutation createAutomation(
  $name: String!,
  $action_id: ID!,
  $event_id: ID!,
  $action_repo_id: ID,
  $event_repo_id: ID,
  $action_params: AutomationActionParamsInput,
  $event_params: AutomationEventParamsInput,
  $condition: ConditionInput
) {
  createAutomation(input: {
    name: $name,
    action_id: $action_id,
    event_id: $event_id,
    action_repo_id: $action_repo_id,
    event_repo_id: $event_repo_id,
    action_params: $action_params,
    event_params: $event_params,
    condition: $condition
  }) {
    automation {
      id
    }
    error_details {
      object_name
      object_key
      messages
    }
  }
}
"""

AI_UPDATE_AUTOMATION_MUTATION = """
mutation updateAutomation($input: UpdateAutomationInput!) {
  updateAutomation(input: $input) {
    automation {
      id
    }
    error_details {
      object_name
      object_key
      messages
    }
  }
}
"""

__all__ = [
    "AI_CREATE_AUTOMATION_MUTATION",
    "AI_UPDATE_AUTOMATION_MUTATION",
]
