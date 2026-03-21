"""GraphQL mutations and queries for sending inbox emails, email templates, and webhook management.

createAndSendInboxEmail: cardId, from, subject, to (required); html, text, cc, bcc optional.
emailTemplates: repoId; filterByName, first, after optional.
parsedEmailTemplate: emailTemplateId, cardUuid (cardUuid optional — omitted returns template without placeholder resolution).
CreateWebhookInput: pipe_id/table_id, url, actions, name, etc.
DeleteWebhookInput: id.
"""

from __future__ import annotations

from gql import gql

# NOTE: Keep this module free of runtime logic. Only GraphQL operation constants.
# API uses createAndSendInboxEmail (not sendInboxEmail); verified via introspection.

GET_EMAIL_TEMPLATES_QUERY = gql(
    """
    query GetEmailTemplates($repoId: ID!, $filterByName: String, $first: Int) {
        emailTemplates(repoId: $repoId, filterByName: $filterByName, first: $first) {
            edges {
                cursor
                node {
                    id
                    name
                    subject
                    body
                    fromEmail
                    fromName
                    toEmail
                    ccEmail
                    bccEmail
                    repoId
                    defaultTemplate
                }
            }
        }
    }
    """
)

GET_PARSED_EMAIL_TEMPLATE_QUERY = gql(
    """
    query GetParsedEmailTemplate($emailTemplateId: ID!, $cardUuid: ID) {
        parsedEmailTemplate(emailTemplateId: $emailTemplateId, cardUuid: $cardUuid) {
            id
            name
            subject
            body
            fromEmail
            fromName
            toEmail
            ccEmail
            bccEmail
            repoId
        }
    }
    """
)

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
    "GET_EMAIL_TEMPLATES_QUERY",
    "GET_PARSED_EMAIL_TEMPLATE_QUERY",
    "SEND_INBOX_EMAIL_MUTATION",
]
