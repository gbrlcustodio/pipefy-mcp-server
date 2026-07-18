"""Tests for ``pipefy kb`` knowledge base commands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_cli.main import app

PLAIN_TEXT_NODE = {
    "id": "kb-1",
    "type": "knowledge_base_plain_texts",
    "name": "Onboarding",
    "description": "How to onboard",
    "updatedAt": "2026-07-17T00:00:00Z",
}

PLAIN_TEXT_FULL = {
    "id": "kb-1",
    "name": "Onboarding",
    "description": "How to onboard",
    "content": "Step 1...",
    "updatedAt": "2026-07-17T00:00:00Z",
}

GREEN_PROBE = {"ok": True, "knowledge_base_count": 1, "note": "Read access confirmed."}
DENIED_PROBE = {
    "ok": False,
    "problem": {
        "kind": "permission_denied",
        "message": "Permission denied",
        "code": "PERMISSION_DENIED",
    },
}


def _env(monkeypatch) -> None:
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")


def _client_patch(mock_client):
    return patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    )


def test_kb_list_json(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_ai_knowledge_bases = AsyncMock(return_value=[PLAIN_TEXT_NODE])

    with _client_patch(mock_client):
        result = runner.invoke(
            app, ["kb", "list", "--pipe-uuid", "pipe-uuid-1", "--json"]
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    data = json.loads(result.stdout)
    assert data["success"] is True
    assert data["knowledge_bases"] == [PLAIN_TEXT_NODE]
    mock_client.get_ai_knowledge_bases.assert_awaited_once_with("pipe-uuid-1")


def test_kb_validate_access_green_exits_0(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=GREEN_PROBE)

    with _client_patch(mock_client):
        result = runner.invoke(
            app, ["kb", "validate-access", "--pipe-uuid", "pipe-uuid-1", "--json"]
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout)["success"] is True


def test_kb_validate_access_failure_exits_1(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=DENIED_PROBE)

    with _client_patch(mock_client):
        result = runner.invoke(
            app, ["kb", "validate-access", "--pipe-uuid", "pipe-uuid-1", "--json"]
        )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["success"] is False


def test_kb_plain_text_get_json(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_ai_knowledge_base_plain_text = AsyncMock(
        return_value=PLAIN_TEXT_FULL
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "plain-text",
                "get",
                "--id",
                "kb-1",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout)["knowledge_base_plain_text"] == PLAIN_TEXT_FULL
    mock_client.get_ai_knowledge_base_plain_text.assert_awaited_once_with(
        "kb-1", "pipe-uuid-1"
    )


def test_kb_plain_text_get_empty_result_exits_1(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    """Missing id resolves to `{}` from the SDK; the CLI must not report success."""
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_ai_knowledge_base_plain_text = AsyncMock(return_value={})

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "plain-text",
                "get",
                "--id",
                "kb-missing",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--json",
            ],
        )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["success"] is False
    assert "not found" in data["error"].lower()


def test_kb_plain_text_create_gated_on_probe(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=GREEN_PROBE)
    mock_client.create_ai_knowledge_base_plain_text = AsyncMock(
        return_value=PLAIN_TEXT_FULL
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "plain-text",
                "create",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--name",
                "Onboarding",
                "--content",
                "Step 1...",
                "--description",
                "How to onboard",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout)["success"] is True
    mock_client.create_ai_knowledge_base_plain_text.assert_awaited_once_with(
        "pipe-uuid-1",
        name="Onboarding",
        content="Step 1...",
        description="How to onboard",
    )


def test_kb_plain_text_create_denied_probe_blocks_write(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=DENIED_PROBE)
    mock_client.create_ai_knowledge_base_plain_text = AsyncMock()

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "plain-text",
                "create",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--name",
                "n",
                "--content",
                "c",
                "--description",
                "d",
                "--json",
            ],
        )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["success"] is False
    mock_client.create_ai_knowledge_base_plain_text.assert_not_awaited()


def test_kb_plain_text_update_partial(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=GREEN_PROBE)
    mock_client.update_ai_knowledge_base_plain_text = AsyncMock(
        return_value=PLAIN_TEXT_FULL
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "plain-text",
                "update",
                "--id",
                "kb-1",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--content",
                "New content",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.update_ai_knowledge_base_plain_text.assert_awaited_once_with(
        "kb-1", "pipe-uuid-1", name=None, content="New content", description=None
    )


def test_kb_plain_text_delete_with_yes(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.delete_ai_knowledge_base_plain_text = AsyncMock(
        return_value={"success": True, "errors": []}
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "plain-text",
                "delete",
                "--id",
                "kb-1",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--yes",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout)["success"] is True
    mock_client.delete_ai_knowledge_base_plain_text.assert_awaited_once_with(
        "kb-1", "pipe-uuid-1"
    )


def test_kb_plain_text_delete_aborts_without_confirmation(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.delete_ai_knowledge_base_plain_text = AsyncMock()

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "plain-text",
                "delete",
                "--id",
                "kb-1",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--json",
            ],
            input="n\n",
        )
    assert result.exit_code != 0
    mock_client.delete_ai_knowledge_base_plain_text.assert_not_awaited()


DOCUMENT_FULL = {
    "id": "kb-2",
    "name": "Handbook",
    "description": "Company handbook",
    "content": "https://app.pipefy.com/storage/v1/signed/orgs/o/u/h.pdf?sig=x",
    "updatedAt": "2026-07-16T00:00:00Z",
}


def _pdf(tmp_path):
    path = tmp_path / "handbook.pdf"
    path.write_bytes(b"%PDF-1.4 body")
    return path


def test_kb_document_get_json(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_ai_knowledge_base_document = AsyncMock(return_value=DOCUMENT_FULL)

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            ["kb", "document", "get", "--id", "kb-2", "--pipe-uuid", "p", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    data = json.loads(result.stdout)
    assert data["success"] is True
    assert data["knowledge_base_document"] == DOCUMENT_FULL
    mock_client.get_ai_knowledge_base_document.assert_awaited_once_with("kb-2", "p")


def test_kb_document_get_empty_result_exits_1(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    """Missing id resolves to `{}` from the SDK; the CLI must not report success."""
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_ai_knowledge_base_document = AsyncMock(return_value={})

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "document",
                "get",
                "--id",
                "kb-missing",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--json",
            ],
        )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["success"] is False
    assert "not found" in data["error"].lower()


def test_kb_document_create_gated_success(
    runner, clean_pipefy_env, saved_cwd, monkeypatch, tmp_path
):
    _env(monkeypatch)
    pdf = _pdf(tmp_path)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=GREEN_PROBE)
    mock_client.create_ai_knowledge_base_document = AsyncMock(
        return_value=DOCUMENT_FULL
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "document",
                "create",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--file",
                str(pdf),
                "--name",
                "Handbook",
                "--description",
                "Company handbook",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout)["success"] is True
    mock_client.create_ai_knowledge_base_document.assert_awaited_once_with(
        "pipe-uuid-1",
        name="Handbook",
        description="Company handbook",
        file_path=pdf,
    )


def test_kb_document_create_denied_probe_blocks_write(
    runner, clean_pipefy_env, saved_cwd, monkeypatch, tmp_path
):
    _env(monkeypatch)
    pdf = _pdf(tmp_path)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=DENIED_PROBE)
    mock_client.create_ai_knowledge_base_document = AsyncMock()

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "document",
                "create",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--file",
                str(pdf),
                "--name",
                "n",
                "--description",
                "d",
                "--json",
            ],
        )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["success"] is False
    mock_client.create_ai_knowledge_base_document.assert_not_awaited()


def test_kb_document_create_s3_step_error_json(
    runner, clean_pipefy_env, saved_cwd, monkeypatch, tmp_path
):
    from pipefy_sdk import KnowledgeBaseDocumentUploadError

    _env(monkeypatch)
    pdf = _pdf(tmp_path)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=GREEN_PROBE)
    mock_client.create_ai_knowledge_base_document = AsyncMock(
        side_effect=KnowledgeBaseDocumentUploadError(
            "S3 upload failed with HTTP 403.",
            step="s3_upload",
            body_snippet="AccessDenied",
            status_code=403,
        )
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "document",
                "create",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--file",
                str(pdf),
                "--name",
                "n",
                "--description",
                "d",
                "--json",
            ],
        )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["success"] is False
    assert data["step"] == "s3_upload"
    assert data["body_snippet"] == "AccessDenied"


def test_kb_document_create_file_read_error_is_bad_parameter(
    runner, clean_pipefy_env, saved_cwd, monkeypatch, tmp_path
):
    from pipefy_sdk import KnowledgeBaseDocumentUploadError

    _env(monkeypatch)
    pdf = _pdf(tmp_path)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=GREEN_PROBE)
    mock_client.create_ai_knowledge_base_document = AsyncMock(
        side_effect=KnowledgeBaseDocumentUploadError(
            "File must be a .pdf: notes.txt", step="file_read"
        )
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "document",
                "create",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--file",
                str(pdf),
                "--name",
                "n",
                "--description",
                "d",
            ],
        )
    assert result.exit_code == 2
    assert ".pdf" in (result.stderr or result.stdout)


def test_kb_document_update_partial(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=GREEN_PROBE)
    mock_client.update_ai_knowledge_base_document = AsyncMock(
        return_value=DOCUMENT_FULL
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "document",
                "update",
                "--id",
                "kb-2",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--name",
                "New name",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.update_ai_knowledge_base_document.assert_awaited_once_with(
        "kb-2", "pipe-uuid-1", name="New name", description=None
    )


def test_kb_document_delete_with_yes(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.delete_ai_knowledge_base_document = AsyncMock(
        return_value={"success": True, "errors": []}
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "document",
                "delete",
                "--id",
                "kb-2",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--yes",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.delete_ai_knowledge_base_document.assert_awaited_once_with(
        "kb-2", "pipe-uuid-1"
    )


DATA_LOOKUP_FULL = {
    "id": "kb-3",
    "name": "Order lookup",
    "description": "Find orders by customer email",
    "sourceRepoId": "303088927",
    "searchQuery": None,
    "outputFields": ["title", "status"],
    "updatedAt": "2026-07-18T00:00:00Z",
}

_STATIC_CONDITION_JSON = '[{"field": "title", "operator": "contains", "value": "x"}]'

_DATA_LOOKUP_CREATE_ARGS = [
    "kb",
    "data-lookup",
    "create",
    "--pipe-uuid",
    "pipe-uuid-1",
    "--name",
    "Order lookup",
    "--description",
    "Find orders",
    "--source-repo-id",
    "303088927",
    "--output-fields",
    '["title"]',
    "--conditions",
    _STATIC_CONDITION_JSON,
]


def test_kb_data_lookup_get_json(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_ai_knowledge_base_data_lookup = AsyncMock(
        return_value=DATA_LOOKUP_FULL
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "data-lookup",
                "get",
                "--id",
                "kb-3",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    data = json.loads(result.stdout)
    assert data["success"] is True
    assert data["knowledge_base_data_lookup"] == DATA_LOOKUP_FULL
    mock_client.get_ai_knowledge_base_data_lookup.assert_awaited_once_with(
        "kb-3", "pipe-uuid-1"
    )


def test_kb_data_lookup_get_not_found_exits_1(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_ai_knowledge_base_data_lookup = AsyncMock(return_value={})

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "data-lookup",
                "get",
                "--id",
                "kb-x",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--json",
            ],
        )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["success"] is False
    assert "pipefy kb list" in data["error"]


def test_kb_data_lookup_create_json(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=GREEN_PROBE)
    mock_client.create_ai_knowledge_base_data_lookup = AsyncMock(
        return_value=DATA_LOOKUP_FULL
    )

    with _client_patch(mock_client):
        result = runner.invoke(app, [*_DATA_LOOKUP_CREATE_ARGS, "--json"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    data = json.loads(result.stdout)
    assert data["success"] is True
    assert data["knowledge_base_data_lookup"] == DATA_LOOKUP_FULL
    mock_client.create_ai_knowledge_base_data_lookup.assert_awaited_once_with(
        "pipe-uuid-1",
        name="Order lookup",
        description="Find orders",
        source_repo_id="303088927",
        output_fields=["title"],
        conditions=[{"field": "title", "operator": "contains", "value": "x"}],
        search_query=None,
    )


def test_kb_data_lookup_create_gated_on_denied_probe(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=DENIED_PROBE)
    mock_client.create_ai_knowledge_base_data_lookup = AsyncMock()

    with _client_patch(mock_client):
        result = runner.invoke(app, [*_DATA_LOOKUP_CREATE_ARGS, "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["success"] is False
    mock_client.create_ai_knowledge_base_data_lookup.assert_not_awaited()


def test_kb_data_lookup_create_invalid_conditions_json_rejected(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.create_ai_knowledge_base_data_lookup = AsyncMock()

    args = list(_DATA_LOOKUP_CREATE_ARGS)
    args[args.index(_STATIC_CONDITION_JSON)] = '{"not": "an array"}'
    with _client_patch(mock_client):
        result = runner.invoke(app, args)
    assert result.exit_code != 0
    assert "--conditions must be a JSON array of objects" in (
        result.stdout + (result.stderr or "")
    )
    mock_client.create_ai_knowledge_base_data_lookup.assert_not_awaited()


def test_kb_data_lookup_create_invalid_output_fields_rejected(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.create_ai_knowledge_base_data_lookup = AsyncMock()

    args = list(_DATA_LOOKUP_CREATE_ARGS)
    args[args.index('["title"]')] = "[1, 2]"
    with _client_patch(mock_client):
        result = runner.invoke(app, args)
    assert result.exit_code != 0
    assert "--output-fields must be a JSON array of strings" in (
        result.stdout + (result.stderr or "")
    )
    mock_client.create_ai_knowledge_base_data_lookup.assert_not_awaited()


def test_kb_data_lookup_update_sends_full_definition(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=GREEN_PROBE)
    mock_client.update_ai_knowledge_base_data_lookup = AsyncMock(
        return_value=DATA_LOOKUP_FULL
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "data-lookup",
                "update",
                "--id",
                "kb-3",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--source-repo-id",
                "303088927",
                "--output-fields",
                '["title"]',
                "--conditions",
                _STATIC_CONDITION_JSON,
                "--name",
                "Renamed",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout)["success"] is True
    mock_client.update_ai_knowledge_base_data_lookup.assert_awaited_once_with(
        "kb-3",
        "pipe-uuid-1",
        source_repo_id="303088927",
        output_fields=["title"],
        conditions=[{"field": "title", "operator": "contains", "value": "x"}],
        search_query=None,
        name="Renamed",
        description=None,
    )


def test_kb_data_lookup_update_requires_definition_options(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.update_ai_knowledge_base_data_lookup = AsyncMock()

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "data-lookup",
                "update",
                "--id",
                "kb-3",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--name",
                "Renamed",
            ],
        )
    assert result.exit_code != 0
    mock_client.update_ai_knowledge_base_data_lookup.assert_not_awaited()


def test_kb_data_lookup_delete_requires_confirmation(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.delete_ai_knowledge_base_data_lookup = AsyncMock()

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "data-lookup",
                "delete",
                "--id",
                "kb-3",
                "--pipe-uuid",
                "pipe-uuid-1",
            ],
            input="n\n",
        )
    assert result.exit_code != 0
    mock_client.delete_ai_knowledge_base_data_lookup.assert_not_awaited()


def test_kb_data_lookup_delete_with_yes(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.delete_ai_knowledge_base_data_lookup = AsyncMock(
        return_value={"success": True, "errors": []}
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "data-lookup",
                "delete",
                "--id",
                "kb-3",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--yes",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout)["success"] is True
    mock_client.delete_ai_knowledge_base_data_lookup.assert_awaited_once_with(
        "kb-3", "pipe-uuid-1"
    )
