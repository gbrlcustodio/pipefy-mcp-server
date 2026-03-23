"""GraphQL mutation strings for AI Automation (internal_api endpoint).

Plain strings (not gql()) since internal_api does not support schema validation.
"""

from __future__ import annotations

CREATE_AUTOMATION_MUTATION = """
mutation createAutomation(
  $name: String!,
  $action_id: ID!,
  $event_id: ID!,
  $action_repo_id: ID,
  $event_repo_id: ID,
  $action_params: AutomationActionParamsInput,
  $condition: ConditionInput
) {
  createAutomation(input: {
    name: $name,
    action_id: $action_id,
    event_id: $event_id,
    action_repo_id: $action_repo_id,
    event_repo_id: $event_repo_id,
    action_params: $action_params,
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

UPDATE_AUTOMATION_MUTATION = """
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
