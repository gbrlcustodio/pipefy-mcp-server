"""GraphQL operations for sending inbox emails and webhook management."""

from __future__ import annotations

from typing import Any

from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.card_queries import (
    GET_CARD_INBOX_EMAILS_QUERY,
)
from pipefy_mcp.services.pipefy.queries.webhook_queries import (
    CREATE_AND_SEND_INBOX_EMAIL_MUTATION,
    CREATE_WEBHOOK_MUTATION,
    DELETE_WEBHOOK_MUTATION,
    GET_EMAIL_TEMPLATES_QUERY,
    GET_PARSED_EMAIL_TEMPLATE_QUERY,
)
from pipefy_mcp.settings import PipefySettings

_DEFAULT_WEBHOOK_NAME = "Pipefy Webhook"


def _require_https(url: str, context: str = "url") -> None:
    """Raise ValueError if url is not HTTPS."""
    if not url.strip().lower().startswith("https://"):
        raise ValueError(
            f"Invalid '{context}': must be HTTPS. HTTP URLs are not allowed."
        )


class WebhookService(BasePipefyClient):
    """Send inbox emails and manage webhooks (create, delete)."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    async def get_email_templates(
        self,
        repo_id: str,
        *,
        filter_by_name: str | None = None,
        first: int = 50,
    ) -> dict[str, Any]:
        """List email templates for a pipe or table.

        Args:
            repo_id: Pipe or table ID.
            filter_by_name: Optional case-insensitive partial match on template name.
            first: Max templates to return (default 50).
        """
        variables: dict[str, Any] = {"repoId": repo_id, "first": first}
        if filter_by_name is not None and filter_by_name.strip():
            variables["filterByName"] = filter_by_name.strip()
        return await self.execute_query(GET_EMAIL_TEMPLATES_QUERY, variables)

    async def get_parsed_email_template(
        self,
        email_template_id: str,
        *,
        card_uuid: str | None = None,
    ) -> dict[str, Any]:
        """Get an email template with dynamic placeholders resolved for a card.

        Args:
            email_template_id: ID of the email template.
            card_uuid: Optional card UUID for placeholder resolution (e.g. {{card.title}}).
                When omitted, returns the template without card-based substitution.
        """
        variables: dict[str, Any] = {"emailTemplateId": email_template_id}
        if card_uuid is not None and card_uuid.strip():
            variables["cardUuid"] = card_uuid.strip()
        return await self.execute_query(GET_PARSED_EMAIL_TEMPLATE_QUERY, variables)

    async def send_inbox_email(
        self,
        card_id: str,
        to: list[str],
        subject: str,
        body: str,
        *,
        from_: str,
        **attrs: Any,
    ) -> dict[str, Any]:
        """Send an email from a card's inbox (createAndSendInboxEmail).

        Args:
            card_id: ID of the card with inbox.
            to: List of recipient email addresses.
            subject: Email subject.
            body: Email body (plain text; use attrs for html).
            from_: Sender email address (required by API).
            **attrs: Extra CreateAndSendInboxEmailInput fields (html, cc, bcc, etc.).
        """
        input_obj: dict[str, Any] = {
            "cardId": card_id,
            "from": from_,
            "subject": subject,
            "to": to,
            "text": body,
        }
        for key, value in attrs.items():
            if value is not None:
                input_obj[key] = value
        return await self.execute_query(
            CREATE_AND_SEND_INBOX_EMAIL_MUTATION,
            {"input": input_obj},
        )

    async def create_webhook(
        self,
        pipe_id: str,
        url: str,
        actions: list[str],
        **attrs: Any,
    ) -> dict[str, Any]:
        """Create a webhook for pipe events.

        Args:
            pipe_id: ID of the pipe.
            url: HTTPS URL to receive events.
            actions: List of event action strings (e.g. ['card.create', 'card.move']).
            **attrs: Extra CreateWebhookInput fields (name, filters, headers, etc.).
        """
        _require_https(url, "url")
        input_obj: dict[str, Any] = {
            "pipe_id": pipe_id,
            "url": url,
            "actions": actions,
            "name": attrs.get("name", _DEFAULT_WEBHOOK_NAME),
        }
        for key, value in attrs.items():
            if key == "name":
                continue
            if value is not None:
                input_obj[key] = value
        return await self.execute_query(
            CREATE_WEBHOOK_MUTATION,
            {"input": input_obj},
        )

    async def delete_webhook(self, webhook_id: str) -> dict[str, Any]:
        """Delete a webhook by ID (permanent).

        Args:
            webhook_id: ID of the webhook to delete.
        """
        return await self.execute_query(
            DELETE_WEBHOOK_MUTATION,
            {"input": {"id": webhook_id}},
        )

    async def get_card_inbox_emails(
        self,
        card_id: str,
        *,
        type: str | None = None,
    ) -> dict[str, Any]:
        """List emails (sent and received) for a card's inbox.

        Args:
            card_id: ID of the card with inbox.
            type: Optional filter: 'sent' | 'received'. When omitted, returns all.
        """
        raw = await self.execute_query(
            GET_CARD_INBOX_EMAILS_QUERY,
            {"card_id": card_id},
        )
        card_data = raw.get("card") or {}
        emails = card_data.get("inbox_emails") or []

        if type is not None and type.strip():
            filter_type = type.strip().lower()
            emails = [e for e in emails if (e.get("type") or "").lower() == filter_type]
            card_data = dict(card_data, inbox_emails=emails)

        return {"card": card_data}
