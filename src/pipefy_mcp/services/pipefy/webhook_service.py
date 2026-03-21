"""GraphQL operations for sending inbox emails and webhook management."""

from __future__ import annotations

from typing import Any

from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.webhook_queries import (
    CREATE_AND_SEND_INBOX_EMAIL_MUTATION,
    CREATE_WEBHOOK_MUTATION,
    DELETE_WEBHOOK_MUTATION,
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
