"""AI knowledge bases (pipe-scoped): list, plain text/document/data lookup CRUD, and access probe."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from pipefy_sdk import KnowledgeBaseDocumentUploadError, PipefyClient

from pipefy_cli.commands._common import (
    confirm_destructive,
    parse_json_value,
    run_cli_command,
)

kb_app = typer.Typer(
    help=(
        "AI knowledge bases (pipe-scoped: list, plain text/document/data "
        "lookup CRUD, access probe)."
    ),
    no_args_is_help=True,
)
plain_text_app = typer.Typer(help="Knowledge base plain texts.", no_args_is_help=True)
kb_app.add_typer(plain_text_app, name="plain-text")
document_app = typer.Typer(
    help="Knowledge base documents (one-shot PDF upload).", no_args_is_help=True
)
kb_app.add_typer(document_app, name="document")
data_lookup_app = typer.Typer(
    help="Knowledge base data lookups (search cards in a source pipe).",
    no_args_is_help=True,
)
kb_app.add_typer(data_lookup_app, name="data-lookup")

_PIPE_UUID_HELP = "Pipe UUID (not the numeric ID; `pipefy pipe get` shows the uuid)."


def _kb_not_found(kind: str, resource_id: str) -> dict[str, object]:
    """Failure payload for a per-id get whose id resolved to nothing.

    Shared by every pipe-scoped knowledge base kind (plain text, document,
    data lookup) so the not-found envelope and discovery hint stay identical.
    """
    return {
        "success": False,
        "error": (
            f"{kind} not found: {resource_id}. "
            "Use `pipefy kb list` to list knowledge base IDs for the pipe."
        ),
    }


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
            return _kb_not_found("Knowledge base plain text", plain_text_id)
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

    ``content`` is the stored document URL, not the extracted text. Exits 1
    with ``success: false`` when the API resolves no document for the id
    (mirrors the MCP tool's not-found handling).
    """

    async def factory(client: PipefyClient):
        document = await client.get_ai_knowledge_base_document(document_id, pipe_uuid)
        if not document:
            return _kb_not_found("Knowledge base document", document_id)
        return {"success": True, "knowledge_base_document": document}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


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


_SOURCE_REPO_HELP = "Numeric ID of the source pipe to look up data from."
_OUTPUT_FIELDS_HELP = (
    "JSON array of field IDs whose values matching records return (1-30)."
)
_CONDITIONS_HELP = (
    "JSON array of condition objects. Each needs field + operator, and either "
    'a string value (static) or "usingFillWithAi": true with '
    "inputName/inputType/inputDescription (AI-filled)."
)
_SEARCH_QUERY_HELP = (
    "Backend-defined search mode marker; leave unset unless you know the "
    "backend value you need."
)


def _parse_data_lookup_options(
    output_fields: str, conditions: str
) -> tuple[list[str], list[dict[str, Any]]]:
    """Parse the JSON-array options shared by data lookup create/update."""
    parsed_fields = parse_json_value(output_fields, "--output-fields")
    if not isinstance(parsed_fields, list) or not all(
        isinstance(f, str) for f in parsed_fields
    ):
        raise typer.BadParameter("--output-fields must be a JSON array of strings")
    parsed_conditions = parse_json_value(conditions, "--conditions")
    if not isinstance(parsed_conditions, list) or not all(
        isinstance(c, dict) for c in parsed_conditions
    ):
        raise typer.BadParameter("--conditions must be a JSON array of objects")
    return parsed_fields, parsed_conditions


@data_lookup_app.command("get")
def kb_data_lookup_get(
    ctx: typer.Context,
    data_lookup_id: str = typer.Option(
        ..., "--id", help="Knowledge base data lookup ID (from `pipefy kb list`)."
    ),
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Fetch one knowledge base data lookup (``get_ai_knowledge_base_data_lookup``).

    The payload never includes ``conditions`` (the API does not expose them on
    reads); keep the lookup definition client-side. Exits 1 with ``success:
    false`` when the API resolves no data lookup for the id (mirrors the MCP
    tool's not-found handling).
    """

    async def factory(client: PipefyClient):
        data_lookup = await client.get_ai_knowledge_base_data_lookup(
            data_lookup_id, pipe_uuid
        )
        if not data_lookup:
            return _kb_not_found("Knowledge base data lookup", data_lookup_id)
        return {"success": True, "knowledge_base_data_lookup": data_lookup}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@data_lookup_app.command("create")
def kb_data_lookup_create(
    ctx: typer.Context,
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    name: str = typer.Option(..., "--name", help="Display name (required)."),
    description: str = typer.Option(
        ..., "--description", help="Description (required, 1-900 characters)."
    ),
    source_repo_id: str = typer.Option(..., "--source-repo-id", help=_SOURCE_REPO_HELP),
    output_fields: str = typer.Option(..., "--output-fields", help=_OUTPUT_FIELDS_HELP),
    conditions: str = typer.Option(..., "--conditions", help=_CONDITIONS_HELP),
    search_query: str | None = typer.Option(
        None, "--search-query", help=_SEARCH_QUERY_HELP
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Create a knowledge base data lookup (``create_ai_knowledge_base_data_lookup``).

    Gated on the read-access probe. The definition is validated client-side:
    ``--source-repo-id`` must be numeric, ``--output-fields`` takes 1-30 field
    IDs, and every condition is typed (static conditions need a string
    ``value``; AI-filled ones need the input trio). Reads never return
    conditions, so keep the definition you send as the source of truth.
    """
    fields, condition_list = _parse_data_lookup_options(output_fields, conditions)

    async def factory(client: PipefyClient):
        gate = await _probe_gate(client, pipe_uuid)
        if gate is not None:
            return gate
        data_lookup = await client.create_ai_knowledge_base_data_lookup(
            pipe_uuid,
            name=name,
            description=description,
            source_repo_id=source_repo_id,
            output_fields=fields,
            conditions=condition_list,
            search_query=search_query,
        )
        return {"success": True, "knowledge_base_data_lookup": data_lookup}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@data_lookup_app.command("update")
def kb_data_lookup_update(
    ctx: typer.Context,
    data_lookup_id: str = typer.Option(
        ..., "--id", help="Knowledge base data lookup ID to update."
    ),
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    source_repo_id: str = typer.Option(..., "--source-repo-id", help=_SOURCE_REPO_HELP),
    output_fields: str = typer.Option(..., "--output-fields", help=_OUTPUT_FIELDS_HELP),
    conditions: str = typer.Option(
        ...,
        "--conditions",
        help=_CONDITIONS_HELP + " Pass the complete set, not a delta.",
    ),
    search_query: str | None = typer.Option(
        None, "--search-query", help=_SEARCH_QUERY_HELP + " Omitted means cleared."
    ),
    name: str | None = typer.Option(None, "--name", help="New name (non-blank)."),
    description: str | None = typer.Option(
        None, "--description", help="New description (1-900 characters)."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Update a knowledge base data lookup by replacing its full definition (``update_ai_knowledge_base_data_lookup``).

    Every update rewrites the stored definition with exactly what this call
    carries: ``--source-repo-id``, ``--output-fields``, and ``--conditions``
    are required every time, and omitting ``--search-query`` clears it. Only
    ``--name``/``--description`` are partial. Gated on the read-access probe.
    """
    fields, condition_list = _parse_data_lookup_options(output_fields, conditions)

    async def factory(client: PipefyClient):
        gate = await _probe_gate(client, pipe_uuid)
        if gate is not None:
            return gate
        data_lookup = await client.update_ai_knowledge_base_data_lookup(
            data_lookup_id,
            pipe_uuid,
            source_repo_id=source_repo_id,
            output_fields=fields,
            conditions=condition_list,
            search_query=search_query,
            name=name,
            description=description,
        )
        return {"success": True, "knowledge_base_data_lookup": data_lookup}

    run_cli_command(ctx, json_out, factory, exit_1_on_unsuccessful=True)


@data_lookup_app.command("delete")
def kb_data_lookup_delete(
    ctx: typer.Context,
    data_lookup_id: str = typer.Option(
        ..., "--id", help="Knowledge base data lookup ID to delete."
    ),
    pipe_uuid: str = typer.Option(..., "--pipe-uuid", help=_PIPE_UUID_HELP),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt."
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print machine-readable JSON to stdout."
    ),
) -> None:
    """Delete a knowledge base data lookup permanently (``delete_ai_knowledge_base_data_lookup``)."""
    confirm_destructive(
        yes=yes,
        description=f"knowledge base data lookup {data_lookup_id}",
    )

    async def factory(client: PipefyClient):
        return await client.delete_ai_knowledge_base_data_lookup(
            data_lookup_id, pipe_uuid
        )

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
