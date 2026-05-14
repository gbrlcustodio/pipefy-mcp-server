"""Card inbox emails and org email templates."""

from __future__ import annotations

import typer
from pipefy_sdk import PipefyClient

from pipefy_cli.commands._common import parse_json_object, run_cli_command

email_app = typer.Typer(help="Inbox emails and email templates.", no_args_is_help=True)
inbox_app = typer.Typer(help="Card inbox (sent/received).", no_args_is_help=True)
template_app = typer.Typer(
    help="Email templates bound to a pipe or table (repo).", no_args_is_help=True
)


@inbox_app.command("list")
def email_inbox_list(
    ctx: typer.Context,
    card_id: str = typer.Option(..., "--card", help="Card id with inbox enabled."),
    email_type: str | None = typer.Option(
        None,
        "--type",
        help="Optional filter: sent or received.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """List inbox emails for a card (``get_card_inbox_emails``)."""

    async def factory(client: PipefyClient):
        return await client.get_card_inbox_emails(card_id, email_type=email_type)

    run_cli_command(ctx, json_out, factory)


@inbox_app.command("send")
def email_inbox_send(
    ctx: typer.Context,
    card_id: str = typer.Option(..., "--card", help="Card id."),
    to: str = typer.Option(
        ...,
        "--to",
        help="Recipient emails (comma-separated).",
    ),
    subject: str = typer.Option(..., "--subject", "-s", help="Email subject."),
    body: str = typer.Option(..., "--body", "-b", help="Plain-text body."),
    from_email: str = typer.Option(
        ...,
        "--from-email",
        help="Sender email address (required by API).",
    ),
    extra: str | None = typer.Option(
        None,
        "--extra",
        help="Optional JSON object: extra CreateAndSendInboxEmailInput fields.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Send an inbox email from a card (``send_inbox_email``)."""
    recipients = [e.strip() for e in to.split(",") if e.strip()]
    if not recipients:
        raise typer.BadParameter("--to must list at least one email.")
    extra_obj = parse_json_object(extra, "--extra") or {}

    async def factory(client: PipefyClient):
        return await client.send_inbox_email(
            card_id,
            recipients,
            subject,
            body,
            from_=from_email,
            **extra_obj,
        )

    run_cli_command(ctx, json_out, factory)


@template_app.command("list")
def email_template_list(
    ctx: typer.Context,
    repo_id: str = typer.Option(
        ...,
        "--repo",
        help="Pipe or table id whose templates to list.",
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        help="Optional substring filter on template name.",
    ),
    first: int = typer.Option(50, "--first", help="Max templates to return."),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """List email templates for a repo (``get_email_templates``)."""

    async def factory(client: PipefyClient):
        return await client.get_email_templates(
            repo_id, filter_by_name=name, first=first
        )

    run_cli_command(ctx, json_out, factory)


@template_app.command("send")
def email_template_send(
    ctx: typer.Context,
    card_id: str = typer.Option(..., "--card", help="Card id (inbox sender context)."),
    template_id: str = typer.Option(
        ...,
        "--template",
        help="Email template id.",
    ),
    to: str | None = typer.Option(
        None,
        "--to",
        help="Optional comma-separated override recipients.",
    ),
    from_email: str | None = typer.Option(
        None,
        "--from-email",
        help="Optional sender override.",
    ),
    extra: str | None = typer.Option(
        None,
        "--extra",
        help="Optional JSON object: extra send fields (cc, bcc, repoId, etc.).",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Send using an email template (``send_email_with_template``)."""
    to_list: list[str] | None = None
    if to is not None and to.strip():
        to_list = [e.strip() for e in to.split(",") if e.strip()]
    extra_obj = parse_json_object(extra, "--extra") or {}

    async def factory(client: PipefyClient):
        return await client.send_email_with_template(
            card_id,
            template_id,
            to=to_list,
            from_=from_email,
            **extra_obj,
        )

    run_cli_command(ctx, json_out, factory)


email_app.add_typer(inbox_app, name="inbox")
email_app.add_typer(template_app, name="template")
