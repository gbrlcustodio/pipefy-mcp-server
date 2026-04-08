"""GraphQL operations for sending inbox emails and webhook management."""

from __future__ import annotations

import logging
from typing import Any

from gql.transport.exceptions import TransportQueryError
from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.card_service import CardService
from pipefy_mcp.services.pipefy.queries.webhook_queries import (
    CREATE_AND_SEND_INBOX_EMAIL_MUTATION,
    CREATE_WEBHOOK_MUTATION,
    DELETE_WEBHOOK_MUTATION,
    GET_CARD_INBOX_EMAILS_QUERY,
    GET_EMAIL_TEMPLATES_QUERY,
    GET_PARSED_EMAIL_TEMPLATE_QUERY,
)
from pipefy_mcp.settings import PipefySettings

logger = logging.getLogger(__name__)

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
        *,
        card_service: CardService | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)
        self._card_service = card_service or CardService(settings=settings, auth=auth)

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
        variables: dict[str, Any] = {"repoId": str(repo_id), "first": first}
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

    async def _resolve_repo_id(
        self, card_id: str, attrs: dict[str, Any]
    ) -> dict[str, Any]:
        """Best-effort resolve ``repoId`` from the card's pipe when omitted.

        Args:
            card_id: Numeric card ID.
            attrs: Mutable copy of extra input fields.

        Returns:
            Updated attrs with ``repoId`` if resolution succeeded, unchanged otherwise.
        """
        if "repoId" in attrs or not card_id.isdigit():
            return attrs
        try:
            card_data = await self._card_service.get_card(card_id)
            pipe_obj = card_data.get("card", {}).get("pipe")
            pipe_id = pipe_obj.get("id") if isinstance(pipe_obj, dict) else None
            if pipe_id is not None:
                return {**attrs, "repoId": str(pipe_id)}
        except (TransportQueryError, KeyError, TypeError):
            logger.debug(
                "Could not auto-resolve repoId for card %s",
                card_id,
                exc_info=True,
            )
        return attrs

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

        When ``repoId`` is omitted and ``card_id`` is numeric, the service best-effort
        fills ``repoId`` from the card's pipe.

        Args:
            card_id: ID of the card with inbox.
            to: List of recipient email addresses.
            subject: Email subject.
            body: Email body (plain text; use attrs for html).
            from_: Sender email address (required by API).
            **attrs: Extra CreateAndSendInboxEmailInput fields (html, cc, bcc, etc.).
        """
        attrs = await self._resolve_repo_id(card_id, attrs)
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

    async def send_email_with_template(
        self,
        card_id: str,
        email_template_id: str,
        *,
        to: list[str] | None = None,
        from_: str | None = None,
        **attrs: Any,
    ) -> dict[str, Any]:
        """Send an email using a template with placeholders resolved for the card.

        Args:
            card_id: Numeric card ID (GraphQL ``ID`` as digits).
            email_template_id: Email template ID.
            to: Optional recipient override; defaults to template ``toEmail``.
            from_: Optional sender override; defaults to template ``fromEmail``.
            **attrs: Extra CreateAndSendInboxEmailInput fields (cc, bcc, repoId, etc.).
        """
        card_id_str = str(card_id).strip()
        if not card_id_str.isdigit():
            raise ValueError(f"card_id must be a numeric card ID, got {card_id!r}.")
        card_data = await self._card_service.get_card(card_id_str)
        card_obj = card_data.get("card") or {}
        card_uuid = card_obj.get("uuid")
        if not card_uuid:
            raise ValueError(
                f"Card {card_id_str} has no UUID; cannot resolve template placeholders."
            )
        parsed = await self.get_parsed_email_template(
            email_template_id,
            card_uuid=card_uuid,
        )
        pt = parsed.get("parsedEmailTemplate") or {}
        subject = pt.get("subject") or ""
        body = pt.get("body") or ""
        from_email = from_ or pt.get("fromEmail") or ""
        if not from_email:
            raise ValueError("Template has no fromEmail; provide from_ explicitly.")
        to_emails = to
        if to_emails is None:
            raw_to = pt.get("toEmail") or ""
            to_emails = [e.strip() for e in raw_to.split(",") if e.strip()]
        if not to_emails:
            raise ValueError(
                "Template has no toEmail and no to override; provide recipients."
            )
        extra = dict(attrs)
        pipe_obj = card_obj.get("pipe") or {}
        if isinstance(pipe_obj, dict) and pipe_obj.get("id"):
            extra["repoId"] = str(pipe_obj["id"])
        return await self.send_inbox_email(
            card_id_str,
            to_emails,
            subject,
            body,
            from_=from_email,
            **extra,
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
            "pipe_id": str(pipe_id),
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
        email_type: str | None = None,
    ) -> dict[str, Any]:
        """List emails (sent and received) for a card's inbox.

        Args:
            card_id: ID of the card with inbox.
            email_type: Optional filter: 'sent' | 'received'. When omitted, returns all.
        """
        raw = await self.execute_query(
            GET_CARD_INBOX_EMAILS_QUERY,
            {"card_id": str(card_id)},
        )
        card_data = raw.get("card") or {}
        emails = card_data.get("inbox_emails") or []

        if email_type is not None and email_type.strip():
            filter_type = email_type.strip().lower()
            emails = [e for e in emails if (e.get("type") or "").lower() == filter_type]
            card_data = dict(card_data, inbox_emails=emails)

        return {"card": card_data}
