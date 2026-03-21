"""GraphQL mutations for sending inbox emails and webhook management.

createAndSendInboxEmail: cardId, from, subject, to (required); html, text, cc, bcc optional.
CreateWebhookInput: pipe_id/table_id, url, actions, name, etc.
DeleteWebhookInput: id.
"""

from __future__ import annotations

from gql import gql

# NOTE: Keep this module free of runtime logic. Only GraphQL operation constants.
# API uses createAndSendInboxEmail (not sendInboxEmail); verified via introspection.

CREATE_AND_SEND_INBOX_EMAIL_MUTATION = gql(
    """
    mutation CreateAndSendInboxEmail($input: CreateAndSendInboxEmailInput!) {
        createAndSendInboxEmail(input: $input) {
            emailSent
            errors
            inboxEmail {
                id
            }
        }
    }
    """
)

CREATE_WEBHOOK_MUTATION = gql(
    """
    mutation CreateWebhook($input: CreateWebhookInput!) {
        createWebhook(input: $input) {
            webhook {
                id
                url
                actions
            }
        }
    }
    """
)

DELETE_WEBHOOK_MUTATION = gql(
    """
    mutation DeleteWebhook($input: DeleteWebhookInput!) {
        deleteWebhook(input: $input) {
            success
        }
    }
    """
)

# Alias for tool/service layer (API mutation is createAndSendInboxEmail).
SEND_INBOX_EMAIL_MUTATION = CREATE_AND_SEND_INBOX_EMAIL_MUTATION

__all__ = [
    "CREATE_AND_SEND_INBOX_EMAIL_MUTATION",
    "CREATE_WEBHOOK_MUTATION",
    "DELETE_WEBHOOK_MUTATION",
    "SEND_INBOX_EMAIL_MUTATION",
]
