"""GraphQL mutations for organization service-account provisioning.

CreateServiceAccountInput: organizationUuid, name, role, optional description
and expirationTime ({ unit, value }).
DeleteServiceAccountInput: organizationUuid, serviceAccountUuid.

The create payload returns the OAuth2 client credentials (``client { id secret }``)
and the token endpoint once, at creation time — there is no query to read them
back later.
"""

from __future__ import annotations

from gql import gql

CREATE_SERVICE_ACCOUNT_MUTATION = gql(
    """
    mutation CreateServiceAccount($input: CreateServiceAccountInput!) {
        createServiceAccount(input: $input) {
            serviceAccount {
                id
                uuid
                email
                name
                role {
                    name
                }
                description
                client {
                    id
                    secret
                }
                token {
                    endpoint
                }
            }
        }
    }
    """
)

DELETE_SERVICE_ACCOUNT_MUTATION = gql(
    """
    mutation DeleteServiceAccount($input: DeleteServiceAccountInput!) {
        deleteServiceAccount(input: $input) {
            success
        }
    }
    """
)

__all__ = [
    "CREATE_SERVICE_ACCOUNT_MUTATION",
    "DELETE_SERVICE_ACCOUNT_MUTATION",
]
