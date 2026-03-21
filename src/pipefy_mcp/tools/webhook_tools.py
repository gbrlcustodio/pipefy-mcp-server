"""MCP tools for sending inbox emails and managing webhooks."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.validation_helpers import (
    mutation_error_if_not_optional_dict,
    valid_repo_id,
)
from pipefy_mcp.tools.webhook_tool_helpers import (
    build_webhook_error_payload,
    build_webhook_success_payload,
    handle_webhook_tool_graphql_error,
)


def _require_https(url: str) -> bool:
    """Return True if url is HTTPS."""
    return url.strip().lower().startswith("https://")


class WebhookTools:
    """MCP tools for sending emails from card inboxes and managing webhooks."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def send_inbox_email(
            card_id: str,
            to: list[str],
            subject: str,
            body: str,
            from_: str,
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Send an email from a card's inbox.

            Requires the card to have an email inbox enabled.

            Args:
                card_id: ID of the card.
                to: List of recipient email addresses.
                subject: Email subject.
                body: Email body (plain text or HTML).
                from_: Sender email address (required by API).
                extra_input: Optional extra CreateAndSendInboxEmailInput fields (html, cc, bcc).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_repo_id(card_id):
                return build_webhook_error_payload(
                    message="Invalid 'card_id': provide a non-empty string or positive integer.",
                )
            if not isinstance(to, list) or not to:
                return build_webhook_error_payload(
                    message="Invalid 'to': provide a non-empty list of email addresses.",
                )
            if not all(isinstance(e, str) and e.strip() for e in to):
                return build_webhook_error_payload(
                    message="Invalid 'to': each recipient must be a non-empty string.",
                )
            if not isinstance(subject, str) or not subject.strip():
                return build_webhook_error_payload(
                    message="Invalid 'subject': provide a non-empty string.",
                )
            if not isinstance(body, str):
                return build_webhook_error_payload(
                    message="Invalid 'body': provide a string.",
                )
            if not isinstance(from_, str) or not from_.strip():
                return build_webhook_error_payload(
                    message="Invalid 'from_': provide a non-empty sender email address.",
                )
            bad = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad is not None:
                return bad
            try:
                raw = await client.send_inbox_email(
                    card_id,
                    [e.strip() for e in to],
                    subject.strip(),
                    body,
                    from_=from_.strip(),
                    **(extra_input or {}),
                )
            except Exception as exc:
                return handle_webhook_tool_graphql_error(
                    exc, "Send inbox email failed.", debug=debug
                )
            return build_webhook_success_payload(
                message="Email sent.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_webhook(
            pipe_id: str,
            url: str,
            actions: list[str],
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Register a webhook for pipe events.

            `url` must be HTTPS. `actions` is a list of event names (e.g. ['card.move', 'card.create']).
            Use `introspect_type('WebhookActions')` to see valid actions.

            Args:
                pipe_id: ID of the pipe.
                url: HTTPS URL to receive events.
                actions: List of event action strings.
                extra_input: Optional extra CreateWebhookInput fields (name, filters, headers).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_repo_id(pipe_id):
                return build_webhook_error_payload(
                    message="Invalid 'pipe_id': provide a non-empty string or positive integer.",
                )
            if not isinstance(url, str) or not url.strip():
                return build_webhook_error_payload(
                    message="Invalid 'url': provide a non-empty string.",
                )
            if not _require_https(url):
                return build_webhook_error_payload(
                    message="Invalid 'url': must be HTTPS. HTTP URLs are not allowed.",
                )
            if not isinstance(actions, list) or not actions:
                return build_webhook_error_payload(
                    message="Invalid 'actions': provide a non-empty list of event action strings.",
                )
            if not all(isinstance(a, str) and a.strip() for a in actions):
                return build_webhook_error_payload(
                    message="Invalid 'actions': each action must be a non-empty string.",
                )
            bad = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad is not None:
                return bad
            try:
                raw = await client.create_webhook(
                    pipe_id,
                    url.strip(),
                    [a.strip() for a in actions],
                    **(extra_input or {}),
                )
            except Exception as exc:
                return handle_webhook_tool_graphql_error(
                    exc, "Create webhook failed.", debug=debug
                )
            return build_webhook_success_payload(
                message="Webhook created.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_webhook(
            webhook_id: str,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Permanently delete a webhook by ID.

            Always confirm with the user before calling — deletion cannot be undone.

            Args:
                webhook_id: ID of the webhook to delete.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not isinstance(webhook_id, str) or not webhook_id.strip():
                return build_webhook_error_payload(
                    message="Invalid 'webhook_id': provide a non-empty string.",
                )
            try:
                raw = await client.delete_webhook(webhook_id.strip())
            except Exception as exc:
                return handle_webhook_tool_graphql_error(
                    exc, "Delete webhook failed.", debug=debug
                )
            return build_webhook_success_payload(
                message="Webhook deleted.",
                data=raw,
            )
