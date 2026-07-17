"""GraphQL queries for LLM provider discovery (read-only).

Covers the organization's provider inventory (custom + Pipefy-managed system
providers in one union), the models a vendor exposes, the organization/owner
default provider, and a provider's dependents. All are reads; provider
mutations ship separately.
"""

from __future__ import annotations

from gql import gql

# allLlmProvidersByOrganization returns a union connection whose nodes are
# either LlmProvider (custom / byom) or SystemLlmProvider (Pipefy-managed).
# __typename plus the shared `type` field (ProviderType: byom | system) both
# discriminate; configuration is JSON with secrets redacted server-side.
GET_LLM_PROVIDERS_QUERY = gql(
    """
    query allLlmProvidersByOrganization(
        $organizationUuid: String!
        $onlyActiveProviders: Boolean
        $first: Int
        $after: String
    ) {
        allLlmProvidersByOrganization(
            organizationUuid: $organizationUuid
            onlyActiveProviders: $onlyActiveProviders
            first: $first
            after: $after
        ) {
            edges {
                node {
                    __typename
                    ... on LlmProvider {
                        id
                        name
                        type
                        active
                        organizationDefault
                        configuration
                    }
                    ... on SystemLlmProvider {
                        id
                        name
                        type
                        organizationDefault
                        systemDefault
                        state
                        description
                        aiCredits
                        deprecationDate
                        configuration
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

GET_AVAILABLE_AI_MODELS_QUERY = gql(
    """
    query availableAiModels($providerName: ProviderName!) {
        availableAiModels(providerName: $providerName)
    }
    """
)

# defaultLlmProvider resolves a single provider for one owner (organization,
# assistant, or behavior); it returns the LlmProvider shape even for a system
# default, with `type` carrying the discriminator.
GET_DEFAULT_LLM_PROVIDER_QUERY = gql(
    """
    query defaultLlmProvider($ownerType: OwnerProvider!, $ownerId: String!) {
        defaultLlmProvider(ownerType: $ownerType, ownerId: $ownerId) {
            id
            name
            type
            active
            organizationDefault
            configuration
        }
    }
    """
)

GET_PROVIDER_DEPENDENCIES_QUERY = gql(
    """
    query providerDependencies(
        $providerId: ID!
        $organizationUuid: String!
        $first: Int
        $after: String
    ) {
        providerDependencies(
            providerId: $providerId
            organizationUuid: $organizationUuid
            first: $first
            after: $after
        ) {
            edges {
                node {
                    ownerId
                    ownerType
                }
            }
            pageInfo {
                hasNextPage
                endCursor
            }
            totalCount
        }
    }
    """
)

__all__ = [
    "GET_AVAILABLE_AI_MODELS_QUERY",
    "GET_DEFAULT_LLM_PROVIDER_QUERY",
    "GET_LLM_PROVIDERS_QUERY",
    "GET_PROVIDER_DEPENDENCIES_QUERY",
]
