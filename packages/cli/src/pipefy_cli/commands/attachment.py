"""Upload attachments to card or table record fields."""

from __future__ import annotations

from pathlib import Path

import typer
from pipefy_sdk import PipefyClient, infer_content_type

from pipefy_cli.commands._common import run_cli_command

attachment_app = typer.Typer(
    help="Attachment uploads (presigned URL + field update).", no_args_is_help=True
)


def _read_local_file_bytes(path: Path) -> bytes:
    """Read file content for upload (S3 PUT requires the full body).

    Args:
        path: Readable file path.

    Returns:
        Raw bytes of the file.

    Raises:
        typer.BadParameter: When the path is not a readable file.
    """
    if not path.is_file():
        raise typer.BadParameter(f"Not a file: {path}")
    return path.read_bytes()


@attachment_app.command("upload")
def attachment_upload(
    ctx: typer.Context,
    file: Path = typer.Option(
        ...,
        "--file",
        "-f",
        help="Local file path to upload.",
        exists=True,
        readable=True,
        dir_okay=False,
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
    file_name = file.name
    file_bytes = _read_local_file_bytes(file)
    effective_type = content_type or infer_content_type(file_name)
    org_str = str(organization).strip()
    field_str = str(field).strip()
    if not org_str or not field_str:
        raise typer.BadParameter("--organization and --field must be non-empty.")

    card_id = str(card).strip() if card is not None else None
    record_id = str(record).strip() if record is not None else None

    async def factory(client: PipefyClient) -> dict[str, object]:
        presigned = await client.create_presigned_url(
            org_str,
            file_name,
            effective_type,
            len(file_bytes),
        )
        upload_url = presigned.get("url")
        download_url = presigned.get("download_url")
        if not isinstance(upload_url, str) or not upload_url.strip():
            return {
                "success": False,
                "step": "presigned_url",
                "message": "Pipefy did not return a presigned upload URL.",
            }
        put_result = await client.upload_file_to_s3(
            upload_url.strip(),
            file_bytes,
            effective_type,
        )
        status = put_result.get("status_code", 0)
        if not isinstance(status, int) or status >= 400:
            snippet = put_result.get("body_snippet", "")
            return {
                "success": False,
                "step": "s3_upload",
                "message": f"S3 upload failed with HTTP {status}.",
                "body_snippet": snippet,
            }
        try:
            storage_path = client.extract_storage_path(upload_url)
        except ValueError as exc:
            return {"success": False, "step": "s3_upload", "message": str(exc)}

        try:
            if card_id is not None:
                await client.update_card_field(card_id, field_str, [storage_path])
                target: dict[str, object] = {"card_id": card_id}
            else:
                await client.set_table_record_field_value(
                    record_id or "", field_str, [storage_path]
                )
                target = {"table_record_id": record_id}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "step": "field_update", "message": str(exc)}

        return {
            "success": True,
            "message": "Attachment uploaded.",
            "file_name": file_name,
            "content_type": effective_type,
            "file_size": len(file_bytes),
            "field_id": field_str,
            "download_url": download_url if isinstance(download_url, str) else None,
            **target,
        }

    run_cli_command(ctx, json_out, factory)
