"""AI knowledge bases (pipe-scoped): list, plain text/document CRUD, and access probe."""

from __future__ import annotations

from pathlib import Path

import typer
from pipefy_sdk import KnowledgeBaseDocumentUploadError, PipefyClient

from pipefy_cli.commands._common import (
    confirm_destructive,
    run_cli_command,
)

kb_app = typer.Typer(
    help="AI knowledge bases (pipe-scoped: list, plain text/document CRUD, access probe).",
    no_args_is_help=True,
)
plain_text_app = typer.Typer(help="Knowledge base plain texts.", no_args_is_help=True)
kb_app.add_typer(plain_text_app, name="plain-text")
document_app = typer.Typer(
    help="Knowledge base documents (one-shot PDF upload).", no_args_is_help=True
)
kb_app.add_typer(document_app, name="document")

_PIPE_UUID_HELP = "Pipe UUID (not the numeric ID; `pipefy pipe get` shows the uuid)."


@kb_app.command("list")
def kb_list(
    ctx: typer.Context,
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """List a pipe's knowledge base items (``get_ai_knowledge_bases``).

    Each item carries ``id`` (used in ``dataSourceIds``), ``type``, ``name``,
    ``description``, and ``updatedAt``. No pagination; the full list is returned.
    """

    async def factory(client: PipefyClient):
        items = await client.get_ai_knowledge_bases(pipe_uuid)
        return {"success": True, "knowledge_bases": items}

    run_cli_command(ctx, json_out, factory)


@kb_app.command("validate-access")
def kb_validate_access(
    ctx: typer.Context,
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Probe knowledge-base read access (``validate_knowledge_base_access``).

    A green probe proves read access only (``read_ai_agents``), never write
    entitlement. Exits 1 when the probe classifies a failure, after rendering
    the structured problem.
    """

    async def factory(client: PipefyClient):
        probe = await client.validate_knowledge_base_access(pipe_uuid)
        return {"success": bool(probe.get("ok")), **probe}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@plain_text_app.command("get")
def kb_plain_text_get(
    ctx: typer.Context,
    plain_text_id: str = typer.Option(
        ..., "--id", help="Knowledge base plain text ID (from `pipefy kb list`)."
    ),
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Fetch one knowledge base plain text with its content (``get_ai_knowledge_base_plain_text``).

    Exits 1 with ``success: false`` when the API resolves no plain text for the
    id (mirrors the MCP tool's not-found handling).
    """

    async def factory(client: PipefyClient):
        plain_text = await client.get_ai_knowledge_base_plain_text(
            plain_text_id, pipe_uuid
        )
        if not plain_text:
            return {
                "success": False,
                "error": (
                    f"Knowledge base plain text not found: {plain_text_id}. "
                    "Use `pipefy kb list` to list knowledge base IDs for the pipe."
                ),
            }
        return {"success": True, "knowledge_base_plain_text": plain_text}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@plain_text_app.command("create")
def kb_plain_text_create(
    ctx: typer.Context,
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    name: str = typer.Option(..., "--name", help="Display name (required)."),
    content: str = typer.Option(
        ..., "--content", help="Plain text content (required, 1-3500 characters)."
    ),
    description: str = typer.Option(
        ..., "--description", help="Description (required, 1-900 characters)."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Create a knowledge base plain text (``create_ai_knowledge_base_plain_text``).

    Gated on the read-access probe: fails with the classified problem if the
    credential cannot read the pipe's knowledge bases. Client-side limits
    (content 1-3500, description 1-900) fail fast before the mutation is sent.
    """

    async def factory(client: PipefyClient):
        gate = await _probe_gate(client, pipe_uuid)
        if gate is not None:
            return gate
        plain_text = await client.create_ai_knowledge_base_plain_text(
            pipe_uuid, name=name, content=content, description=description
        )
        return {"success": True, "knowledge_base_plain_text": plain_text}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@plain_text_app.command("update")
def kb_plain_text_update(
    ctx: typer.Context,
    plain_text_id: str = typer.Option(
        ..., "--id", help="Knowledge base plain text ID to update."
    ),
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    name: str | None = typer.Option(None, "--name", help="New name (non-blank)."),
    content: str | None = typer.Option(
        None, "--content", help="New content (1-3500 characters)."
    ),
    description: str | None = typer.Option(
        None, "--description", help="New description (1-900 characters)."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Update a knowledge base plain text (``update_ai_knowledge_base_plain_text``).

    Partial: only the fields you pass change. Provide at least one of --name,
    --content, or --description. Gated on the read-access probe.
    """

    async def factory(client: PipefyClient):
        gate = await _probe_gate(client, pipe_uuid)
        if gate is not None:
            return gate
        plain_text = await client.update_ai_knowledge_base_plain_text(
            plain_text_id,
            pipe_uuid,
            name=name,
            content=content,
            description=description,
        )
        return {"success": True, "knowledge_base_plain_text": plain_text}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@plain_text_app.command("delete")
def kb_plain_text_delete(
    ctx: typer.Context,
    plain_text_id: str = typer.Option(
        ..., "--id", help="Knowledge base plain text ID to delete."
    ),
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Delete a knowledge base plain text permanently (``delete_ai_knowledge_base_plain_text``)."""
    confirm_destructive(
        yes=yes,
        description=f"knowledge base plain text {plain_text_id}",
    )

    async def factory(client: PipefyClient):
        return await client.delete_ai_knowledge_base_plain_text(
            plain_text_id, pipe_uuid
        )

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@document_app.command("get")
def kb_document_get(
    ctx: typer.Context,
    document_id: str = typer.Option(
        ..., "--id", help="Knowledge base document ID (from `pipefy kb list`)."
    ),
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Fetch one knowledge base document (``get_ai_knowledge_base_document``).

    ``content`` is the stored document URL, not the extracted text.
    """

    async def factory(client: PipefyClient):
        document = await client.get_ai_knowledge_base_document(document_id, pipe_uuid)
        return {"success": True, "knowledge_base_document": document}

    run_cli_command(ctx, json_out, factory)


@document_app.command("create")
def kb_document_create(
    ctx: typer.Context,
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    file: Path = typer.Option(
        ...,
        "--file",
        "-f",
        help="Local .pdf file to upload (<=20 MiB). Supports ~ expansion.",
    ),
    name: str = typer.Option(..., "--name", help="Display name (required)."),
    description: str = typer.Option(
        ..., "--description", help="Description (required, 1-900 characters)."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Create a knowledge base document from a local PDF (``create_ai_knowledge_base_document``).

    One-shot: presigned URL, S3 PUT, then the create mutation. Gated on the
    read-access probe. Client-side checks fail fast (``.pdf`` extension, 20 MiB
    cap, description 1-900). Indexing is asynchronous, so the document may not be
    searchable by agents immediately.
    """

    async def factory(client: PipefyClient):
        gate = await _probe_gate(client, pipe_uuid)
        if gate is not None:
            return gate
        try:
            document = await client.create_ai_knowledge_base_document(
                pipe_uuid, name=name, description=description, file_path=file
            )
        except KnowledgeBaseDocumentUploadError as exc:
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
        return {"success": True, "knowledge_base_document": document}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@document_app.command("update")
def kb_document_update(
    ctx: typer.Context,
    document_id: str = typer.Option(
        ..., "--id", help="Knowledge base document ID to update."
    ),
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    name: str | None = typer.Option(None, "--name", help="New name (non-blank)."),
    description: str | None = typer.Option(
        None, "--description", help="New description (1-900 characters)."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Update a knowledge base document's metadata (``update_ai_knowledge_base_document``).

    Metadata only (name/description); the PDF cannot be replaced. Provide at
    least one of --name or --description. Gated on the read-access probe.
    """

    async def factory(client: PipefyClient):
        gate = await _probe_gate(client, pipe_uuid)
        if gate is not None:
            return gate
        document = await client.update_ai_knowledge_base_document(
            document_id, pipe_uuid, name=name, description=description
        )
        return {"success": True, "knowledge_base_document": document}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@document_app.command("delete")
def kb_document_delete(
    ctx: typer.Context,
    document_id: str = typer.Option(
        ..., "--id", help="Knowledge base document ID to delete."
    ),
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Delete a knowledge base document permanently (``delete_ai_knowledge_base_document``)."""
    confirm_destructive(
        yes=yes,
        description=f"knowledge base document {document_id}",
    )

    async def factory(client: PipefyClient):
        return await client.delete_ai_knowledge_base_document(document_id, pipe_uuid)

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


async def _probe_gate(client: PipefyClient, pipe_uuid: str) -> dict | None:
    """Gate a write on the read-access probe; return a failure dict or None.

    A failed probe returns the classified problem so the write never runs and
    the CLI exits 1 (via ``exit_1_on_unsuccessful``) with the problem rendered.
    """
    probe = await client.validate_knowledge_base_access(pipe_uuid)
    if probe.get("ok"):
        return None
    return {"success": False, **probe}
