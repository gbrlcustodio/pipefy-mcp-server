"""Upload attachments to card or table record fields."""

from __future__ import annotations

from pathlib import Path

import typer
from pipefy_sdk import (
    Attachment,
    AttachmentUploadError,
    CardTarget,
    PipefyClient,
    TableRecordTarget,
)

from pipefy_cli.commands._common import run_cli_command

attachment_app = typer.Typer(
    help="Attachment uploads (presigned URL + field update).", no_args_is_help=True
)


@attachment_app.command("upload")
def attachment_upload(
    ctx: typer.Context,
    file: Path = typer.Option(
        ...,
        "--file",
        "-f",
        help="Local file path to upload. Supports ~ expansion.",
    ),
    card: str | None = typer.Option(
        None,
        "--card",
        help="Target card id (mutually exclusive with --record).",
    ),
    record: str | None = typer.Option(
        None,
        "--record",
        help="Target table record id (mutually exclusive with --card).",
    ),
    organization: str = typer.Option(
        ...,
        "--organization",
        "--org",
        help="Organization id (required for presigned URL).",
    ),
    field: str = typer.Option(
        ...,
        "--field",
        help="Attachment field slug on the card or table record.",
    ),
    content_type: str | None = typer.Option(
        None,
        "--content-type",
        help="Optional MIME type (defaults from file name).",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print machine-readable JSON to stdout.",
    ),
) -> None:
    """Upload a local file to a card or table record attachment field.

    Uses the same SDK flow as MCP ``upload_attachment_to_card`` /
    ``upload_attachment_to_table_record``: presigned URL, S3 PUT, then field update.
    """
    if (card is None) == (record is None):
        raise typer.BadParameter("Provide exactly one of --card or --record.")

    org_str = str(organization).strip()
    field_str = str(field).strip()
    if not org_str or not field_str:
        raise typer.BadParameter("--organization and --field must be non-empty.")

    card_id = str(card).strip() if card is not None else None
    record_id = str(record).strip() if record is not None else None

    try:
        attachment = Attachment(path=file, content_type=content_type)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if card_id is not None:
        target = CardTarget(card_id=card_id, field_id=field_str)
    else:
        target = TableRecordTarget(table_record_id=record_id or "", field_id=field_str)

    async def factory(client: PipefyClient) -> dict[str, object]:
        try:
            result = await client.upload_attachment(
                attachment, organization_id=org_str, target=target
            )
        except AttachmentUploadError as exc:
            if exc.step == "file_read":
                message = str(exc.__cause__) if exc.__cause__ else str(exc)
                raise typer.BadParameter(message) from exc
            out: dict[str, object] = {
                "success": False,
                "step": exc.step,
                "message": str(exc),
            }
            if exc.body_snippet is not None:
                out["body_snippet"] = exc.body_snippet
            return out

        target_payload: dict[str, object]
        if isinstance(target, CardTarget):
            target_payload = {"card_id": target.card_id}
        else:
            target_payload = {"table_record_id": target.table_record_id}

        return {
            "success": True,
            "message": "Attachment uploaded.",
            "file_name": result["file_name"],
            "content_type": result["content_type"],
            "file_size": result["file_size"],
            "field_id": result["field_id"],
            "download_url": result["download_url"],
            **target_payload,
        }

    run_cli_command(ctx, json_out, factory)
