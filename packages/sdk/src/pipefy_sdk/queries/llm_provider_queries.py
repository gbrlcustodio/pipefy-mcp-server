"""GraphQL queries and mutations for LLM providers.

Reads cover the organization's provider inventory (custom + Pipefy-managed
system providers in one union), the models a vendor exposes, the
organization/owner default provider, and a provider's dependents.

Writes cover custom (BYOM) provider lifecycle — create, update (full
configuration replacement), delete — plus the active-status toggle and the
organization default assignment (set/reset). The create and update selection
sets deliberately omit ``configuration``: the mutation payload exposes it as a
non-null field, but requesting it would echo secret material back to the
caller, so these queries never select it (secrets are never returned).
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

# --- Write mutations (custom / BYOM providers) ---------------------------

# The provider payload's `llmProvider.configuration` is non-null in the schema,
# but selecting it would return secret configuration to the caller, so create
# and update select only non-secret identity/state fields.
_LLM_PROVIDER_WRITE_FIELDS = """
    id
    name
    type
    active
    organizationDefault
"""

CREATE_LLM_PROVIDER_MUTATION = gql(
    """
    mutation createLlmProvider($input: CreateLlmProviderInput!) {
        createLlmProvider(input: $input) {
            llmProvider {
                %s
            }
        }
    }
    """
    % _LLM_PROVIDER_WRITE_FIELDS
)

# A full-replacement update: `configuration` is non-null on the input, so every
# call must send the complete configuration, not a partial patch.
UPDATE_LLM_PROVIDER_MUTATION = gql(
    """
    mutation updateLlmProvider($input: UpdateLlmProviderInput!) {
        updateLlmProvider(input: $input) {
            llmProvider {
                %s
            }
        }
    }
    """
    % _LLM_PROVIDER_WRITE_FIELDS
)

DELETE_LLM_PROVIDER_MUTATION = gql(
    """
    mutation deleteLlmProvider($input: DeleteLlmProviderInput!) {
        deleteLlmProvider(input: $input) {
            success
        }
    }
    """
)

SET_LLM_PROVIDER_ACTIVE_STATUS_MUTATION = gql(
    """
    mutation setLlmProviderActiveStatus($input: SetLlmProviderActiveStatusInput!) {
        setLlmProviderActiveStatus(input: $input) {
            success
        }
    }
    """
)

# setActiveLlmProvider assigns the owner's active/default provider; the returned
# ActiveLlmProvider carries llmProviderId XOR systemLlmProviderId per the choice.
SET_ACTIVE_LLM_PROVIDER_MUTATION = gql(
    """
    mutation setActiveLlmProvider($input: SetActiveLlmProviderInput!) {
        setActiveLlmProvider(input: $input) {
            activeLlmProvider {
                id
                ownerId
                ownerType
                llmProviderId
                systemLlmProviderId
            }
        }
    }
    """
)

RESET_LLM_PROVIDER_OWNER_MUTATION = gql(
    """
    mutation resetLlmProviderOwner($input: ResetLlmProviderOwnerInput!) {
        resetLlmProviderOwner(input: $input) {
            success
        }
    }
    """
)

__all__ = [
    "CREATE_LLM_PROVIDER_MUTATION",
    "DELETE_LLM_PROVIDER_MUTATION",
    "GET_AVAILABLE_AI_MODELS_QUERY",
    "GET_DEFAULT_LLM_PROVIDER_QUERY",
    "GET_LLM_PROVIDERS_QUERY",
    "GET_PROVIDER_DEPENDENCIES_QUERY",
    "RESET_LLM_PROVIDER_OWNER_MUTATION",
    "SET_ACTIVE_LLM_PROVIDER_MUTATION",
    "SET_LLM_PROVIDER_ACTIVE_STATUS_MUTATION",
    "UPDATE_LLM_PROVIDER_MUTATION",
]
