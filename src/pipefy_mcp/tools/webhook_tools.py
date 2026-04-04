"""MCP tools for sending inbox emails and managing webhooks."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.validation_helpers import (
    mutation_error_if_not_optional_dict,
    valid_repo_id,
)
from pipefy_mcp.tools.webhook_tool_helpers import (
    build_webhook_error_payload,
    build_webhook_success_payload,
    handle_webhook_tool_graphql_error,
)


class WebhookTools:
    """MCP tools for sending emails from card inboxes and managing webhooks."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_email_templates(
            repo_id: str,
            filter_by_name: str | None = None,
            first: int = 50,
            debug: bool = False,
        ) -> dict[str, Any]:
            """List email templates for a pipe or table.

            Use before send_email_with_template to discover template IDs.
            Templates are created in the Pipefy UI; this query lists existing ones.

            Args:
                repo_id: Pipe or table ID.
                filter_by_name: Optional case-insensitive partial match on template name.
                first: Max templates to return (default 50).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_repo_id(repo_id):
                return build_webhook_error_payload(
                    message="Invalid 'repo_id': provide a non-empty string or positive integer.",
                )
            try:
                raw = await client.get_email_templates(
                    str(repo_id).strip(),
                    filter_by_name=filter_by_name.strip() if filter_by_name else None,
                    first=first,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_webhook_tool_graphql_error(
                    exc, "List email templates failed.", debug=debug
                )
            return build_webhook_success_payload(
                message="Email templates listed.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_card_inbox_emails(
            card_id: str,
            email_type: str | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """List emails (sent and received) for a card's inbox.

            When someone replies to an email sent from the card, the reply appears
            with type 'received'. Use email_type='received' to get only replies.

            Args:
                card_id: ID of the card with inbox.
                email_type: Optional filter: 'sent' or 'received' to get only that type.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_repo_id(card_id):
                return build_webhook_error_payload(
                    message="Invalid 'card_id': provide a non-empty string or positive integer.",
                )
            trimmed_email_type = email_type.strip() if email_type else None
            if trimmed_email_type is not None and trimmed_email_type.lower() not in (
                "sent",
                "received",
            ):
                return build_webhook_error_payload(
                    message="Invalid 'email_type': must be 'sent' or 'received' when provided.",
                )
            try:
                raw = await client.get_card_inbox_emails(
                    card_id.strip(),
                    email_type=trimmed_email_type,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_webhook_tool_graphql_error(
                    exc, "Get card inbox emails failed.", debug=debug
                )
            return build_webhook_success_payload(
                message="Card inbox emails listed.",
                data=raw,
            )

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
            except Exception as exc:  # noqa: BLE001
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
        async def send_email_with_template(
            card_id: str,
            email_template_id: str,
            to: list[str] | None = None,
            from_: str | None = None,
            extra_input: dict[str, Any] | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Send an email from a card's inbox using an existing email template.

            Fetches the template with placeholders (e.g. {{card.title}}) resolved
            for the card, then sends via createAndSendInboxEmail. Template must
            exist (created in Pipefy UI). Use get_email_templates to find template IDs.

            Args:
                card_id: ID of the card with inbox.
                email_template_id: ID of the email template.
                to: Optional override for recipients; if omitted, uses template's toEmail.
                from_: Optional override for sender; if omitted, uses template's fromEmail.
                extra_input: Optional extra CreateAndSendInboxEmailInput fields (cc, bcc).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_repo_id(card_id):
                return build_webhook_error_payload(
                    message="Invalid 'card_id': provide a non-empty string or positive integer.",
                )
            if not isinstance(email_template_id, str) or not email_template_id.strip():
                return build_webhook_error_payload(
                    message="Invalid 'email_template_id': provide a non-empty string.",
                )
            if to is not None and (
                not isinstance(to, list)
                or not all(isinstance(e, str) and e.strip() for e in to)
            ):
                return build_webhook_error_payload(
                    message="Invalid 'to': when provided, must be a non-empty list of email strings.",
                )
            bad = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad is not None:
                return bad
            try:
                raw = await client.send_email_with_template(
                    card_id.strip(),
                    email_template_id.strip(),
                    to=to,
                    from_=from_,
                    **(extra_input or {}),
                )
            except ValueError as exc:
                return build_webhook_error_payload(message=str(exc))
            except Exception as exc:  # noqa: BLE001
                return handle_webhook_tool_graphql_error(
                    exc, "Send email with template failed.", debug=debug
                )
            return build_webhook_success_payload(
                message="Email sent with template.",
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
            except ValueError as exc:
                return build_webhook_error_payload(message=str(exc))
            except Exception as exc:  # noqa: BLE001
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
            ctx: Context[ServerSession, None],
            webhook_id: str,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a webhook permanently.

            Two-step operation: call without ``confirm`` to preview, then with
            ``confirm=True`` after user approval. When the MCP client supports
            elicitation, the user is prompted interactively instead.

            Args:
                ctx: MCP context for debug logging.
                webhook_id: ID of the webhook to delete.
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not isinstance(webhook_id, str) or not webhook_id.strip():
                return build_webhook_error_payload(
                    message="Invalid 'webhook_id': provide a non-empty string.",
                )

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"webhook (ID: {webhook_id})",
            )
            if guard is not None:
                return guard

            try:
                raw = await client.delete_webhook(webhook_id.strip())
            except Exception as exc:  # noqa: BLE001
                return handle_webhook_tool_graphql_error(
                    exc, "Delete webhook failed.", debug=debug
                )
            return build_webhook_success_payload(
                message="Webhook deleted.",
                data=raw,
            )
