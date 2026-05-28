"""Upload attachments to card or table record fields."""

from __future__ import annotations

from pathlib import Path

import typer
from pipefy_sdk import PipefyClient
from pipefy_sdk.attachment_upload import AttachmentUploadError

from pipefy_cli.commands._common import run_cli_command

attachment_app = typer.Typer(
    help="Attachment uploads (presigned URL + field update).", no_args_is_help=True
)


def _read_local_file_bytes(path: Path) -> tuple[Path, bytes]:
    """Read file content for upload (S3 PUT requires the full body).

    ``~`` is expanded so programmatic invocations
    (``subprocess.run([..., "--file", "~/foo.pdf"])``) work the same as
    shell-expanded paths and mirror the MCP tool's ``file_path`` behavior.

    Args:
        path: File path to read.

    Returns:
        ``(expanded_path, file_bytes)``. The expanded path is returned so
        callers can derive ``file_name`` from the same value that was read.

    Raises:
        typer.BadParameter: When the (expanded) path is not a readable file.
    """
    expanded = path.expanduser()
    if not expanded.is_file():
        raise typer.BadParameter(f"Not a file: {expanded}")
    try:
        data = expanded.read_bytes()
    except PermissionError as exc:
        raise typer.BadParameter(f"Cannot read {expanded}: {exc.strerror}") from exc
    except OSError as exc:
        raise typer.BadParameter(f"Cannot read {expanded}: {exc}") from exc
    return expanded, data


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
    expanded_file, file_bytes = _read_local_file_bytes(file)
    file_name = expanded_file.name
    org_str = str(organization).strip()
    field_str = str(field).strip()
    if not org_str or not field_str:
        raise typer.BadParameter("--organization and --field must be non-empty.")

    card_id = str(card).strip() if card is not None else None
    record_id = str(record).strip() if record is not None else None

    async def factory(client: PipefyClient) -> dict[str, object]:
        try:
            if card_id is not None:
                result = await client.upload_attachment_to_card_field(
                    organization_id=org_str,
                    card_id=card_id,
                    field_id=field_str,
                    file_name=file_name,
                    file_bytes=file_bytes,
                    content_type=content_type,
                )
                target: dict[str, object] = {"card_id": card_id}
            else:
                result = await client.upload_attachment_to_table_record_field(
                    organization_id=org_str,
                    table_record_id=record_id or "",
                    field_id=field_str,
                    file_name=file_name,
                    file_bytes=file_bytes,
                    content_type=content_type,
                )
                target = {"table_record_id": record_id}
        except AttachmentUploadError as exc:
            out: dict[str, object] = {
                "success": False,
                "step": exc.step,
                "message": str(exc),
            }
            if exc.body_snippet is not None:
                out["body_snippet"] = exc.body_snippet
            return out

        return {
            "success": True,
            "message": "Attachment uploaded.",
            "file_name": result["file_name"],
            "content_type": result["content_type"],
            "file_size": result["file_size"],
            "field_id": result["field_id"],
            "download_url": result["download_url"],
            **target,
        }

    run_cli_command(ctx, json_out, factory)
